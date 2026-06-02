# Symbolic Stubs — The Foundational Rule

This is a meta-pattern that applies to every stub class you write for CrossHair (Django ORM, SQLAlchemy ORM, HTTP requests, file objects, third-party SDK clients, anything). Both the `crosshair-django` and `crosshair-sqlalchemy` skills depend on it.

---

## The rule

**Stub return values must be symbolic (`proxy_for_type(...)`), not concrete.**

A stub that returns concrete values *appears* to work — CrossHair runs your function without crashing — but it silently disables symbolic execution for every code path that branches on the stubbed value. You're not finding bugs anymore; you're testing one specific (and arbitrary) execution.

---

## Worked example

### Wrong — concrete values, hides bugs

```python
class MockUser:
    def __init__(self):
        self.is_authenticated = True   # always True
        self.is_active = True          # always True
        self.id = 1                    # always 1

    def check_password(self, raw):
        return False                   # always False
```

When CrossHair analyzes:

```python
def replace_own(*, old_password, new_password, **kwargs):
    user = kwargs.get(REQUEST_KEY).user
    if not user.check_password(old_password):     # always True with mock
        raise Exception('Old password is incorrect')
    change_password(user.id, new_password)        # never reached
```

Every CrossHair iteration takes the *same path* (raise Exception). The success path (`change_password(user.id, ...)`) is never explored. Bugs in `change_password` that depend on `user.id` are invisible. The entire function looks "covered" but only one of two branches was checked.

### Right — symbolic values, branches explored

```python
from crosshair.core_and_libs import proxy_for_type
from typing import Any

class MockUser:
    def __getattr__(self, name):
        bool_fields = {"is_authenticated", "is_active", "is_staff",
                       "is_superuser", "is_anonymous"}
        int_fields = {"id", "pk"}
        str_fields = {"username", "email", "password"}
        if name in bool_fields:
            return proxy_for_type(bool, f"user_{name}")
        if name in int_fields:
            return proxy_for_type(int, f"user_{name}")
        if name in str_fields:
            return proxy_for_type(str, f"user_{name}")
        if name == "check_password":
            return lambda *a, **kw: proxy_for_type(bool, "user_check_password")
        if name == "set_password":
            def _set(raw):
                # honor mutating writes — see "Honoring writes" below
                object.__setattr__(self, "password", raw)
            return _set
        return proxy_for_type(Any, f"user_{name}")
```

Now `user.check_password(...)` returns `proxy_for_type(bool, ...)` — CrossHair forks both branches at the `if not` and explores `change_password(user.id, new_password)` with a symbolic int `user.id`.

---

## Why concrete-value stubs are tempting (and wrong)

Concrete stubs feel safer because the code "just runs." But CrossHair's value isn't running the code — `pytest` already does that. CrossHair's value is **the symbolic exploration**. Every `if x is None:`, `if not user.is_authenticated:`, `if response.status_code == 200:` is a branch CrossHair only explores when the controlling expression is symbolic.

A common warning sign: your stub has an `__init__` that assigns concrete defaults to many attributes. That's almost always wrong. Use `__getattr__` to return symbolic proxies on demand.

---

## Honoring writes

The above `__getattr__` pattern handles reads. But user code mutates objects too:

```python
self.user.password_change_needed = False
```

You want a postcondition like `post: self.user.password_change_needed == False` to actually pass. The mutation has to be observable.

The trick: `__setattr__` puts the value in the instance's `__dict__`, which Python checks **before** calling `__getattr__`. So after the write, subsequent reads return the written value, while reads of unset attributes still go through `__getattr__` to get fresh symbolic proxies.

Let normal assignment (`self.attr = x`) work — don't override `__setattr__`. The default behavior populates `__dict__`, which is exactly what you want.

For methods that mutate (`set_password`), use `object.__setattr__(self, name, value)` to bypass any custom descriptors:

```python
if name == "set_password":
    def _set(raw):
        object.__setattr__(self, "password", raw)
    return _set
```

This makes reads of `self.password` after `set_password(x)` return `x` (deterministic) while the unmutated `self.username` still produces a fresh symbolic string.

---

## When concrete defaults ARE acceptable

Three cases where a concrete value is fine:

