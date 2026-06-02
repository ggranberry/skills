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
- **`async def` functions** — CrossHair simply does not analyze
  async functions. They produce
  `WARNING: Targets found, but contain no checkable functions.`
  This is structural: FastAPI / Starlette projects with
  `async def` route handlers, `async def` dependency-injection
  functions, etc. are effectively unanalyzable as written.
  For an async-heavy codebase, the realistic CrossHair surface
  shrinks to the sync repository / service / parser / sanitizer
  layer underneath the routes. Note this in the run script's
  comment so reviewers don't get confused.

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

---

## Alternative: `register_type` factories

Layer A patches `Model.__init__` so any user-code call to `User(...)`
gets symbolic fields. There's a complementary approach: register a
custom factory with `crosshair.register_type` so CrossHair uses it
when synthesizing a function *argument* of the model type.

Both can coexist, but the registration approach is more surgical —
it intervenes only at the boundary where CrossHair generates args
for the function under analysis, leaving real `Model(...)` calls in
the function body untouched. This was added to one project (Zulip)
in 2026-05 and unblocked ~33 action files + ~65 view files whose
signatures took `UserProfile`, `Realm`, `Stream`, etc.

### Sketch

```python
from crosshair import register_type, ResumedTracing
from crosshair.core_and_libs import proxy_for_type

def _make_symbolic_model(model_class, factory):
    from django.db.models.base import ModelState
    instance = model_class.__new__(model_class)              # bypass __init__
    instance.__dict__["_state"] = ModelState()
    instance._state.adding = False
    instance._state.db = "default"
    for col, info in _load_constraints()[key].items():
        ftype = info["type"]
        if ftype in ("ForeignKey", "OneToOneField"):
            # Set symbolic FK id; let the patched FK descriptor
            # synthesize the related object lazily on first access
            # to avoid infinite recursion in cyclic schemas.
            instance.__dict__[col] = factory(int, col)
        elif ftype in CHARFIELD_TYPES:
            val = factory(str, col)
            with ResumedTracing():                             # ← critical
                if "max_length" in info:
                    space.add(len(val) <= info["max_length"])
            instance.__dict__[col] = val
        # ... int / bool / autofield branches

def _register_symbolic_models():
    import importlib
    for key in _load_constraints():
        module_name, _, class_name = key.rpartition(".")
        try:
            model = getattr(importlib.import_module(module_name), class_name)
        except (ImportError, AttributeError):
            continue
        # Default-arg `m=model` is required: closure-by-reference
        # would make every lambda see the LAST model in the loop.
        register_type(model, lambda factory, m=model: _make_symbolic_model(m, factory))
```

### Two gotchas not present in the `_patched_model_init` path

#### 1. `with ResumedTracing()` around `space.add(...)`

A `register_type` factory runs during `gen_args`, which executes with
tracing **paused** (`COMPOSITE_TRACER` is off). Calling
`context_statespace().add(symbolic_expr)` from that context crashes:

```
crosshair.util.CrossHairInternal: Numeric operation on symbolic while not tracing
```

Wrap any constraint application in `with ResumedTracing()`:

```python
from crosshair import ResumedTracing
with ResumedTracing():
    space.add(len(val) <= max_length)
```

The Layer A `_patched_model_init` doesn't need this because user-code
`Model(...)` calls happen inside the traced function body — tracing
is already on.

#### 2. FK descriptor `__get__` patch must use `field.name`, not `get_cache_name()`

The Layer B description in this doc references `field.cache_name` but
in newer Django versions `FieldCacheMixin.get_cache_name()` raises
`NotImplementedError` on the abstract base, and what gets resolved
depends on the concrete field class hierarchy. The simple,
version-stable cache key is `self.field.name`:

```python
def _fk_descriptor_get(self, instance, cls=None):
    if instance is None:
        return self
    cache_name = self.field.name                              # not get_cache_name()
    cache = instance._state.fields_cache
    if cache_name in cache:
        return cache[cache_name]
    related = proxy_for_type(self.field.related_model, f"_fk_{cache_name}")
    cache[cache_name] = related
    return related
```

Patch it on **both** `ForwardManyToOneDescriptor.__get__` (regular
ForeignKey) and `ForwardOneToOneDescriptor.__get__` (OneToOneField).
Patching just the setter (`ForeignKeyDeferredAttribute.__set__`) is
not enough — reads route through the descriptor's `__get__`, which
on cache miss issues a real DB query.

### When to prefer this over Layer A

- Code under analysis treats model arguments as opaque (passes them
  along, reads a few fields). The factory's symbolic fields suffice.
- You want to leave `Model.__init__` semantics intact for any
  *internal* construction CrossHair encounters.
- The schema is cyclic and you don't want to manage a depth counter
  — `register_type` produces a fresh proxy per gen_args call, and
  FKs only resolve on access via the descriptor patch.

### When to prefer Layer A (`_patched_model_init`)

- Code under analysis constructs models internally via
  `Model(field=val, ...)` and the construction itself needs to
  produce a symbolic instance.
- You need symbolic Form / BaseForm support (Layer C builds on
  Layer A's init-patch infrastructure).

---

## Pre-resolving generic type parameters at install time

A common shape for application-layer wrappers around the ORM:

```python
class RepositoryGeneric[Schema: BaseModel, Model: SqlAlchemyBase]:
    def __init__(self, session, primary_key, sql_model: type[Model],
                 schema: type[Schema]) -> None: ...

class RepositoryUsers(GroupRepositoryGeneric[PrivateUser, User]):
    ...
```

When stubbing the constructor of such a class, the no-op `__init__`
needs to bind `self.model` and `self.schema` to *concrete* classes
(they're later used in `select(self.model)` and
`self.schema.model_validate(...)` — neither survives a symbolic
proxy). Don't ask CrossHair to generate symbolic types — instead
pre-resolve them from each subclass's generic base.

```python
from typing import get_args

repo_generics: dict[type, tuple[type, type]] = {}

for cls in _all_subclasses(RepositoryGeneric):
    for base in getattr(cls, '__orig_bases__', ()):
        try:
            args = get_args(base)
        except Exception:
            continue
        if (len(args) >= 2
                and isinstance(args[0], type)
                and isinstance(args[1], type)):
            repo_generics[cls] = (args[0], args[1])
            break

# Later, in the patched __init__:
def _repo_init(self, *args, **kwargs):
    ...
    sg = repo_generics.get(type(self))
    if sg is not None:
        schema_cls, model_cls = sg
        object.__setattr__(self, 'schema', schema_cls)
        object.__setattr__(self, 'model', model_cls)
    ...
```

The same pre-resolution applies to any `Generic[T, U]` subclass
where the concrete types are required at runtime. This pattern
keeps the patched `__init__` lightweight (one dict lookup) instead
of doing `get_args(__orig_bases__[0])` every construction.

Caveat: `__orig_bases__` is only populated on classes that
*directly* parameterize a `Generic` (or PEP 695 generic) base.
Subclasses that inherit from already-parameterized bases get the
empty `()`. Walk the MRO if the project has deeper hierarchies.
