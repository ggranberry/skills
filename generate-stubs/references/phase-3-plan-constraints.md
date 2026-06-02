# Phase 3: Plan Constraint Translation

Spawn as: `Task(subagent_type="Plan")`

Plan how to translate database constraints into CrossHair state space constraints.

## Inputs

1. Schema JSON from Phase 1

## Instructions

For each model and its columns, plan the constraint code using this translation table:

| Constraint | Translation |
|------------|-------------|
| nullable=false | `space.add(result.field != None)` |
| check: "age >= 0" | `space.add(result.age >= 0)` |
| enum: ["a", "b"] | `space.add(z3.Or(result.x == 'a', result.x == 'b'))` |
| String(N) | `space.add(len(result.field) <= N)` |
| foreign_key | Document the relationship (may affect test setup) |

### Critical: do **not** use `is`/`is not` in constraint lambdas

`is None` / `is not None` are identity comparisons that CrossHair **cannot** intercept. They evaluate eagerly to a concrete Python `bool`, and `space.add(<concrete bool>)` raises `crosshair.util.CrossHairInternal: Attempted to assert a concrete boolean`. This kills the whole analysis when one constraint fires.

Always use `== None` / `!= None` (CrossHair overrides `__eq__` on its symbolic types). Same lesson for `is True`/`is False` — use `== True`/`== False`.

### Critical: catch `BaseException`, not `Exception`, around `space.add(...)`

`CrossHairInternal` inherits from `BaseException`, not `Exception`. A `try/except Exception` around `space.add(constraint_fn(result))` will **silently fail to catch it** and the analysis dies. Use:

```python
for _field, constraint_fn in constraints:
    try:
        space.add(constraint_fn(result))
    except BaseException:
        # CrossHairInternal is a BaseException subclass — suppress so one
        # eagerly-realized constraint doesn't kill the whole analysis.
        pass
```

This is the recommended shape regardless of how careful the constraint lambdas are, because there are other code paths inside `space.add` that can raise `CrossHairInternal` (e.g. realization triggered by `getattr` on a symbolic proxy).

### Recommended: add `_apply_lookup_constraints` for `.objects.get(id=k)`

By default, `MockManager.get(id=k)` returns a proxy whose `.id` is an *independent* symbolic int — no relationship to `k`. Postconditions like `__return__.id == lookup_key` are then trivially satisfiable by CrossHair (it just picks `mock.id = lookup_key`), masking real lookup-key/result mismatches.

The cheap fix is a helper that registers the equality constraint after `proxy_for_type`:

```python
def _apply_lookup_constraints(result: Any, kwargs: dict) -> None:
    """Link exact-match lookup kwargs (id=, pk=) to the returned mock's fields."""
    if result is None or not kwargs:
        return
    space = context_statespace()
    if space is None:
        return
    for key in ('id', 'pk'):
        if key in kwargs:
            try:
                space.add(getattr(result, key) == kwargs[key])
            except BaseException:
                pass
```

Wire it into both `MockManager.get` and `MockQuerySet.get` immediately after `proxy_for_type(...)` and before the schema-constraint application. This makes lookup-key-linked postconditions symbolically tractable for the common Django pattern `Model.objects.get(id=...)`.

## Output

Return a plan with:
1. The `_apply_constraints(result, model_type)` function code — using `== None` / `!= None`, wrapped in `except BaseException`
2. The `_apply_lookup_constraints(result, kwargs)` helper if the project has functions whose post-conditions link `Model.objects.get(id=k)` to `__return__.id`
3. Any imports needed (z3, etc.)
4. Notes on edge cases or limitations
