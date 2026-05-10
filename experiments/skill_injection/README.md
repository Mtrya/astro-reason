# Skill Injection Ablation

This experiment family tracks issue #59: measuring whether task-specific,
repository-owned skills improve space-agent performance when benchmark,
runtime, verifier exposure, and harness settings are otherwise fixed.

The initial benchmark is `stereo_imaging`. It was selected because weak
harnesses often produce invalid or valid-but-near-zero solutions under opaque
verifier exposure, while transparent verifier exposure shows the task is
learnable when agents receive better constraint feedback.

## Conditions

- `no_skill`: control condition; no injected task-specific skills.
- `compact_domain`: one compact stereo-imaging procedural skill.
- `skill_pack`: four focused skills covering Python search performance,
  OR-Tools CP-SAT modeling, classical OR scheduling methods, and
  stereo-imaging product strategy.

Skill assembly is owned by the condition profiles under:

```text
experiments/skill_injection/conditions/
```

The copied skill payloads live under:

```text
experiments/_fragments/skills/skill_injection/
```

That fragments directory should contain only actual skill directories, not
experiment manifests.

## Planning

Preview the configured matrix:

```bash
uv run python experiments/skill_injection/run.py --dry-run
```

Preview only the control condition:

```bash
uv run python experiments/skill_injection/run.py \
  --dry-run \
  --condition no_skill \
  --harness opencode_dpsk \
  --case case_0001
```

The runner currently implements dry-run planning only. Execution, aggregation,
reports, and plots still need to be added before publishing experiment results.
