# Inventory Overrides

`inventory_stubs.py` auto-detects the stub vocabulary by parsing the stub file. If detection misses entries (e.g. the stubs use a custom factory pattern) or over-detects (e.g. flags a non-stubbed helper class), supply an overrides JSON via `--overrides`.

## Format

```json
{
  "stubbed_models": ["User", "Order", "LineItem"],
  "factory_models": ["Order"],
  "instance_attrs": ["uuid", "created_at", "shipping_address"],
  "plural_hints": {"orders": "Order", "items": "LineItem", "lineitems": "LineItem"},
  "extra_orm_patterns": []
}
```

## Merge semantics

- **Lists** (`stubbed_models`, `factory_models`, `instance_attrs`, `extra_orm_patterns`): union with auto-detected.
- **Dicts** (`plural_hints`): keys in the override replace auto-detected entries.

To *remove* an auto-detected entry, edit the inventory JSON manually after running.

## When to use

| Situation | Override field |
|---|---|
| Stub file uses `@stub_model` decorator instead of `MockManager(...)` | `stubbed_models` |
| Mock instances built via custom dataclass instead of SimpleNamespace | `factory_models`, `instance_attrs` |
| Project has unusual plural forms (e.g. "geese", "alumni") | `plural_hints` |
| Want to track Tortoise/Peewee-style `Model.filter(...)` (no `.objects`) | `extra_orm_patterns` (analyzer support pending) |

## Verification

After running the inventory + analyzer with overrides, check the per-file `orm_call_sites` for a known ORM-dense file. If your favorite manager call still shows up as 0 sites, your override likely needs the model name added to `stubbed_models`.
