# Phase 5: Symbolic Model / Form / UUID Construction

The auto-generated `_crosshair_stubs.py` from Phase 2/4 handles
*manager-side* access (`Model.objects.get(...)`, `.filter(...)`,
`.first()` etc.) by returning `proxy_for_type` results with the schema
constraint registry applied. That covers code that reads from the
ORM via the manager.

It does **not** cover *direct construction* of model / form / UUID
instances, or methods that take such instances as parameters. That's
what this phase adds — woven into the same
`crosshair_django_setup.py` plugin.

## Why direct-construction matters

Most contracted methods take `self` (the instance) or a related model
as a parameter. CrossHair generates these by calling the class's real
`__init__` with symbolic field values. Three failure modes follow,
each one resulting in either `CrosshairUnsupported` or
"Skipping <fn> because it has no conditions":

1. **Descriptor `__set__` runs outside CrossHair's tracing region.**
   Django's `Model.__init__` ends each kwarg with
   `setattr(self, field.attname, val)`, which routes through related-
   field descriptors. The descriptors do `cached != value` on the
   symbolic int CrossHair passed — a comparison that runs in
   not-traced code and trips:
   ```
   CrossHairInternal: Numeric operation on symbolic while not tracing
   ```
   `uuid.UUID.__init__` has the same shape: it does `if int >> 128:`
   on the symbolic int.

2. **`forms.Field.__init__` iterates symbolic kwargs.** It does
   `error_messages.items()` and `copy.deepcopy(widget)` on
   parameters CrossHair passes as opaque symbolic objects, raising
   `CrosshairUnsupported`.

3. **`forms.BaseForm.__init__` populates `self.fields` and `cleaned_data` lazily.** `clean_X(self)` methods read
   `self.cleaned_data["X"]` on the first line; without pre-populated
   symbolic values, every method KeyErrors before reaching the
   contract.

## The fix in three layers

(All baked into the template; this section explains *why* each piece
is shaped the way it is.)

### Layer A: `Model.__init__` bypass + symbolic field values

Replace `Model.__init__` with one that:

1. Writes values straight into `self.__dict__`, bypassing the
   descriptor chain. (`DeferredAttribute.__get__` reads from
   `instance.__dict__` directly — no DB query needed when the slot
   is already populated.)
2. When CrossHair is tracing, calls `proxy_for_type(<py_type>,
   varname)` for the field's mapped Python type instead of using
   concrete defaults. **This is the most important piece.** Without
   it, every `self.<charfield>` reads as `""` and contracts like
   `pre: "|" in self.channel.value` are unsatisfiable.
3. After populating the dict, calls `_apply_constraints` (from the
   manager-side stubs) so the symbolic values inherit the schema
   constraints (`max_length`, `choices`, etc.).

The `_DJANGO_FIELD_TO_PY` map covers every Django field type that
maps to a CrossHair-proxyable Python primitive. Relations / generated
columns / JSON / file-blob fields fall through to the concrete-empty
default appropriate for the field (i.e. `""` if
`empty_strings_allowed`, else `None`).

### Layer B: ForeignKey descriptor proxy via `_state.fields_cache`

`ForwardManyToOneDescriptor.__get__` reads
`instance._state.fields_cache[field.cache_name]` *before* falling
through to a DB query. Pre-populating that cache with a fresh
related-model instance (which itself goes through our patched
`Model.__init__`, so its fields are symbolic) makes `flip.owner`
return a usable symbolic Check.

A `threading.local`-backed depth counter guards against infinite
recursion on cyclic schemas (Profile → Project → User → Profile →
…). Only the *top-level* construction proxies its FKs; nested
constructions get default-populated unpatched instances.

### Layer C: Form `__init__` patches

- `forms.Field.__init__` → minimal init that sets every attribute
  subclasses read (`self.validators`, `self.error_messages`,
  `self.widget`), walking `__class__.__mro__` to populate
  `default_error_messages` so e.g.
  `ValidationError(code="required")` doesn't `KeyError` at lookup.
  Widget is a `types.SimpleNamespace` so `ChoiceField`'s
  `self.widget.choices = ...` doesn't crash.