1. **Container shape** — initializing `self.GET = MockQueryDict()` so user code can `request.GET[key]` without an attribute error. The container is concrete; its contents (returned via `proxy_for_type` inside the dict's methods) are symbolic.

2. **Reference identity** — `__return__ is self.user` postconditions need the *same* object back, not a fresh symbolic one. Concrete object identity is the goal here.

3. **Constants the function never branches on** — `request.scheme = "http"` is fine if no caller ever does `if request.scheme == "https":`. But you usually can't know this, so default to symbolic.

When in doubt, return symbolic. The cost of an extra symbolic value is negligible; the cost of missing a branch is invisible.

---

## Self-check

After writing a stub, ask:
- For every attribute the stub exposes, can both `True`/`False` (or 0/non-zero, or empty/non-empty) be observed by CrossHair?
- For every method the stub exposes, can it return any value of its declared return type?
- Do mutating writes flow through to subsequent reads of the same attribute?

If "no" to any of these, the stub is hiding bugs.

---

## When this pattern shows up in the existing skills

- `crosshair-django/plugin-patterns.md` Pattern 5 (ORM stubs) — `MockManager.get()` returns `proxy_for_type(self.model_type, ...)`, not a concrete model instance
- `crosshair-django/plugin-patterns.md` Pattern 5d (FK descriptor `__get__`) — `instance.related_field` returns `proxy_for_type(self.field.related_model, ...)`, not a real `Model.objects.get(pk=...)` query
- `crosshair-sqlalchemy/plugin-patterns.md` Pattern 3 (Engine/Connection/Session stubs) — `MockResult.fetchone()` returns `proxy_for_type(Optional[T], ...)`, not `None` or an empty tuple
- Any future MockRequest, MockSerializer, MockResponse, MockS3Client, etc.

---

## `CrossHairInternal` is a `BaseException`, not `Exception`

Code that wraps CrossHair calls in `try`/`except Exception` will **silently miss `CrossHairInternal`** because it inherits from `BaseException` directly:

```python
class CrossHairInternal(ControlFlowException):  # ControlFlowException → BaseException
    ...
```

If your stub or factory needs a fallback for "CrossHair isn't in a state where this works" (typical example: `proxy_for_type` called outside a statespace context), use `except BaseException`:

```python
def _symbolic_now():
    try:
        return proxy_for_type(datetime, "now")
    except BaseException:                    # NOT `except Exception`
        return datetime(2025, 1, 1, tzinfo=timezone.utc)
```

This shows up most often when:
- A patched function is called at **module-load time** (e.g. `LAST_X = timezone_now()` at import) — there's no statespace, `proxy_for_type` raises `CrossHairInternal: Not in a statespace context`.
- A factory tries to `space.add(...)` from a context where tracing isn't active.

The general rule: when wrapping CrossHair calls for "best-effort fall back to something concrete," reach for `except BaseException`. Plain `except Exception` will let CrossHair internals propagate and crash your factory.

---

## The "concrete vs symbolic type mismatch" trap

CrossHair's `libimpl/*` modules define their own implementations of several stdlib types — `datetime.datetime`, `datetime.timedelta`, `datetime.timezone`, `decimal.Decimal`, etc. These classes set `__module__ = "datetime"` (or wherever the stdlib type lives) so they *look* like the real builtins, but they're separate Python types. CrossHair `register_patch`-replaces user-code calls to constructors like `timedelta(...)` so they return its symbolic instance.

This creates a non-obvious failure mode for stub-side patches: **if your patch returns a real concrete stdlib instance, it can't interoperate with CrossHair's symbolic instance of the "same" type.**

Concrete example. The naive way to make `timezone_now()` deterministic is:

```python
fixed = datetime(2025, 1, 1, tzinfo=timezone.utc)
django.utils.timezone.now = lambda: fixed              # ❌ concrete
```

User code then does `timezone_now() - timedelta(days=N)`. The `timedelta(...)` call is `register_patch`-replaced and returns CrossHair's symbolic timedelta. Python's `datetime.__sub__` slot wrapper does `isinstance(other, datetime.timedelta)`, sees CrossHair's lookalike, returns NotImplemented, and the operation raises:

```
TypeError: unsupported operand type(s) for -: 'datetime.datetime' and 'timedelta'
```

The fix is to return a CrossHair-symbolic value via `proxy_for_type`, not a concrete one:

```python
def _symbolic_now(*a, **kw):
    return proxy_for_type(datetime, '_tz_now')         # ✅ both sides symbolic
```

Now `concrete_dt - symbolic_td` becomes `symbolic_dt - symbolic_td`, both CrossHair types, slot wrappers find each other, and arithmetic works.

### When to apply this

- Any patch that returns a stdlib type CrossHair models in `libimpl/`. Check by importing `crosshair.libimpl.<typename>lib`; if the type is defined there, you're in this trap.
- Any factory that produces values *for use by* user code that then operates on them with stdlib operators.

### When concrete is actually fine

- Values that are only **read** by user code (attribute access, comparison to constants), never used as operands of arithmetic/slot-wrapper-dispatched operations.
- The schema-driven default for a model field that's not in an arithmetic hot path. (For example, a `DateTimeField` populated as `datetime(2025, 1, 1, ...)` is fine if user code only does `obj.created_at.year` or `obj.created_at == None`. It breaks the moment user code does `obj.created_at - timedelta(...)`.)

The general rule: when in doubt, return a `proxy_for_type` symbolic value. It always interoperates with other symbolic values; concrete returns are an optimization that occasionally trades for an unfixable type-mismatch error.

---

## Bounded symbolic `__iter__` for stub collections

When stubbing iterable collection types (Django `QuerySet`, SQLAlchemy `Result`, generic `Sequence`-typed stubs), the `__iter__` implementation has three options, each with its own failure mode:

| Implementation | Problem |
|---|---|
| `iter([])` | `list(qs)[0]` always raises `IndexError`; user code paths that handle a non-empty result are unreachable |
| `proxy_for_type(List[T])` (unbounded) | CrossHair tries lengths 0, 1, 2, 3, …; loop-heavy code times out before completing analysis |
| `proxy_for_type(List[T])` with `space.add(len(items) <= N)` | Bounded exploration of empty / single / multiple cases without explosion |

The bounded form is almost always what you want. `N=2` or `N=3` is enough to exercise the empty / one / many surface; larger N rarely surfaces new bugs and increases analysis cost quadratically.

Implementation pattern:

```python
def __iter__(self):
    try:
        items = proxy_for_type(List[self.model_type], 'qs_iter')
        try:
            from crosshair.statespace import context_statespace
            space = context_statespace()
            with ResumedTracing():                     # ← required
                if isinstance(len(items) <= 2, bool):
                    pass
                else:
                    space.add(len(items) <= 2)
        except Exception:
            pass
    except Exception:
        items = []
    for item in items:
        yield _apply_constraints(item, self.model_type)
```

The `with ResumedTracing()` is required because `__iter__` itself is often called outside a traced region (during `gen_args`, in `len(items)` for path-count bookkeeping, etc.). Without it, `space.add(...)` raises `CrossHairInternal: Numeric operation on symbolic while not tracing`.

This pattern generalizes to any "symbolic-length collection" stub — it's not Django-specific.

---

## The `ResumedTracing` rule for `register_type` factories

Stubs that implement methods called from user code (`MockManager.get`, `MockResult.fetchone`) run while CrossHair is tracing — `proxy_for_type(...)` and `space.add(...)` work directly.

**A factory registered with `crosshair.register_type(MyType, factory)` is different.** It runs during `gen_args`, which executes with tracing **paused**. Calling `space.add(symbolic_expr)` from that context crashes with:

```
crosshair.util.CrossHairInternal: Numeric operation on symbolic while not tracing
```

If your factory needs to apply SMT constraints (e.g., bounding `len(symbolic_str) <= max_length`), wrap them in `with ResumedTracing()`:

```python
from crosshair import ResumedTracing, register_type
from crosshair.statespace import context_statespace
from crosshair.core_and_libs import proxy_for_type


def _my_type_factory(factory):
    val = factory(str, "field")
    space = context_statespace()
    with ResumedTracing():
        space.add(len(val) <= 50)
    return MyType(val)


register_type(MyType, _my_type_factory)
```

Calling `proxy_for_type(...)` itself works inside the factory without `ResumedTracing` (it knows how to handle paused-tracing). Only the `space.add(...)` SMT calls need the wrapper.

---

## Common gotchas writing stubs

### `context_statespace()` raises outside a state space

Stub code often needs to know whether CrossHair is actively tracing — e.g., to decide between symbolic and concrete defaults in a `Model.__init__` patch. The intuitive `space = context_statespace(); if space is None:` doesn't work — `context_statespace()` raises `CrossHairInternal("Not in a statespace context")` (a `BaseException`, not `Exception`) outside a statespace. The correct guard:

```python
try:
    space = context_statespace()
    is_tracing = space is not None
except BaseException:
    is_tracing = False
```

Bare `except:` or `except BaseException:` is required — `except Exception:` lets `CrossHairInternal` through and the stub crashes at import time.

### `space.add(<concrete bool>)` crashes

`space.add(True)` and `space.add(False)` both raise `CrossHairInternal("Attempted to assert a concrete boolean (look for unexpected realization)")`. This bites constraint-application loops:

```python
# Wrong — the constraint lambda may return a concrete True/False if the
# subject's relevant fields happen to be concrete
for constraint_fn in constraints:
    space.add(constraint_fn(result))   # crashes
```

Guard the call by skipping concrete results — `True` is already satisfied, `False` would just prune the path (use `space.add(False)` directly only if that's actually what you want):

```python
for constraint_fn in constraints:
    try:
        cond = constraint_fn(result)
        if cond is True or cond is False:
            continue
        space.add(cond)
    except BaseException:
        pass
```

The `except BaseException` is again required because `CrossHairInternal` is a `BaseException`.

### Pydantic `model_validate` on symbolic ORM instances raises `ValidationError`

Common false positive: a repo/service method ending in `return Schema.model_validate(orm_instance)` reports a `ValidationError` counterexample. Cause: CrossHair-symbolic field values flow into Pydantic, which catches mismatches (`EmailStr` rejects unrecognized strings, `UUID4` rejects ints, `min_length` validators reject too-short strings).

These are stub artifacts, not bugs. The symbolic ORM instance has fields too loose for the Pydantic schema. Either:
- Constrain the symbolic field values in the stub's `mock_model_init` to satisfy the schema (`_max_len`, `_in_values` etc.), or
- Accept the finding and move on — it's a known stub limitation, not a production bug.

Recognize the pattern: any `error: ValidationError: <N> validation errors for <SchemaName>` from a function that calls `schema.model_validate(...)` on ORM-sourced data is in this category.
