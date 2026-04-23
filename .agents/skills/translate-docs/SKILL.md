---
name: translate-docs
description: Translate technical documentation (benchmark READMEs, contracts, dataset cards) from English into a target language while preserving structure, code, and domain accuracy.
---

## When to use

- Adding a new language translation under `docs/i18n/<lang>/`
- Updating an existing translation after the English source changes
- Translating benchmark READMEs, dataset READMEs, `benchmark_contract.md`, `DATASET_CARD.md`, or repository-level docs
- Any future language expansion (e.g., `docs/i18n/ja/`, `docs/i18n/de/`) that follows the `_TERMS.md` glossary pattern

## Before you start

1. Read the English source file(s) you need to translate.
2. Locate the target-language glossary:
   - `docs/i18n/<lang>/_TERMS.md`
   - If it does not exist, create it first by extracting key domain terms from the English source and defining their canonical translations (discuss with the maintainer).
3. Check whether `scripts/check_i18n_sync.py` exists. If it does, H1/H2 headings must remain in one-to-one correspondence with the English source (same count and level). Body text can be freely restructured for naturalness.

## Core rules

### 1. Terminology is canonical

- The `_TERMS.md` glossary is the single source of truth for that language.
- Every term listed in `_TERMS.md` must be used exactly as specified.
- If an English term is not in `_TERMS.md` yet, add it with a well-reasoned translation before using it.
- Do not invent ad-hoc synonyms for glossary terms inside the same document.

### 2. Preserve code and schema

Keep the following in English (do not translate):

- JSON / YAML keys and values that are identifiers (e.g., `"type": "observation"`)
- CLI commands, flags, file paths
- Metric / field names in backticks (e.g., `coverage_ratio`, `mean_latency_ms`)
- Package names, module names, and API names (e.g., `brahe`, `datasets`)
- BibTeX keys and citation metadata

### 3. Adapt sentence structure for the target language

- Do not translate sentence-for-sentence if the target language flows better with clause reordering.
- Break up long English sentences that become unreadable when directly rendered.
- Use active voice where the target language prefers it.
- After drafting, run the appropriate `humanizer` skill for the target language (e.g., `humanizer-zh`) to remove translation artifacts.

### 4. Heading parity for i18n sync

If the repo enforces structural sync via `scripts/check_i18n_sync.py`:

- H1 and H2 headings must match the English source in count and level.
- The text of the heading itself should be translated naturally, not word-for-word.
- Do not add or remove H1/H2 sections.
- H3+ may be added or omitted if they help readability, unless the sync script also checks them.

### 5. Domain-specific nuance

Space-mission documentation frequently uses terms that have both everyday and engineering meanings. Prefer the engineering convention of the target language:

- English *horizon* → 任务时域 (not just "时域")
- English *slew* → 姿态机动 (not generic "机动")
- English *valid/invalid* → 合法/非法 (not just "有效/无效")

When no engineering convention exists, choose the clearest descriptive phrase and add it to `_TERMS.md`.

## Translation workflow

```text
For each file:
  1. Read English source
  2. Read docs/i18n/<lang>/_TERMS.md
  3. Draft translation section by section
  4. Run humanizer-<lang> on the draft
  5. Verify heading parity against English source
  6. Write to target path
  7. Run scripts/check_i18n_sync.py (if available)
  8. Run focused tests for the affected benchmark
```

## Creating a new `_TERMS.md`

When bootstrapping a new language, seed `_TERMS.md` with these categories:

1. **Architecture terms** — benchmark, verifier, generator, dataset, fixture, smoke test
2. **Roles & entities** — space agent, solver, satellite, constellation, ground station
3. **Actions & scheduling** — observation, schedule, strip observation, track
4. **Geometry & orbit** — ground track, TLE, off-nadir, slew, bang-coast-bang, elevation angle
5. **Resources & constraints** — battery state of charge, power model, eclipse, sunlit
6. **Scoring & metrics** — coverage ratio, service fraction, latency, valid/invalid
7. **Benchmark-specific terms** — scene types, tri-stereo, B/H proxy, pixel scale ratio

## Verification checklist

- [ ] `_TERMS.md` exists and covers all domain terms used in the translation
- [ ] No code identifiers, JSON keys, CLI args, or metric names were translated
- [ ] H1/H2 count and level match the English source (if i18n sync is enforced)
- [ ] `scripts/check_i18n_sync.py` passes (if available)
- [ ] Focused tests for any affected benchmark pass
- [ ] The translation has been run through the target-language humanizer skill

## Example prompt for future sessions

> "Use the `translate-docs` skill to translate the newly added `benchmarks/<name>/README.md` into Chinese. Read `docs/i18n/zh_CN/_TERMS.md` first, follow the glossary strictly, keep all code and metrics in English, and run `scripts/check_i18n_sync.py` and the benchmark tests afterward."