- `BaseForm.__init__` → minimal init that pre-populates
  `self.cleaned_data` with one `proxy_for_type` value per declared
  field, using `_FORM_FIELD_TO_PY` to map form field type →
  Python type. Walks `type(self).base_fields` (set on the class by
  `DeclarativeFieldsMetaclass`) — works for any Form subclass with
  no per-form configuration.

## The exec-scope closure gotcha

CrossHair `exec()`s the plugin file inside `main()` without a custom
namespace, so the file's locals are torn down after exec returns.
The Phase 2 docs warn about this for *class bodies* — the `_RegistryStubAppConfig` workaround puts stub classes in a real
importable module (`_crosshair_registry_patch.py`) so name resolution
still works at call time.

**The same caveat applies to function bodies.** A function defined
in the plugin that closes over an exec-local name (e.g.
`_orig_get_type_hints`) appears to work, but at call time the closure
cell is dead and you get a confusing `NameError` from inside the
patched function — surfacing as "Skipping <fn> because it has no
conditions" or similar.

Two reliable mitigations:

1. **Re-import inside the function body.** This is what every
   `__init__` patch in the template does:
   ```python
   def _patched_model_init(self, *args, **kwargs):
       from django.db.models.base import ModelState  # re-import here
       self.__dict__["_state"] = ModelState()
       ...
   ```

2. **Bind cross-frame references via default args.** This is what
   `_patched_get_type_hints` does:
   ```python
   def _patched_get_type_hints(
       obj, globalns=None, localns=None, include_extras=False,
       _typealias_globals=_typealias_globals,    # ← captured at def time
       _orig_get_type_hints=_orig_get_type_hints,
   ):
       ...
   ```
   Default args evaluate at function-definition time (while the
   exec scope is still live) and are bound onto the function object
   itself — they survive scope teardown.

If you're adding a new patch and seeing `NameError` on something
that's clearly defined at module level, this is almost certainly
why.

## Recursive type-alias forward references

Projects often define a recursive JSON-shape type alias:

```python
# typealias.py
JSONDict = dict[str, "JSONValue"]
JSONList = list["JSONValue"]
JSONValue = JSONDict | JSONList | str | int | float | bool | None
```

Modules that import only `JSONDict` don't have `JSONValue` in their
`__globals__`, so `typing.get_type_hints(fn, fn_globals(fn))` —
which CrossHair's `resolve_signature` calls — raises `NameError`
on the forward reference. CrossHair drops the entire signature and
silently skips the function.

Layer 4 of the template wraps `typing.get_type_hints` to merge the
typealias module's namespace into `globalns` before resolution.
Important: rebind on `crosshair.fnutil` too — that module captures
`get_type_hints` at import time:

```python
import crosshair.fnutil as _ch_fnutil
_ch_fnutil.get_type_hints = _patched_get_type_hints
```

The template parameter `{{ typealias_module }}` should be set to the
project's typealias module (e.g. `hc.lib.typealias`,
`myapp.types`, `core.json_types`). If the project doesn't have such
a module, leave the parameter empty — the wrapping block is wrapped
in `{% if typealias_module %}` and is a no-op when not set.

## When this isn't enough

Even with all three layers, some functions stay UNKNOWN:

- **HTTP-I/O functions** — anything calling `pycurl`, `requests`,
  `socket`. CrossHair can't symbolically execute through real I/O.
  Permanent skip; document with a comment.
- **Heavy template / JSON-Schema validation** — Pydantic
  `model_validate_json`, Django template rendering. CrossHair
  explores hundreds of paths but rarely CONFIRMs in 10s. Either
  raise the timeout (`--per_condition_timeout 30+`) or accept
  UNKNOWN as "no contract violation found within budget."
- **Rich symbolic types CrossHair lacks built-in support for** —
  `decimal.Decimal`, complex `pydantic.BaseModel` subclasses with
  custom validators, etc. Workaround: contract a wrapper that takes
  primitives.

## Generation

When the `/generate-stubs` skill runs Phase 2 for a Django project,
also:

1. Detect the project's recursive type alias module if any
   (heuristic: a top-level `.py` with `JSON*` aliases or
   similar). Pass as `typealias_module` to the template.
2. Render the full template (including all four layers).
3. The resulting `crosshair_django_setup.py` is the only file the
   user passes to `crosshair --extra_plugin`. The
   `_crosshair_registry_patch.py` and `_crosshair_stubs.py`
   companions are imported automatically.
