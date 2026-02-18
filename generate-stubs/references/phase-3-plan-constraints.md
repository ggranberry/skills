# Phase 3: Plan Constraint Translation

Spawn as: `Task(subagent_type="Plan")`

Plan how to translate database constraints into CrossHair state space constraints.

## Inputs

1. Schema JSON from Phase 1

## Instructions

For each model and its columns, plan the constraint code using this translation table:

| Constraint | Translation |
|------------|-------------|
| nullable=false | `space.add(result.field is not None)` |
| check: "age >= 0" | `space.add(result.age >= 0)` |
| enum: ["a", "b"] | `space.add(z3.Or(result.x == 'a', result.x == 'b'))` |
| String(N) | `space.add(len(result.field) <= N)` |
| foreign_key | Document the relationship (may affect test setup) |

## Output

Return a plan with:
1. The `_apply_constraints(result, model_type)` function code
2. Any imports needed (z3, etc.)
3. Notes on edge cases or limitations
