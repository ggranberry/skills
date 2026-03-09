# Phase 4a: Plan Constraint Application

Spawn as: `Task(subagent_type="Plan")`

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
