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

The non-control skill directories are intentionally planned, not complete. The
bundle manifests live under:

```text
experiments/_fragments/skills/skill_injection/
```

Do not run `compact_domain` or `skill_pack` as evidence until their referenced
skill directories exist and the writing roadmap phases are complete.

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
reports, and plots should be added after the skill content exists, so the
experiment does not accidentally publish placeholder guidance.

## Skill Writing Roadmaps

The source-grounded skill writing plan is in:

```text
experiments/skill_injection/roadmaps/SKILL_WRITING_ROADMAP.md
```

