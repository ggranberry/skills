---
name: generate-contracts
description: Add PEP 316 docstring contracts (preconditions, postconditions, invariants) to business logic functions for CrossHair symbolic analysis. Use when asked to add contracts, prepare for CrossHair, or annotate functions with pre/post conditions. Not for general code documentation or type annotations.
---

# Generate Contracts

Adds PEP 316 docstring contracts to business logic classes and functions so CrossHair can verify them symbolically against database stubs.

## Purpose

CrossHair stubs replace DB calls with symbolic values, but without contracts there is nothing to *check*. Contracts define what "correct" means:

- **Preconditions** (`pre:`) declare what must be true for a function to work correctly
- **Postconditions** (`post:`) declare what the function guarantees when it returns
- **Invariants** (`inv:`) declare what must always be true about an object's state

CrossHair searches for inputs that satisfy preconditions but violate postconditions or invariants — those are bugs.

No library dependency is needed. PEP 316 contracts are pure docstrings that CrossHair reads natively.

## Prerequisites

Before running this skill:
- `orm-detection.json` must exist (from detect-orm)
- `schema-constraints.json` must exist (from parse-migrations)
- `_crosshair_stubs.py` should exist (from generate-stubs), though contracts can be planned without it

## Context Isolation

Each phase runs as a separate agent with its own context:

| Phase | Reads | Does NOT read |
|-------|-------|---------------|
| Phase 1 (Explore) | orm-detection.json, exclusions.md, source files (for metadata extraction) | schema-constraints.json, pep316-guide.md |
| Phase 2 (Plan) | contract-targets.json (lightweight manifest), schema-constraints.json, pep316-guide.md, source files (scoped to batch) | exclusions.md (already applied in Phase 1) |
| Phase 3 (Apply) | contract-plan.md, source files (to edit) | contract-targets.json, schema-constraints.json |
| Phase 4 (Validate) | Modified source files (via CrossHair CLI) | Everything else — this is just a bash command |

**Phase 1 outputs a lightweight manifest** (file paths, function names, signatures, line counts) — no embedded source. **Phase 2 reads source files directly**, scoped to its assigned batch. Phase 2 is the **only** phase that reads the PEP 316 guide.

## Workflow

### Phase 1: Explore (Discover Contract Candidates)

Spawn Explore agent to perform a broad, mechanical sweep of the project. This phase discovers all functions that could potentially receive contracts, applying only mechanical exclusions. It does NOT judge contract-worthiness.

Read and follow the prompt in `.claude/skills/generate-contracts/references/phase-1-explore.md`.

Write output to `.claude/artifacts/crosshair-bugs/contract-targets.json`.

### Phase 2: Plan Contracts

Spawn Planner agent to triage candidates and design contracts. The orchestrator splits the manifest from Phase 1 into batches of 3–5 files. Each batch gets its own Phase 2 agent.

The planner first triages each function as CONTRACT or SKIP (with reason), then designs contracts only for CONTRACT functions. Skipped functions are recorded in the output for auditability.

**This is the only phase that reads the PEP 316 guide** at `.claude/skills/generate-contracts/references/pep316-guide.md`.

Read and follow the prompt in `.claude/skills/generate-contracts/references/phase-2-plan.md`.

Write output to `.claude/artifacts/crosshair-bugs/contract-plan.md`.

### Phase 3: Apply Contracts

Spawn Generator agent to add docstring contracts. This is mechanical — just apply the plan.

Read and follow the prompt in `.claude/skills/generate-contracts/references/phase-3-apply.md`.

### Phase 4: Validate Contract Syntax

Quick smoke test to confirm CrossHair can find and parse the contracts. This is NOT a bug-finding run — just a syntax check.

```bash
crosshair check <file> \
  --per_condition_timeout 1 \
  --analysis_kind PEP316 \
  2>&1
```

Run this on each file modified in Phase 3. Timeouts and "no violation found" are both fine — they mean the contract was parsed successfully.

## Output

- `.claude/artifacts/crosshair-bugs/contract-targets.json` — discovered candidates (lightweight manifest)
- `.claude/artifacts/crosshair-bugs/contract-plan.md` — triage decisions + planned contracts with rationale
- Modified source files with PEP 316 docstring contracts

## Resuming

- Phase 2+ can read `contract-targets.json`
- Phase 3 can read `contract-plan.md`
