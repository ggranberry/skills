# Phase 4a: Plan Constraint Application

Spawn as: `Agent(subagent_type="Plan")`

Plan how to apply database constraints to CrossHair symbolic variables.

## Instructions

1. Read `.claude/artifacts/crosshair-bugs/schema-constraints.json`
2. Read `_crosshair_stubs.py` to understand current structure

For each constraint type, plan the translation:

| Constraint | CrossHair Code |
|------------|----------------|
| nullable=false | `space.add(result.field is not None)` |
| check: "age >= 0" | `space.add(result.age >= 0)` |
| enum: ["a","b"] | `space.add(z3.Or(result.x == 'a', result.x == 'b'))` |
| String(N) | `space.add(len(result.field) <= N)` |

**Critical:** every `space.add(...)` MUST be wrapped in `try: ... except BaseException: pass`. `space.add` can raise `crosshair.util.CrossHairInternal` (e.g. "Attempted to assert a concrete boolean") which extends `ControlFlowException` → `BaseException`, **not** `Exception`. A plain `except Exception:` lets the error propagate and kills the entire analysis run with a misleading traceback. This was a silent stub-failure mode on a real project (wger, 2026-05).

## Output

Write to `.claude/artifacts/crosshair-bugs/plans/constraint-plan.md`:

```markdown
# Constraint Application Plan

## Imports Needed
- from crosshair.statespace import context_statespace
- import z3 (if enums present)

## _apply_constraints Function Structure
[describe the function]

## Per-Model Constraints

### User
- email: not null → space.add(result.email is not None)
- age: check → space.add(result.age >= 0)

### Article
...

## Integration Points
- Update .first() to call _apply_constraints(result, self.model_type)
- Update .get() similarly
- etc.
```

Do NOT write code — just the plan in markdown.
