# SatNet Mock Solution Fixtures

本目录包含 SatNet benchmark 的 5 个解文件及其真实指标。这些文件作为验证 SatNet 验证器实现正确性的“黄金标准”。它们是验证器测试 fixtures，不是文献基线。

## 来源与方法论

这些解使用 **参考 `satnet` 包**（NASA/JPL 基线）生成，该包定义了问题逻辑和评分机制。

**源仓库**：[https://github.com/edwinytgoh/satnet.git](https://github.com/edwinytgoh/satnet.git)

### 生成过程
1. **环境搭建**：我们为 2018 年数据集中的 5 周（W10、W20、W30、W40、W50）分别实例化了 `satnet.envs.SimpleEnv`。
2. **智能体执行**：我们运行了一个“随机智能体” episode。
3. **调度导出**：我们没有使用 `sim.generate_schedule_json()`（它只导出已满足请求的跟踪弧段），而是调用了一个辅助函数 `export_full_schedule(sim)`，来自 `docs/reference_repo/satnet/generate_ground_truth.py`，该函数：
   - 重放 `sim.tracks` 中所有已满足请求的原始导出逻辑，并且
   - 额外导出任何已经计入仿真器内部核算、但留在 `sim._tid_tracks_temp` 中的合法部分拆分跟踪弧段。
   这确保了 JSON 调度完全反映了参考仿真器在计算其指标时使用的所有分配（没有遗漏的“幽灵”跟踪弧段）。
4. **指标捕获**：然后我们直接从仿真器状态读取指标：
   - **Score**：成功通信的总小时数（所有导出调度行的 TRACKING_OFF - TRACKING_ON 之和）。
   - **$U_i$（未满足比例）**：来自 `sim.U_i` 的每任务未满足比例，基于 `mission_remaining_duration` 和 `mission_requested_duration`。
   - **$U_{rms}$**：直接来自 `sim.U_rms`。
   - **$U_{max}$**：直接来自 `sim.U_max`。

因为 `export_full_schedule` 导出了所有影响 `sim.U_i` 的跟踪弧段，任何从调度 JSON 加问题数据重新推导公平性的验证器都会与这些存储的指标匹配。

## 文件结构

对于每一周（例如 `W10_2018`），有两个文件：

1. **`W10_2018_solution.json`**：包含已分配跟踪弧段列表的调度文件。
   ```json
   [
     {
       "RESOURCE": "DSS-34",
       "SC": "521",
       "START_TIME": 1520286007,
       "TRACKING_ON": 1520289607,
       "TRACKING_OFF": 1520293207,
       "END_TIME": 1520294107,
       "TRACK_ID": "fc9bbb54-3-1"
     },
     ...
   ]
   ```

2. **`W10_2018_metrics.json`**：真实分数和公平性指标。
   ```json
   {
     "score": 234.5678,
     "n_tracks": 145,
     "n_satisfied_requests": 132,
     "u_rms": 0.4512,
     "u_max": 0.8500,
     "per_mission_u_i": {
       "521": 0.0,
       "522": 0.5,
       ...
     }
   }
   ```

## 使用方式

`test_satnet_verifier.py` 脚本加载这些成对文件。它验证：
1. `solution.json` 被我们的独立验证器判定为 **valid**。
2. 我们的验证器计算的分数与 `metrics.json` 中的分数匹配。
3. 我们的验证器计算的公平性指标（$U_{rms}$、$U_{max}$）与 `metrics.json` 中的值匹配。

## 复现

以下是我们用于生成 mock solutions 和真实指标的代码：

```generate_ground_truth.py
#!/usr/bin/env python3
"""
Generate ground truth solutions for the SatNet benchmark.

This script uses the reference SatNet implementation to generate solutions
for all available weeks, along with their scores and fairness metrics.

Run from within the satnet reference repo directory with the venv activated:
    cd docs/reference_repo/satnet
    source .venv/bin/activate.fish
    python generate_ground_truth.py
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

# Add satnet package to path
sys.path.insert(0, str(Path(__file__).parent))

import satnet
from satnet.simulator.prob_handler import ProbHandler, json_keys
from satnet.envs.simple_env import SimpleEnv
from satnet.gym_wrappers.reward_wrappers import HrsAllocatedWrapper

# Output directory (absolute path to project test fixtures)
OUTPUT_DIR = Path.home() / "Developments" / "astro-reason" / "tests" / "fixtures" / "satnet_mock_solutions"

# Weeks to generate solutions for
WEEKS = [10, 20, 30, 40, 50]
YEAR = 2018


# Column indices into SchedulingSimulator.week_array
SUBJECT = json_keys.index("subject")
SETUP_TIME = json_keys.index("setup_time")
TEARDOWN_TIME = json_keys.index("teardown_time")


def run_random_agent_episode(env, seed=42):
    """
    Run a single episode with the random agent.
    
    Returns the final environment state with all metrics.
    """
    np.random.seed(seed)
    obs = env.reset()
    done = False
    total_reward = 0.0
    n_steps = 0
    
    while not done and n_steps < 9999:
        sample_action = env.action_space.sample()
        if not np.all(obs["action_mask"] == 0):
            sample_action = np.random.choice(
                np.where(obs["action_mask"] == 1)[0], 1
            )[0]
        else:
            sample_action = 0
            
        obs, reward, done, info = env.step(sample_action)
        total_reward += reward
        n_steps += 1
    
    return env, total_reward, info


def export_full_schedule(sim):
    """Export a schedule JSON consistent with the simulator's internal metrics.

    The upstream ``generate_schedule_json`` only exports tracks for
    *satisfied* requests (``sim.satisfied_tracks``). However, when an
    episode terminates due to the step limit, the simulator may have
    allocated valid partial split tracks for some long requests that are
    stored in ``sim._tid_tracks_temp`` and already debited from
    ``mission_remaining_duration``, but never promoted into
    ``sim.tracks`` / ``generate_schedule_json``.

    This helper returns a combined schedule that includes:
    - all tracks from ``sim.tracks`` for satisfied requests (identical to
      ``generate_schedule_json``), and
    - additional per-antenna rows for any remaining partial split tracks in
      ``sim._tid_tracks_temp`` for unsatisfied, non-undone requests.
    """

    track_list = []

    # Recreate the behaviour of SchedulingSimulator.generate_schedule_json
    for trx_on, trx_off, resource_combination, sc, track_id in sim.tracks:
        req_iloc = sim.track_idx_map[track_id]
        if track_id in sim.satisfied_tracks:
            trx_on_abs = int(trx_on + sim.start_date)
            trx_off_abs = int(trx_off + sim.start_date)
            setup = int(sim.week_array[req_iloc, SETUP_TIME])
            teardown = int(sim.week_array[req_iloc, TEARDOWN_TIME])
            for antenna in resource_combination.split("_"):
                track_list.append(
                    {
                        "RESOURCE": antenna,
                        "SC": int(sc),
                        "START_TIME": trx_on_abs - setup,
                        "TRACKING_ON": trx_on_abs,
                        "TRACKING_OFF": trx_off_abs,
                        "END_TIME": trx_off_abs + teardown,
                        "TRACK_ID": track_id,
                    }
                )

    # Add partial split tracks that contributed to the internal metrics but
    # are not part of sim.tracks / satisfied_tracks.
    for track_id, segments in sim._tid_tracks_temp.items():
        if not segments:
            continue
        if track_id in sim.satisfied_tracks:
            # Already exported above via sim.tracks
            continue
        if track_id in sim.incomplete_split_reqs:
            # These were fully undone via undo_request and do not contribute
            # to mission_remaining_duration.
            continue

        req_iloc = sim.track_idx_map[track_id]
        sc = int(sim.week_array[req_iloc, SUBJECT])
        setup = int(sim.week_array[req_iloc, SETUP_TIME])
        teardown = int(sim.week_array[req_iloc, TEARDOWN_TIME])

        for trx_on, trx_off, resource_combination in segments:
            trx_on_abs = int(trx_on + sim.start_date)
            trx_off_abs = int(trx_off + sim.start_date)
            for antenna in resource_combination.split("_"):
                track_list.append(
                    {
                        "RESOURCE": antenna,
                        "SC": sc,
                        "START_TIME": trx_on_abs - setup,
                        "TRACKING_ON": trx_on_abs,
                        "TRACKING_OFF": trx_off_abs,
                        "END_TIME": trx_off_abs + teardown,
                        "TRACK_ID": track_id,
                    }
                )

    return track_list


def generate_solution_for_week(week: int, year: int, prob_handler: ProbHandler) -> dict:
    """
    Generate a solution for a specific week using the reference implementation.
    
    Returns:
        Dictionary with solution tracks, score, and fairness metrics.
    """
    config = {
        "prob_handler": prob_handler,
        "shuffle_requests": False,
        "absolute_max_steps": 10000,
        "rough_schedule_cols": 169,
        "tol_mins": 0.1,
        "allow_splitting": True,
        "week": week,
    }
    
    env = SimpleEnv(config)
    env = HrsAllocatedWrapper(env)
    
    # Run the random agent
    final_env, total_reward, info = run_random_agent_episode(env, seed=42)
    
    # Extract the simulator for metrics
    sim = final_env.sim

    # Generate schedule JSON that reflects all allocations the simulator
    # used for its internal metrics (including partial split tracks).
    schedule = export_full_schedule(sim)

    # Calculate score (total tracking hours) from the exported schedule
    score = sum(
        (track["TRACKING_OFF"] - track["TRACKING_ON"]) / 3600.0
        for track in schedule
    )

    # Fairness metrics come directly from the simulator's internal
    # accounting (mission_remaining_duration), which is the same source
    # used during RL training.
    missions = list(sim.mission_requested_duration.keys())
    u_i_array = sim.U_i
    per_mission_u_i = {
        str(mission): float(u_i) for mission, u_i in zip(missions, u_i_array)
    }
    u_rms = float(sim.U_rms)
    u_max = float(sim.U_max)
    
    return {
        "week": week,
        "year": year,
        "solution": schedule,
        "metrics": {
            "score": score,
            "total_reward": total_reward,  # From reward wrapper
            "n_tracks": len(schedule),
            "n_satisfied_requests": len(sim.satisfied_tracks),
            "u_rms": u_rms,
            "u_max": u_max,
            "per_mission_u_i": per_mission_u_i,
        }
    }


def main():
    """Generate ground truth solutions for all weeks."""
    print("=" * 80)
    print("SatNet Ground Truth Generator")
    print("=" * 80)
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load problem handler
    print(f"\nLoading problems from: {satnet.problems[2018]}")
    prob_handler = ProbHandler(satnet.problems[2018])
    
    # Summary list for all solutions
    all_results = []
    
    for week in WEEKS:
        print(f"\n{'-' * 80}")
        print(f"Week {week}, {YEAR}")
        print(f"{'-' * 80}")
        
        try:
            result = generate_solution_for_week(week, YEAR, prob_handler)
            
            metrics = result["metrics"]
            print(f"✓ Generated solution:")
            print(f"  - Score (hours): {metrics['score']:.4f}")
            print(f"  - Tracks: {metrics['n_tracks']}")
            print(f"  - Satisfied requests: {metrics['n_satisfied_requests']}")
            print(f"  - U_rms: {metrics['u_rms']:.4f}")
            print(f"  - U_max: {metrics['u_max']:.4f}")
            
            # Save solution to separate file
            solution_file = OUTPUT_DIR / f"W{week}_{YEAR}_solution.json"
            with open(solution_file, "w") as f:
                json.dump(result["solution"], f, indent=2)
            print(f"  - Solution saved to: {solution_file}")
            
            # Save metrics to separate file
            metrics_file = OUTPUT_DIR / f"W{week}_{YEAR}_metrics.json"
            with open(metrics_file, "w") as f:
                json.dump(result["metrics"], f, indent=2)
            print(f"  - Metrics saved to: {metrics_file}")
            
            # Add to summary
            all_results.append({
                "week": week,
                "year": YEAR,
                "solution_file": f"W{week}_{YEAR}_solution.json",
                "metrics_file": f"W{week}_{YEAR}_metrics.json",
                "score": metrics["score"],
                "n_tracks": metrics["n_tracks"],
                "u_rms": metrics["u_rms"],
                "u_max": metrics["u_max"],
            })
            
        except Exception as e:
            print(f"✗ Error generating solution: {e}")
            import traceback
            traceback.print_exc()
    
    # Save summary metadata
    summary_file = OUTPUT_DIR / "ground_truth_summary.json"
    with open(summary_file, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n{'-' * 80}")
    print(f"Summary")
    print(f"{'-' * 80}")
    print(f"Generated {len(all_results)} solutions")
    print(f"Summary saved to: {summary_file}")
    print(f"\nScores:")
    for r in all_results:
        print(f"  W{r['week']}_{r['year']}: {r['score']:.4f}h, U_rms={r['u_rms']:.4f}, U_max={r['u_max']:.4f}")
    
    print("\n" + "=" * 80)
    print("Done!")
    print("=" * 80)


if __name__ == "__main__":
    main()
```

要复现，请克隆 [https://github.com/edwinytgoh/satnet.git](https://github.com/edwinytgoh/satnet.git)，安装必要的依赖，创建包含上述内容的 Python 脚本并运行该脚本。
