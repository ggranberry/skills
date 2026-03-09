---
name: crosshair-bugs
description: Find bugs using CrossHair symbolic execution. Use when asked to find bugs, run CrossHair, or do symbolic analysis. Orchestrates ORM detection, stub generation, schema extraction, and contract generation. Not for unit testing, linting, or static type checking.
---

# CrossHair Bugs

Top-level orchestrator that prepares a codebase for CrossHair symbolic execution by generating database stubs with schema constraints and adding PEP 316 contracts to business logic.

## Artifacts

All intermediate outputs are persisted to `.claude/artifacts/crosshair-bugs/`:

```
crosshair-bugs/
├── orm-detection.json          # Phase 1 — ORM type, model files
├── schema-constraints.json     # Phase 3 — models with column constraints
├── contract-targets.json       # Phase 5 — contract candidate manifest
├── planner-assignments.json    # Phase 5.5 — per-file planner scoping
├── plans/
│   ├── constraint-plan.md      # Phase 4a — constraint application plan
│   └── contract-plan-*.md      # Phase 6 — per-file triage + planned contracts
└── crosshair/
    ├── run_crosshair.sh         # Phase 9 — generated run script
    ├── crosshair-output-*.txt   # Phase 9 — raw CrossHair output per file
    └── bugs-report.md           # Phase 9 — counterexamples and findings
```

## Setup

```bash
mkdir -p .claude/artifacts/crosshair-bugs/plans .claude/artifacts/crosshair-bugs/crosshair
```

## Workflow

**Copy this checklist into your response at the start and check off each phase as it completes:**

```
Phase Progress:
- [ ] Phase 1: Detect ORM
- [ ] Phase 2: Generate base stubs
- [ ] Phase 3: Extract schema constraints
- [ ] Phase 4a: Plan constraints
- [ ] Phase 4b: Apply constraints
- [ ] Phase 5: Explore contract candidates
- [ ] Phase 5.5: Chunk into assignments
- [ ] Phase 6: Plan contracts (batched)
- [ ] Phase 7: Apply contracts
- [ ] Phase 8: Validate contract syntax
- [ ] Phase 9: Find bugs
```

Each phase reads a reference file with its full prompt. This keeps the orchestrator lightweight.

### Phase 1: Detect ORM

```bash
bash .claude/skills/detect-orm/scripts/detect-orm.sh > .claude/artifacts/crosshair-bugs/orm-detection.json
```

**If the detected ORM is Django**, follow the `crosshair-django` pre-flight before Phase 2:
read `.claude/skills/crosshair-django/references/preflight.md` and complete its checklist
(install dependencies into the CrossHair venv, create the `crosshair_django_setup.py` plugin,
confirm a testing settings module, add `--unblock` flags).

### Phase 2: Generate Base Stubs

Follow `.claude/skills/crosshair-bugs/references/phase-2-generate-base-stubs.md`

### Phase 3: Extract Schema Constraints

Follow `.claude/skills/crosshair-bugs/references/phase-3-extract-schema.md`

### Phase 4a: Plan Constraints

Follow `.claude/skills/crosshair-bugs/references/phase-4a-plan-constraints.md`

### Phase 4b: Apply Constraints

Follow `.claude/skills/crosshair-bugs/references/phase-4b-apply-constraints.md`

### Phases 5–8: Generate Contracts

Follow `.claude/skills/crosshair-bugs/references/phases-5-8-generate-contracts.md`

### Phase 9: Find Bugs

Follow `.claude/skills/crosshair-bugs/references/phase-9-find-bugs.md`

## Resuming

If a phase fails, you can resume from artifacts:
- Phase 2+ can read `orm-detection.json`
- Phase 4+ can read `schema-constraints.json`
- Phase 4b can read `plans/constraint-plan.md`
- Phase 5.5+ can read `contract-targets.json`
- Phase 6+ can read `planner-assignments.json`
- Phase 7+ can read `plans/contract-plan-*.md`
- Phase 8 can re-run after fixing contracts
- Phase 9 can re-run after adjusting contracts or stubs; per-file `crosshair/crosshair-output-*.txt` artifacts are skipped if they already exist — delete specific files to force a re-check

**Phase 6 (contract planning) uses file-existence progress tracking:** `batch-progress.py` diffs assignments against existing `plans/contract-plan-*.md` files, so subsequent sessions automatically resume where the last stopped. Phase 7 (apply) checks for a `## Applied` marker at the end of each plan file to skip already-processed plans.

## Post-Analysis

Do NOT remove PEP 316 contracts or stubs after analysis. Contracts serve as executable specifications and enable re-running CrossHair after code changes. Only remove them if the user explicitly asks.

## Sub-skills Used

| Skill | Phase | Purpose |
|-------|-------|---------|
| detect-orm | 1 | Identify ORM and model files |
| crosshair-django | 1 (post), 6, 9 | Django/DRF pre-flight, contract patterns, run-script flags (Django only) |
| generate-stubs | 2 | Base stub templates |
| parse-migrations | 3 | Constraint extraction patterns |
| generate-contracts | 5–8 | PEP 316 contract discovery, planning, application, validation |
