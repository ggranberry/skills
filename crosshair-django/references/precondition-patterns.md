# Django/DRF Precondition Patterns

Patterns for writing `pre:` conditions in Django and DRF code that avoid symbolic noise false positives. Planner agents in Phase 6 must apply these alongside the PEP 316 guide.

---

## Django/DRF Type Guards — `isinstance`/`hasattr` Pattern Table

CrossHair cannot symbolically construct Django ORM objects (they require a live database and app registry). Use `hasattr` duck-typing guards instead of type-name checks, which are fragile across proxy models and subclasses.

| Argument type | Safe `pre:` guard | Notes |
|---------------|-------------------|-------|
| Django model instance | `pre: hasattr(x, '_meta')` | `_meta` is present on all `Model` subclasses; absent on dicts, None, plain objects |
| Django queryset | `pre: hasattr(qs, 'filter') and hasattr(qs, 'model')` | Distinguishes from lists; both attrs required |
| Python dict (not model) | `pre: isinstance(x, dict)` | Use when function accepts dict OR model — guards the dict branch |
| SQL compiler | `pre: hasattr(compiler, 'compile')` | `SQLCompiler.compile` is the entry point; absent on plain objects |
| Django request | `pre: hasattr(request, 'META')` | `META` is always set on `HttpRequest`; absent on faked objects |
| DRF view instance | `pre: hasattr(view, 'allowed_methods')` | Set by `APIView.__init__`; absent on plain callables |
| DRF serializer field | `pre: hasattr(field, 'label')` | `Field.label` is set during `bind()`; absent on plain objects |
| DRF serializer | `pre: hasattr(serializer, 'validated_data')` | Present after `is_valid()` — use only when validating post-validation behavior |
| Django template context | `pre: isinstance(context, dict)` | `Context` objects are dict-like; plain dict is also valid |
| Django form | `pre: hasattr(form, 'cleaned_data')` | Present after `is_valid()`; use only for post-validation functions |

**Rule of thumb:** Prefer `hasattr` over `isinstance(x, SomeModel)` because CrossHair cannot import and instantiate model classes. `hasattr` checks work on any symbolic object.

---

## `isdecimal()` vs `isdigit()` — Unicode Digit False Positives

**Never use `isdigit()` as a `pre:` guard when you intend to call `int()` afterward.**

`str.isdigit()` returns `True` for characters that are not valid Python integer literals:
- Superscript digits: `'²'`, `'³'`, `'⁴'` (Unicode category `No`)
- Circled digits: `'①'`, `'②'` (Unicode category `No`)
- Fullwidth digits: `'２'` (works with `int()` — OK)

CrossHair's symbolic string engine generates these Unicode strings. A function guarded by `pre: s.isdigit()` but then calling `int(s)` will raise `ValueError` on the superscript inputs, producing a false counterexample.

**Correct guard:**

```python
pre: s.isdecimal()
# or
pre: s.isdecimal() and s.isascii()  # stricter: ASCII decimal digits only
```

`str.isdecimal()` returns `True` only for characters that `int()` will accept. Use it whenever the function calls `int(s)` or `float(s)`.

**Equivalently for length checks:**

```python
# Bad: s.isdigit() allows superscript '²²²' which has len 3 but int() fails
# Good:
pre: s.isdecimal() and len(s) <= 10
```

---

## String `post:` Length Pitfalls

**Do NOT assert `len(__return__) == len(value)` for string transformation functions.**

Unicode case mapping is not length-preserving:
- `'ß'.upper()` → `'SS'` (1 character → 2 characters)
- `'ﬁ'.upper()` → `'FI'` (ligature → 2 characters)
- `'DŽ'.lower()` → `'dž'` (same length, but not universal)

CrossHair generates Unicode strings. A `post:` like `post: len(__return__) == len(value)` will produce a false counterexample for `upper()`, `lower()`, `title()`, or any case-folding operation.

**Safe alternatives:**

```python
# Instead of: post: len(__return__) == len(value)
# Use: post: len(__return__) >= len(value)   # only if you know upper expands
# Or:  post: isinstance(__return__, str)      # just assert it's a string
# Or:  post: __return__.lower() == value.lower()  # round-trip equivalence
```

**Affected operations:** `str.upper()`, `str.lower()`, `str.title()`, `str.casefold()`, `str.swapcase()`.

---

## Django Signal / AppRegistry Guards

Functions that call `django.apps.apps.get_model()` or access the app registry at call time will raise `AppRegistryNotReady` if CrossHair analyzes them before `django.setup()` runs.

The `crosshair_django_setup.py` plugin (see `preflight.md`) handles the top-level setup. However, if a function accepts a model class as an argument and the planner wants to write a `pre:` for it:

```python
# Avoid:
pre: isinstance(model_class, type)  # too broad — accepts any class

# Prefer:
pre: hasattr(model_class, '_meta') or (isinstance(model_class, type) and hasattr(model_class, '_default_manager'))
```

---

## `hasattr` Preconditions on Untyped Args — Silent Analysis Death

**`hasattr(user, 'is_superuser')` (or any `hasattr` precondition) on a parameter without a type annotation will silently kill analysis.**

When a parameter has no type annotation, CrossHair generates symbolic values by trying primitive types first (`int`, `str`, etc.). None of those have `.is_superuser`, so the `hasattr` precondition fails for every iteration. CrossHair reports the function as "clean" but it never actually ran the body. `post: False` also returns clean — definitive symptom.

**Diagnosis** (verbose run):

```
attempt_call() Failed to meet precondition hasattr(user, 'is_superuser')
analyze_calltree() Iter complete. Worst status found so far: UNKNOWN
```

**Fix:** Add the type annotation so CrossHair generates the right kind of mock:

```python
# Before — silently fails:
def f(user, ...):
    """
    pre: hasattr(user, 'is_superuser')
    """

# After — CrossHair uses the ORM stub's User mock:
def f(user: User, ...):
    """
    pre: hasattr(user, 'is_superuser')
    """
```

**Caveat:** for `AbstractUser`-derived `User` (Django auth), the proxy construction itself is intractable. See **`crosshair-django/references/plugin-patterns.md` Pattern 5g** for `register_type`/`SimpleNamespace` workarounds.

**Verifying analysis is reaching the body:** temporarily insert `post: False`. A reachable function ALWAYS surfaces a counterexample for `post: False`. If it doesn't, your preconditions or proxy construction are silently aborting before the body.

---

## Summary: Quick Reference

| Pattern | Use |
|---------|-----|
| `hasattr(x, '_meta')` | Guard for Django model instances |
| `hasattr(qs, 'filter') and hasattr(qs, 'model')` | Guard for Django querysets |
| `hasattr(request, 'META')` | Guard for Django HttpRequest |
| `hasattr(view, 'allowed_methods')` | Guard for DRF APIView instances |
| `hasattr(field, 'label')` | Guard for DRF Field instances |
| `hasattr(compiler, 'compile')` | Guard for Django SQL compiler |
| `s.isdecimal()` not `s.isdigit()` | Before calling `int(s)` or `float(s)` |
| Avoid `len(__return__) == len(value)` | After `str.upper()` / `str.lower()` |
| Annotate args before using `hasattr(...)` pre: | Untyped + `hasattr` → silent analysis death |
| `post: False` as reachability probe | A reachable body ALWAYS surfaces a CE for `post: False` |
