---
name: trace-case-study
description: Study benchmark or agent-run traces and write evidence-first case studies. Use when the user asks to inspect traces, compare harness behavior, explain surprising benchmark scores, diagnose why an evaluated space agent succeeded or failed, or create/update a case study report from trace artifacts, aggregate reports, verifier behavior, prompt/workspace contracts, README files, skills, solver models, or solution schemas.
---

# Trace Case Study

## Overview

Use this skill to turn surprising benchmark outcomes into reusable case-study reports grounded in stable repository artifacts. Do not start from a favorite failure pattern. Start from the observed outcome, reconstruct what the evaluated space agent could see, and then test competing explanations against the trace, benchmark contract, controls, and verifier behavior.

The central question is authority discipline: what source of truth did the evaluated space agent use for the task contract, validity, scoring, and domain model? A private solver model is often normal, especially when the verifier is opaque and the README is the exposed contract. It becomes a red flag only when the private model substitutes for the provided authoritative verifier or contradicts it without being reconciled.

## Workflow

1. Identify the reported outcome.
   - Start from aggregate reports such as `experiments/*/reports/*.md`.
   - Record exact benchmark, harness, split, case ids, validity, primary metrics, and diagnostic counters like `num_actions`.
   - Include successes as controls when they are relevant; a high score can be lucky, contract-faithful, or rescued by late verifier use.
   - Do not assume success or failure means the same thing across benchmarks; inspect the benchmark contract.

2. Anchor to stable artifacts.
   - Prefer tracked reports, trace exports, prompt fragments, benchmark README files, verifier source, and experiment configs.
   - Avoid making the report depend on ignored `results/*` paths unless the user explicitly asks for ad hoc local debugging evidence.
   - If ignored artifacts helped during exploration, translate the finding back to tracked evidence before writing.

3. Reconstruct the workspace authority hierarchy.
   - Inspect the benchmark experiment config to see what was assembled into `/app/workspace`: usually `README.md`, `case/`, `verifier`, `AGENTS.md`, and prompt files.
   - Inspect prompt fragments, workspace instructions, README contracts, visible skills, and expected solver entrypoints.
   - Separate what the evaluated space agent could see from what you can inspect retrospectively. Verifier source is useful analyst evidence, but the evaluated space agent usually saw only an opaque verifier executable plus README instructions.
   - Use verifier source to explain why a submitted solution was accepted, rejected, scored low, or silently ignored; do not imply the evaluated space agent had that source unless the trace or workspace proves it.

4. Inspect trace behavior chronologically.
   - First minutes matter: did the space agent list `/app/workspace`, read `README.md`, run `verifier --help`, or only inspect `case/`?
   - Did it read relevant skills such as `brahe`, or did it hand-roll domain logic without checking available guidance?
   - Track when the first solution schema appears and whether later scripts reinforce it.
   - Distinguish external verifier output from private solver metrics, custom assertions, or generated proxy validators.
   - Private propagation, geometry, scheduling, or scoring code is not automatically suspicious; these are often needed for search. It is suspicious when such code becomes the final acceptance test after the local verifier disagrees.
   - Look for self-contained alternate contracts: custom `verify.py`, guessed coordinate transforms used as proof of validity, private objective functions treated as benchmark scores, or validations that assert invented fields.

5. Compare against controls.
   - Compare high-scoring and low-scoring cases for the same harness.
   - Compare other harnesses on the same case when available.
   - Ask whether performance differences follow from authority acquisition, schema fidelity, skill use, solver model quality, optimization/search quality, verifier timing, timeout, or real problem difficulty.
   - Actively check for counterexamples. If a case succeeds without reading a README or verifier, call that out as luck, prior knowledge, task simplicity, or hidden robustness only when the evidence supports it.

6. Write the case study.
   - Lead with the observable outcome.
   - Separate immediate symptom from root cause.
   - Cite stable artifacts by path.
   - Include short code snippets only when they expose the causal mechanism.
   - Prefer precise claims such as "valid empty schedule due to unparsed actions," "private access model replaced verifier acceptance," or "solver optimized a proxy metric" over broad claims such as "the model was bad at geometry."
   - When the user asks not to wrap paragraphs, keep paragraphs unwrapped.

## Explanation Patterns

Use these as hypotheses, not templates. Keep only the ones supported by evidence.

- **Authority acquisition**: The evaluated space agent did or did not read the README, verifier help, workspace instructions, or relevant skills before committing to a representation.
- **Acceptance discipline**: The evaluated space agent used the packaged verifier as the final arbiter, used it only as a late debugger, or replaced it with a private validator.
- **Contract/schema mismatch**: The output used invented top-level keys, missing action types, ignored fields, or a schema from a neighboring benchmark.
- **Domain model drift**: The solver used an approximate physical, geometric, scheduling, or scoring model whose assumptions diverged from the benchmark contract or verifier.
- **Search/optimization weakness**: The representation was valid but the search strategy produced empty, trivial, or low-value solutions.
- **Runtime/tooling friction**: Failures came from environment setup, dependency choices, timeouts, file paths, or brittle scripts rather than task reasoning.
- **Problem difficulty or case structure**: The case itself is harder, has sparse opportunities, or exposes edge conditions that simpler cases do not.
- **Lucky success**: The final score is good despite weak authority discipline because the guessed schema, heuristic, or case geometry happened to align with the verifier.

## Diagnostic Checklist

- Did the space agent read `README.md`?
- Did it read relevant skills before reimplementing domain logic?
- Did it run the local verifier before optimizing?
- Did it run the local verifier before finishing?
- Did the submitted JSON use the required top-level key and action `type`?
- Did private validation merely guide search, or did it replace the verifier as acceptance authority?
- Did the verifier silently skip unknown action types or missing top-level keys?
- Did the model optimize a proxy metric that can disagree with the benchmark metric?
- Did the trace contain final claims that conflict with aggregate metrics?
- Did verifier source explain the behavior only retrospectively, or was that behavior visible to the evaluated space agent through README/help output?
- Is the evidence available from tracked artifacts?

## Helper Script

Use `scripts/trace_signals.py` to quickly summarize trace exports:

```bash
python .agents/skills/trace-case-study/scripts/trace_signals.py experiments/main_agentic/reports/traces/data/events/*claude_code*case_0001.js
```

The script reports early root/README/verifier signals, skill-loading hints, action-schema keywords, private model or acceptance hints, and final metric claims. Treat it as a triage aid; still read the relevant trace excerpts yourself before writing conclusions.
