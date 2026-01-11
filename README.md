# AstroReason-Bench

A dual-purpose project for astronautics mission design:

1. **toolkits/** - Agent-facing libraries that bridge high-level reasoning with low-level physics engines
2. **engines/** - Swappable physics backends shared by toolkits, baselines, and verifiers
3. **benchmarks/** - General-purpose astronautics benchmarks for any approach (LLM or traditional)

---

## Why This Project?

### Problem 1: No Agent-Friendly Mission Planning Tools

Traditional aerospace software (STK, GMAT, etc.) is powerful but GUI-driven, making it inaccessible to AI agents. As LLMs become more capable at technical reasoning, they need **native tool interfaces**.

**toolkits/** demonstrates a potential way to design domain-specific tools for LLM interaction:
- MCP tool calling (mirrors GUI interaction) + Python API (mirrors programmatic automation)
- Tool-calling APIs for orbital mechanics, resource simulation, and planning
- Proof that complex aerospace operations can be agent-accessible

### Problem 2: Aerospace Lacks Rigorous Benchmarks

The AI community has standardized benchmarks (ImageNet, GLUE, etc.). The aerospace community doesn't have equivalent public benchmarks for algorithms.

**benchmarks/** aims at filling this gap with rigorous problem definitions:
- Contains **Datasets**(problems) and **Verifiers**(scoring logic), independent of the solution method
- Includes **Baselines** to establish performance floors.
- Designed to be solver-agnostic: usable by LLM agents, metaheuristic solvers, reinforcement learning agents, or human experts.

### Problem 3: One Physics Engine Doesn't Fit All

Different benchmarks and toolkits may require different physics backends. Some need high-fidelity propagation, while others prioritize speed; Some focus on orbital mechanics, while other lean toward onboard resources.

**engines/** decouples the physics from the problem definition. Pushing physics into this shared layer guarantees:
- **Consistency**: Single source of truth for both acting and verification (toolkits, baselines, verifiers)
- **Reuse**: Multiple benchmarks can leverage the same engine (e.g., SPG4 is likely sufficient for all LEO satellites)
