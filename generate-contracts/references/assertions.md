# Assertions as Intermediate Contracts

CrossHair checks `assert` statements inside function bodies, not just PEP 316 docstring contracts. While `pre:`/`post:`/`inv:` define contracts at function boundaries, `assert` lets CrossHair verify intermediate values *within* the function itself.

## When to use assertions

Assertions are most valuable when a function has internal steps where correctness can be stated independently of the final return value. They catch bugs that a postcondition alone would miss — particularly when the postcondition only checks the end result and a subtle corruption happens mid-function.

### Loop invariants

The strongest use case is forming loop invariants: assertions at the start or end of a loop body that must hold on every iteration.

```python
def redistribute(self, items, buckets):
    """
    pre: len(buckets) > 0
    pre: all(b.capacity > 0 for b in buckets)
    post: sum(b.count for b in buckets) == len(items)
    """
    total_placed = 0
    for i, item in enumerate(items):
        bucket = buckets[i % len(buckets)]
        bucket.add(item)
        total_placed += 1
        assert total_placed == i + 1  # running count stays in sync with iteration
        assert bucket.count <= bucket.capacity  # never exceed capacity
```

CrossHair will try to find inputs where either assertion fails on *any* iteration — surfacing bugs like off-by-one errors or capacity overflows that a postcondition on the final sum wouldn't catch.

### Multi-step mutations

When a function performs several state changes in sequence, assertions between steps verify that each step left things in a valid state:

```python
def merge(self, from_food, to_food):
    """
    pre: from_food != to_food
    post: __return__.id == to_food
    """
    target = self.get(to_food)
    source = self.get(from_food)

    for ref in source.references:
        ref.food_id = target.id
        assert ref.food_id == target.id  # reassignment actually stuck

    self.delete(source)
    assert self.get(from_food) is None  # source is gone before we return target
    return target
```

## Guidelines

- **Don't remove existing `assert` statements** — they are checked by CrossHair and may catch bugs that docstring contracts miss.
- **Use assertions for properties that only make sense mid-execution** — if you can state it as a `post:`, prefer that. Use `assert` for things that aren't visible at the function boundary.
- **Loop invariants are the highest-value target** — an assertion inside a loop is checked on every iteration, giving CrossHair many opportunities to find a violation.
- **Keep assertions simple** — same principle as docstring contracts. If it needs a helper function, it's checking too much.
- **Don't duplicate docstring contracts** — if a `post:` already checks a property, don't also assert it at the end of the body.
