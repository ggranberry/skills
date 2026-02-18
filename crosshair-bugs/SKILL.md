---
name: crosshair-bugs
description: Find bugs using CrossHair symbolic execution. Use when asked to find bugs, run CrossHair, or do symbolic analysis. Orchestrates ORM detection, stub generation, schema extraction, and contract generation. Not for unit testing, linting, or static type checking.
---

# CrossHair Bugs

Top-level orchestrator that prepares a codebase for CrossHair symbolic execution by generating database stubs with schema constraints and adding PEP 316 contracts to business logic.

## Artifacts

All intermediate outputs are persisted to `.claude/artifacts/crosshair-bugs/`:

| File | Phase | Contents |
|------|-------|----------|
| `orm-detection.json` | 1 | ORM type, model files |
| `schema-constraints.json` | 3 | Models with column constraints |
| `constraint-plan.md` | 4a | Planner's reasoning and plan |
| `contract-targets.json` | 5 | Classes and functions to receive PEP 316 contracts (includes source) |
| `contract-plan.md` | 6 | Planned pre/post/inv contracts per target |
| `bugs-report.md` | 9 | CrossHair counterexamples and bug findings |

## Setup

```bash
mkdir -p .claude/artifacts/crosshair-bugs
```

## Workflow

Each phase reads a reference file with its full prompt. This keeps the orchestrator lightweight.

### Phase 1: Detect ORM

```bash
bash .claude/skills/detect-orm/scripts/detect-orm.sh > .claude/artifacts/crosshair-bugs/orm-detection.json
```

### Phase 2: Generate Base Stubs

Follow `.claude/skills/crosshair-bugs/references/phase-2-generate-base-stubs.md`

### Phase 3: Extract Schema Constraints

Follow `.claude/skills/crosshair-bugs/references/phase-3-extract-schema.md`

### Phase 4a: Plan Constraints

Follow `.claude/skills/crosshair-bugs/references/phase-4a-plan-constraints.md`

### Phase 4b: Apply Constraints

Follow `.claude/skills/crosshair-bugs/references/phase-4b-apply-constraints.md`

### Phases 5–8: Generate Contracts

Follow the `generate-contracts` skill (`.claude/skills/generate-contracts/SKILL.md`).

- **Phase 5** → generate-contracts Phase 1 (Explore: find targets, embed source)
- **Phase 6** → generate-contracts Phase 2 (Plan: design PEP 316 contracts)
- **Phase 7** → generate-contracts Phase 3 (Apply: add docstring contracts to source)
- **Phase 8** → generate-contracts Phase 4 (Validate: `crosshair check` syntax smoke test)

### Phase 9: Find Bugs

Follow `.claude/skills/crosshair-bugs/references/phase-9-find-bugs.md`

## Resuming

If a phase fails, you can resume from artifacts:
- Phase 2+ can read `orm-detection.json`
- Phase 4+ can read `schema-constraints.json`
- Phase 4b can read `constraint-plan.md`
- Phase 6+ can read `contract-targets.json`
- Phase 7+ can read `contract-plan.md`
- Phase 8 can re-run after fixing contracts
- Phase 9 can re-run after adjusting contracts or stubs

## Post-Analysis

Do NOT remove PEP 316 contracts or stubs after analysis. Contracts serve as executable specifications and enable re-running CrossHair after code changes. Only remove them if the user explicitly asks.

## Sub-skills Used

| Skill | Phase | Purpose |
|-------|-------|---------|
| detect-orm | 1 | Identify ORM and model files |
| generate-stubs | 2 | Base stub templates |
| parse-migrations | 3 | Constraint extraction patterns |
| generate-contracts | 5–8 | PEP 316 contract discovery, planning, application, validation |
