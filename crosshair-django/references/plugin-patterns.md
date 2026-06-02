# CrossHair Plugin Patterns for Django

Patterns specific to the `crosshair_django_setup.py` plugin file. Together with the cross-cutting CrossHair workarounds, these solve real failures discovered across NetBox, Mathesar, and similar Django projects.

If your `crosshair check` invocation fails with `AppRegistryNotReady`, `ImproperlyConfigured`, allauth's `SOCIALACCOUNT_ENABLED` errors, or settings-load file writes — work through this file first.

For native-driver issues (psycopg2, cairocffi, cryptography → ldconfig/dlopen) and SQLAlchemy-specific failures, read **`crosshair-sqlalchemy/references/plugin-patterns.md`**. The patterns there apply to any Django project that also touches SQLAlchemy or has CFFI-bound dependencies (cairocffi for SVG/PDF generation, etc.).

---

## Pattern 0: Set `TEST=True` env var to disable background-thread decorators

Many Django projects gate "fire-and-forget" background work behind `settings.TEST`:

```python
def maintain_models(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if settings.TEST is False and cache.add(MAINTENANCE_DONE, True, CACHE_TIMEOUT):
            threading.Thread(target=run_model_maintenance).start()
        return f(*args, **kwargs)
    return wrapped
```

If `TEST` isn't set during analysis, the wrapped function spawns a background thread that runs **outside** CrossHair's per-thread state space. The thread's first MockManager method call crashes with:

```
AttributeError: '_thread._local' object has no attribute 'space'
```

…and the harness output explodes with megabytes of stack traces while the foreground analysis silently stalls.

**Fix.** At the top of `crosshair_django_setup.py`, before `DJANGO_SETTINGS_MODULE` is imported:

```python
import os
os.environ.setdefault("TEST", "True")
```

Most projects ship a `settings.TEST = bool(os.environ.get('TEST', default=False))` declaration that responds to this env var. Check the project's settings file once to confirm the shape; if `TEST` isn't a recognized flag, look for an equivalent (`CI`, `IS_RUNNING_TESTS`, etc.) or directly disable the `wire_*` / `maintain_*` decorators in the plugin.

**Also affects.** `wire_analytics`, `run_model_maintenance`, and any other `@wraps`-style decorator chain that fires background work. The mathesar RPC layer wraps every endpoint in this combo, so without `TEST=True` you can't analyze any decorated endpoint cleanly.

---

## Pattern 1: SECRET_KEY env var to skip auto-generation side effects

**Problem.** Some Django projects auto-generate a secret key on first run if `SECRET_KEY` env var is unset:

```python
# typical settings.py pattern
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    os.makedirs(SECRETS_ROOT, exist_ok=True)        # auditwall: os.mkdir
    with open(SECRET_KEY_FILE, 'x') as f:           # auditwall: open(... 'x')
        f.write(get_random_secret_key())
```

Both `os.makedirs` and `open(... 'x')` trip auditwall during settings load.

**Fix.** Set a fixed value in the plugin before any Django imports:

```python
import os
os.environ.setdefault("SECRET_KEY", "crosshair-fixed-secret-not-for-production")
```

Generic for any Django project that has the auto-generate-secret pattern (NetBox, Mathesar, Saleor, etc.).

---

## Pattern 2: `apps.is_installed()` allow-list for feature-flag apps

**Problem.** Many third-party Django apps use `apps.is_installed("foo")` as a feature flag during model imports:

```python
# allauth/app_settings.py
@property
def SOCIALACCOUNT_ENABLED(self):
    return apps.is_installed("allauth.socialaccount")

# allauth/socialaccount/models.py — module level
if not allauth_settings.SOCIALACCOUNT_ENABLED:
    raise ImproperlyConfigured("not installed, yet its models are imported.")
```

If you skip a full `django.setup()` (to avoid loading the world), `is_installed` returns False for everything → ImproperlyConfigured during model imports.

**Fix.** Patch the `Apps` class to lie about specific apps:

```python
from django.apps import apps as _apps

_INSTALLED_APP_LIES = frozenset({
    "allauth.account",
    "allauth.socialaccount",
    "allauth.mfa",
    "allauth.usersessions",
    "allauth.headless",
    "django.contrib.sites",
    "django.contrib.contenttypes",
    "django.contrib.auth",
})

def _patched_is_installed(self, app_name, _Lies=_INSTALLED_APP_LIES):
    self.check_apps_ready()
    if any(ac.name == app_name for ac in self.app_configs.values()):
        return True
    return app_name in _Lies

# Patch the class so all Apps instances (including the global) use it
_apps.__class__.is_installed = _patched_is_installed
```

**Class-level vs instance-level patching:** Patching `_apps.is_installed = ...` only affects the singleton. If any code does `from django.apps import apps; apps2 = type(apps)()`, the new instance has the original method. Patch the class instead.

Add to the allow-list whichever apps trigger ImproperlyConfigured in your import chain. Each error tells you the missing app name.

---

## Pattern 3: Stub `apps.get_containing_app_config` and `get_app_config`

**Problem.** Django models call `apps.get_containing_app_config(module)` during class creation. If the model's module isn't in `INSTALLED_APPS`, this returns None and Django's `ModelBase.__new__` raises.

**Fix.** Patch with a stub that returns a synthetic AppConfig:

```python
from _crosshair_registry_patch import _RegistryStubAppConfig  # see Pattern 4

def _patched_get_containing_app_config(self, object_name, _Stub=_RegistryStubAppConfig):
    self.check_apps_ready()
    for app_config in self.app_configs.values():
        if object_name.startswith(app_config.name):
            subpath = object_name.removeprefix(app_config.name)
            if subpath == "" or subpath[0] == ".":
                return app_config
    parts = object_name.split(".")
    label = parts[-2] if len(parts) >= 2 else parts[0]
    name = ".".join(parts[:-1]) if len(parts) >= 2 else parts[0]
    return _Stub(label, name)


def _patched_get_app_config(self, app_label, _Stub=_RegistryStubAppConfig):
    self.check_apps_ready()
    try:
        return self.app_configs[app_label]
    except KeyError:
        return _Stub(app_label)


_apps.__class__.get_containing_app_config = _patched_get_containing_app_config
_apps.__class__.get_app_config = _patched_get_app_config

# Mark registry as ready
_apps.apps_ready = True
_apps.models_ready = True
_apps.ready = True
```

The `_RegistryStubAppConfig` class lives in a separate `_crosshair_registry_patch.py` module — see Pattern 4 for why.

---

## Pattern 4: exec scope gotcha — keep stubs in importable modules

**Problem.** CrossHair runs the plugin via `exec(Path(plugin).read_text())`, which is buggy with class bodies:

```python
# In crosshair_django_setup.py
class _RegistryStub:
    def __init__(self):
        ...

def _use_stub(_Stub=_RegistryStub):  # captures correctly via default
    return _Stub()

class _UseStubBad:
    def __init__(self):
        return _RegistryStub()  # NameError under exec!
```

Class bodies in `exec`'d code cannot see other names defined in the same exec scope.

**Fix.** Put all class definitions in a sibling `_crosshair_registry_patch.py` module and `from _crosshair_registry_patch import ...` at the top of the plugin. Same for ORM stubs (`_crosshair_stubs.py`).

Also: if a function inside the plugin needs to reference module-level names, capture them via default argument values (`def foo(x, _Helper=_Helper):`), not by closure.

This is a CrossHair plugin gotcha, not Django-specific — but Django plugins tend to have the most class definitions, so it bites here first.

---

## Pattern 5: ORM stub auto-loading via `importlib.import_module`

**Problem.** If you put ORM stubs in `_crosshair_stubs.py` and try to `import _crosshair_stubs` at the top of the plugin, the import works but the stubs install in a frame namespace that gets discarded after exec returns. Subsequent CrossHair calls don't see the stubs.

**Fix.** Load stubs via `importlib.import_module` (which installs the module in `sys.modules` permanently) and let module-level side effects do the patching:

```python
# crosshair_django_setup.py — at the very end, after registry patches
import importlib
importlib.import_module("_crosshair_stubs")
```

```python
# _crosshair_stubs.py
def install_stubs():
    from mathesar.models.base import Server
    Server.objects = MockManager(Server)
    # ... etc

install_stubs()  # runs at module import
```

The stubs survive because `sys.modules["_crosshair_stubs"]` keeps a reference; the patches on Django model classes persist for the rest of the CrossHair process.

---

## Pattern 5b: `django.core.cache.cache` no-op stub (defeats `NotDeterministic`)

**Problem.** Many Django decorators use the cache for rate limiting, throttling, or memoization:

```python
# typical pattern
@mathesar_rpc_method(name="users.add")
def add(*, user_def):
    cache.set(f"user:{user_def['username']}:lock", time.time(), timeout=10)
    if cache.get(f"rate:{user_def['username']}") > 10:
        raise RateLimitExceeded()
    ...
```

CrossHair sees `cache.get()` as a non-deterministic side effect: across iterations of symbolic execution, the cache returns different values for the same SMT decisions. This trips `NotDeterministic: Found a different execution paths after making the same decisions` and aborts analysis of the decorated function.

**Fix.** Replace `django.core.cache.cache` with a deterministic no-op:

```python
from django.core import cache as _dj_cache


class _NoOpCache:
    def get(self, key, default=None):
        return default

    def set(self, key, value, timeout=None, **kwargs):
        pass

    def add(self, key, value, timeout=None, **kwargs):
        return True

    def delete(self, key):
        pass

    def get_or_set(self, key, default, timeout=None):
        return default() if callable(default) else default

    def incr(self, key, delta=1):
        return delta

    def has_key(self, key):
        return False

    def __getattr__(self, name):
        return lambda *a, **kw: None


_dj_cache.cache = _NoOpCache()
```

Both `cache.get()` and `cache.set()` become deterministic constants under symbolic execution. Functions decorated with rate limiters / cache-keyed gates can now be analyzed.

This is essential for any project that uses `@cache_page`, `@rate_limit`, custom RPC decorators with cache-based rate limiting, or `@method_decorator(cache_page(...))`.

---

## Pattern 5c: `django.db.transaction.atomic` passthrough (no DATABASES needed)

**Problem.** Functions decorated with `@transaction.atomic` blow up under CrossHair because the atomic context manager calls into the live database connection pool to manage savepoints. Without a configured `DATABASES["default"]`, you see:

```
ImproperlyConfigured: settings.DATABASES is improperly configured.
Please supply the ENGINE value.
when calling set_up_new_database_for_user_on_internal_server('\x00\x02', ...)
```

CrossHair tried to enter the atomic block, the dummy DB backend complained, and the contract precondition was never even evaluated.

**Fix.** Replace `transaction.atomic` with a no-op decorator/context manager:

```python
from django.db import transaction as _dj_transaction
from contextlib import contextmanager


@contextmanager
def _noop_atomic_cm(*args, **kwargs):
    yield None


def _passthrough_atomic(using=None, savepoint=True, durable=False):
    # `transaction.atomic` is dual-use:
    #   - bare:        @atomic                (using=the function)
    #   - with parens: @atomic() / with atomic():    (using=None or db alias)
    if callable(using):
        return using   # bare-decorator form: return the wrapped function unchanged
    return _noop_atomic_cm()


_dj_transaction.atomic = _passthrough_atomic
```

After this, any `@transaction.atomic` function becomes equivalent to its bare body for CrossHair's purposes. Combine with the ORM stubs (Pattern that handles `Model.objects.update_or_create` etc.) and you can analyze full transactional flows.

The dual-use form (bare vs parens) is real — Django supports both `@transaction.atomic` and `@transaction.atomic(using="db_alias")`, plus `with transaction.atomic():`. The `callable(using)` branch handles the bare case.

---

## Pattern 5f: HttpRequest symbolic factory (unblocks `def view(request: HttpRequest, ...)`)

**Problem.** Views typed `(request: HttpRequest, user_profile: UserProfile, ...)` are unanalyzable by default. CrossHair calls `HttpRequest()`, the constructor populates most attributes from nothing (`META = {}`, `_post = None`), and any view code that reads `request.user` / `request.headers` / `request.POST` raises AttributeError before reaching the contract.

**Fix.** Register a `register_type(HttpRequest, factory)` that pre-populates the commonly-accessed attributes. Use `__new__` to bypass the constructor, then write into `instance.__dict__` directly because **many HttpRequest attributes are properties** (`body`, `scheme`, `content_type`, `encoding`) and can't be set via normal `instance.X = Y` syntax.

```python
from crosshair import register_type
from django.http import HttpRequest, QueryDict
from django.utils.datastructures import MultiValueDict


def _make_symbolic_httprequest(factory):
    instance = HttpRequest.__new__(HttpRequest)
    d = instance.__dict__   # bypass property setters

    # Container attrs — empty real Django types so .get() / .getlist() work
    d["GET"] = QueryDict(mutable=True)
    d["POST"] = QueryDict(mutable=True)
    d["FILES"] = MultiValueDict()
    d["COOKIES"] = {}
    d["META"] = {"REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": "testserver",
                 "REQUEST_METHOD": "GET", "wsgi.input": b""}
    d["session"] = {}     # plain dict supports __getitem__/get/__contains__
    d["headers"] = {}

    # `user` — synthesize via the registered UserProfile factory
    from <project>.models import UserProfile
    d["user"] = factory(UserProfile, "_request_user")

    # Primitives — symbolic so contracts can branch on them
    d["method"] = factory(str, "_request_method")
    d["path"] = factory(str, "_request_path")
    d["path_info"] = d["path"]

    # `body` is a @cached_property; writing into __dict__ overrides it
    body = factory(bytes, "_request_body")
    d["body"] = body
    d["_body"] = body
    d["_read_started"] = True

    # Properties that need defaults to avoid AttributeError on read
    d["content_type"] = "application/json"
    d["content_params"] = {}
    d["encoding"] = "utf-8"
    d["scheme"] = "http"
    d["resolver_match"] = None

    return instance


register_type(HttpRequest, _make_symbolic_httprequest)
```

**Three non-obvious gotchas:**

1. **Properties masquerade as attributes.** `instance.body = b""` raises `AttributeError: can't set attribute 'body'` because `body` is a `@cached_property`. `instance.scheme = "http"` raises the same. Solution: write into `instance.__dict__` directly. Python's attribute lookup checks `__dict__` before consulting the descriptor, so the override wins.

2. **`session` and `headers` don't need real types.** Real `SessionBase` and `HttpHeaders` are complex; views overwhelmingly call `.get(name)` / `name in obj`, so a plain `dict` works. Don't reach for the real types unless you find a caller that needs `.cycle_key()` or `.has_header()`.

3. **The factory presupposes the UserProfile/Realm factory.** If you register HttpRequest before models, `factory(UserProfile, ...)` raises ImportError. Register HttpRequest *after* `_register_symbolic_models()` in `install_stubs()`.

This unlocks any `zerver/views/`-style file. Combine with `--unblock open subprocess.Popen --` from preflight Pitfall section.

---

## Pattern 5e: `timezone.now` patch must return a CrossHair-symbolic datetime, not a concrete one

**Problem.** Code calling `django.utils.timezone.now() - timedelta(days=N)` (or any `dt - timedelta` involving `timezone_now()`) raises:

```
TypeError: unsupported operand type(s) for -: 'datetime.datetime' and 'timedelta'
```

The cause is non-obvious. CrossHair's `crosshair.libimpl.datetimelib` defines its own `datetime` and `timedelta` classes that **fake `__module__ = "datetime"`** to look like the real builtins, but they're separate types. CrossHair `register_patch`-replaces `datetime.timedelta(...)` calls in user code to return its symbolic timedelta. If `timezone_now()` returns a real concrete `datetime`, Python's slot wrapper does an isinstance check on the timedelta arg, fails, returns NotImplemented, and raises.

**Wrong fix:**
```python
from django.utils import timezone as _tz
fixed = datetime(2025, 1, 1, tzinfo=timezone.utc)
_tz.now = lambda: fixed                                    # ❌ concrete dt
```

**Right fix:**
```python
from crosshair import register_patch
from crosshair.core_and_libs import proxy_for_type

def _symbolic_now(*a, **kw):
    return proxy_for_type(datetime, '_tz_now')             # ✅ CrossHair-symbolic dt

register_patch(_tz.now, _symbolic_now)
_tz.now = _symbolic_now
```

Both sides are CrossHair types; subtraction works.

**Caveats.**

1. **`tzinfo.utcoffset(dt)` cannot be fixed this way.** It's a C-level method that does an isinstance check rejecting CrossHair's lookalike datetime. The error `utcoffset(dt) argument must be a datetime instance or None, not datetime` is unfixable from outside CrossHair; document as permanent FP.

2. **Don't extend this to DateTimeField defaults in `_make_symbolic_model`.** `factory(datetime, ...)` produces symbolic instances that CrossHair's own `gen_args` `deepcopy` trips on (`timezone.__new__` does `if not offset:` outside tracing → CrossHairInternal). Use a concrete `datetime(2025, 1, 1, ...)` for model fields and rely on the `timezone_now` patch alone for `dt - timedelta` arithmetic.

3. **`orjson.dumps` patches that call `deep_realize` must wrap it in `with ResumedTracing()`** — realization walks into symbolic datetime/timedelta/timezone whose `__bool__` and `__eq__` need tracing on, otherwise CrossHairInternal at `numeric_binop`.

---

## Pattern 5d: FK descriptor `__get__` patch (avoid DB queries on `instance.related`)

**Problem.** Even with `MockManager.get(...)` returning symbolic instances, every `user.realm` (or any FK / OneToOne attribute access) bypasses the manager and goes through `ForwardManyToOneDescriptor.__get__`, which on cache miss issues a real DB query:

```
psycopg2.OperationalError: connection to server at "localhost" ... failed
```

This shows up in `__str__` calls during CrossHair counterexample formatting, in any helper that does `obj.fk_field.<attr>`, and in audit-log machinery that touches `acting_user.realm`. Patching only `ForeignKeyDeferredAttribute.__set__` (a common starter patch) fixes writes but not reads.

**Fix.** Patch the descriptor's `__get__` to return a fresh symbolic proxy of the related model, cached on `_state.fields_cache` so identity is preserved across multiple accesses:

```python
from crosshair.core_and_libs import proxy_for_type
from django.db.models.fields.related_descriptors import (
    ForwardManyToOneDescriptor,
    ForwardOneToOneDescriptor,
)


def _fk_descriptor_get(self, instance, cls=None):
    if instance is None:
        return self
    cache_name = self.field.name              # NOT self.field.get_cache_name()
    try:
        cache = instance._state.fields_cache
    except AttributeError:
        return None
    if cache_name in cache:
        return cache[cache_name]
    related = proxy_for_type(self.field.related_model, f"_fk_{cache_name}")
    cache[cache_name] = related
    return related


ForwardManyToOneDescriptor.__get__ = _fk_descriptor_get
ForwardOneToOneDescriptor.__get__ = _fk_descriptor_get
```

**Two non-obvious points:**

1. **Use `self.field.name`, not `get_cache_name()`.** The abstract `FieldCacheMixin.get_cache_name()` raises `NotImplementedError`; the concrete override depends on the field class hierarchy and isn't reliable. `field.name` is the simple, version-stable cache key (and it's what Django itself uses internally).

2. **Patch BOTH `ForwardManyToOneDescriptor` and `ForwardOneToOneDescriptor`.** They're separate classes with separate `__get__` methods. Code that touches `OneToOneField` relations (e.g., `customer.profile` or `user.profile`) skips a `ManyToOne`-only patch.

For a deeper discussion of paired symbolic-instance synthesis (the `register_type` factory that produces the parent instance whose FK then resolves through this patch), see **`generate-stubs/references/phase-5-symbolic-models.md` § Alternative: register_type factories**.

---

## Pattern 5g: Django Model `__init__` is unintrospectable — `proxy_for_type(Model)` crashes

**Problem.** When CrossHair tries to construct a symbolic Django Model instance — directly via `proxy_for_type(SomeModel)` or indirectly because a function-under-analysis has an arg of that type — it crashes deep in its own machinery:

```
File ".../crosshair/dynamic_typing.py", line 342, in intersect_signatures
    result = Signature(
        parameters=list(out_params.values()), return_annotation=out_return_annotation
    )
File "/usr/lib/python3.14/inspect.py", line 3006, in __init__
    raise ValueError(msg)
ValueError: wrong parameter order: keyword-only parameter before variadic positional parameter
```

**Cause.** Django's `Model.__init__` signature (and the synthesized per-model `__init__` from `ModelBase`) has the shape `def __init__(self, *args, field1=None, field2=None, **kwargs)`. Python `inspect.Signature` rejects this when CrossHair tries to *intersect* it with parent-class signatures — keyword-only parameters can't appear before a variadic positional. The error is upstream of any contract evaluation: CrossHair never gets to your code.

**Where this fires.** Any path that asks CrossHair to synthesize a symbolic Model:

- Function-under-analysis takes a Model arg: `def view(request, child: Child) -> ...`
- Untyped arg whose usage forces CrossHair to infer a Model: `def helper(min_date, max_date, events, child)` where `child` flows into `qs.filter(child=child)`
- Custom stubs that call `proxy_for_type(self.model_type, ...)` directly — e.g., the obvious `MockQuerySet.first() -> proxy_for_type(self.model_type, ...)` implementation
- `deep_realize` during counterexample formatting — so even when analysis itself works, CrossHair can crash while building the error message, swallowing the actual finding

**Three workarounds.**

### A. Bypass `__init__` via `__new__` + `register_type` (most surgical)

Register a custom factory so CrossHair uses *your* construction path instead of introspecting the class:

```python
from crosshair import register_type
from django.db.models.base import ModelState

def _make_symbolic_model(model_class, factory):
    instance = model_class.__new__(model_class)              # skip __init__
    instance.__dict__["_state"] = ModelState()
    instance._state.adding = False
    instance._state.db = "default"
    # populate fields field-by-field from your schema spec...
    for col, info in _fields_for(model_class):
        instance.__dict__[col] = factory(_python_type(info), col)
    return instance

for model in (Child, Sleep, Feeding, ...):
    register_type(model, lambda factory, m=model: _make_symbolic_model(m, factory))
```

Combine with the FK descriptor patch (Pattern 5d) so `instance.related_field` returns its own symbolic proxy lazily. The Layer-B approach in `generate-stubs/references/phase-5-symbolic-models.md` walks through this in detail, including the `with ResumedTracing()` requirement around `space.add(...)`.

**Three implementation notes from a real project (wger, 2026-05) that an earlier version of this pattern got subtly wrong:**

1. **Patch `ForeignKeyDeferredAttribute.__set__` — NOT `ForwardManyToOneDescriptor.__set__`.** The `intersect_signatures` crash happens during `Model.__init__` → `_setattr(self, field.attname, val)` → the descriptor at `Model.<fk>_id` (the attname). That descriptor class is `ForeignKeyDeferredAttribute` from `django.db.models.fields.related_descriptors` (line 92 in Django 5.x). `ForwardManyToOneDescriptor` handles the *relation name* (`Model.<fk>`), which is what Pattern 5d covers — different class, different problem.

2. **`__new__` bypass alone is not enough — also patch `DeferredAttribute.__get__` and respect `null=True`.** After `__new__` leaves `__dict__` empty, the *next* crash is `DeferredAttribute.__get__` → `_check_parent_chain(instance)` → `link_field.attname` → `AttributeError: 'NoneType' object has no attribute 'attname'` (Django's parent-chain logic assumes the model was loaded via the ORM). Patch `DeferredAttribute.__get__` to return a typed symbolic proxy when the field name isn't in `__dict__`:

   ```python
   from django.db.models.query_utils import DeferredAttribute
   from django.db.models import IntegerField, CharField, TextField, BooleanField, FloatField, DecimalField, DateField, DateTimeField

   def deferred_get(self, instance, cls=None):
       if instance is None:
           return self
       data = instance.__dict__
       name = self.field.attname
       if name in data:
           return data[name]
       field = self.field
       python_type = None
       if isinstance(field, (IntegerField,)):  # covers Big/Small/Positive variants
           python_type = int
       elif isinstance(field, (CharField, TextField)):
           python_type = str
       elif isinstance(field, BooleanField):
           python_type = bool
       elif isinstance(field, FloatField):
           python_type = float
       elif isinstance(field, DecimalField):
           from decimal import Decimal
           python_type = Decimal
       elif isinstance(field, DateTimeField):
           from datetime import datetime
           python_type = datetime
       elif isinstance(field, DateField):
           from datetime import date
           python_type = date
       try:
           if python_type is None:
               val = None
           elif getattr(field, 'null', False):
               # CRITICAL: respect null=True so CrossHair explores both
               # the None and the typed branches. Returning a non-None
               # value for nullable fields masks real bugs (e.g. wger's
               # attribution_link family — TypeError str + None when
               # license_author is NULL — went silent until we honored
               # nullability here).
               from typing import Optional
               val = proxy_for_type(Optional[python_type], f"deferred_{type(instance).__name__}_{name}")
           else:
               val = proxy_for_type(python_type, f"deferred_{type(instance).__name__}_{name}")
       except BaseException:
           val = None
       data[name] = val
       return val

   DeferredAttribute.__get__ = deferred_get
   ```

3. **Prefer universal registration via `apps.get_models()` over hand-listing.** Hand-listing 3–5 "problematic models" leaves a long tail of stub gaps as new ORM-touching contracts get added. One loop covers every model in the project's apps and self-maintains:

   ```python
   from django.apps import apps
   for model in apps.get_models():
       if not (model.__module__ or '').startswith('your_project.'):
           continue
       try:
           register_type(model, lambda _f, m=model: _make_symbolic_model_via_new(m))
       except Exception:  # register_type raises Duplicate on re-register
           pass
   ```

   Filter by your project's module prefix so you don't register third-party app models you haven't designed factories for.

### B. Build a `SimpleNamespace` mock instead of touching the Model class

If you don't need `register_type` integration — e.g., your `MockQuerySet.__iter__` just needs to yield 0 or 1 instance — assemble a `SimpleNamespace` field-by-field and don't ask CrossHair to construct the real Model at all:

```python
from types import SimpleNamespace
from datetime import datetime

def _make_mock_sleep():
    return SimpleNamespace(
        id=proxy_for_type(int, 'sleep.id'),
        start=proxy_for_type(datetime, 'sleep.start'),
        end=proxy_for_type(datetime, 'sleep.end'),
        nap=proxy_for_type(bool, 'sleep.nap'),
        notes=proxy_for_type(Optional[str], 'sleep.notes'),
        child=_make_mock_child(),                      # nested mock, not the real Child
        tags=_MockRelatedManager(),                    # .all() returns []
    )

class MockQuerySet:
    def __iter__(self):
        has_row = proxy_for_type(bool, 'qs_nonempty')
        return iter([_make_mock_sleep()] if has_row else [])
```

This avoids the `__init__` introspection entirely — CrossHair only sees the per-field `proxy_for_type` calls, which use the standard introspection that works for `int`/`str`/`datetime`/etc. Used in babybuddy (2026-05) for the Tier-2 ORM stubs.

**Variant: lazy-symbolic `__getattr__` (cheapest unblock for User / AbstractUser).** When the only blocker is `AbstractUser` and you don't need real Model identity, a `__getattr__`-driven class beats the eager SimpleNamespace because (a) you don't have to enumerate fields up front and (b) every access yields a fresh symbolic value so CrossHair explores both branches of every boolean check the user appears in. Mathesar (2026-05) used this to unblock all User-bound function-under-analysis:

```python
class MockUser:
    """Lazy-symbolic Django auth User. Field-by-field types only, no _state."""
    def __getattr__(self, name):
        bool_fields = {"is_active", "is_staff", "is_superuser",
                       "is_authenticated", "is_anonymous"}
        int_fields  = {"id", "pk"}
        str_fields  = {"username", "email", "password",
                       "first_name", "last_name"}
        if name in bool_fields:
            return proxy_for_type(bool, f"user_{name}")
        if name in int_fields:
            return proxy_for_type(int, f"user_{name}")
        if name in str_fields:
            return proxy_for_type(str, f"user_{name}")
        if name in ("check_password", "has_perm", "has_perms",
                    "has_module_perms", "has_usable_password"):
            return lambda *a, **kw: proxy_for_type(bool, f"user_{name}_call")
        if name == "save":
            return lambda *a, **kw: None
        return proxy_for_type(Any, f"user_{name}")

# One-line wiring at the end of install_runtime_patches() / plugin setup:
from crosshair import register_type
register_type(User, lambda _factory: MockUser())
```

After this is in place, **annotate the function-under-analysis with `user: User`** so CrossHair looks up the registered factory. Without the annotation, CrossHair guesses primitives and your `hasattr(user, ...)` precondition silently aborts the run (see `precondition-patterns.md`).

**Caveat.** `MockUser` is *not* a `User` subclass. Code doing `isinstance(user, User)` or `user._meta...` introspection will fail. For Mathesar-shaped code (mostly `user.is_superuser`, `user.is_authenticated`, `user.id`), `__getattr__` is enough. If the analyzed code does ORM introspection on the user, escalate to workaround (A) `__new__` bypass.

**Pairs with Pattern 5d.** Once `user: User` resolves via this factory, the function body typically continues into `Model.objects.get(user=user, ...)` and then accesses FK fields on the returned proxy (`user_dbrm.server.host`). Without Pattern 5d those accesses raise `RelatedObjectDoesNotExist`. Wire both together.

### C. Constrain the precondition so CrossHair never has to construct a Model

Cheapest workaround when the function under analysis has a Model parameter that isn't actually exercised in the contract:

```python
def _add_diaper_changes(min_date, max_date, events, child):
    """
    pre: child is None
    ...
    """
```

CrossHair only generates `child = None`; never tries to construct a `Child`. Loses coverage of the FK-filtered branch but unblocks the rest of the contract.

**Choosing between A/B/C.**

| Workaround | When to use | Cost |
|---|---|---|
| A. `register_type` + `__new__` | Whole-codebase analysis, FK relations matter, multiple model types referenced as args | Highest — needs a schema spec and ResumedTracing wrapping |
| B. `SimpleNamespace` mocks | Targeted analysis of a few iteration-heavy files; you control the QuerySet stub anyway | Medium — one factory per model used |
| C. Precondition `is None` | Single function, FK arg isn't exercised by the contract you actually care about | Lowest — but loses a code path |

**Cross-references.**

- **Pattern 5d** (FK descriptor `__get__` patch) builds on top of approach A. Without (A), the FK patch's `proxy_for_type(self.field.related_model, ...)` triggers the same `intersect_signatures` failure on the related model.
- **Pattern 5f** (HttpRequest factory) uses the `__new__` bypass technique for `HttpRequest` itself — see lines mentioning `instance = HttpRequest.__new__(HttpRequest); d = instance.__dict__`. Same idea, applied to a Django framework class.
- **Pattern 7** (function-level targeting) is the *file-scope* dual of this problem — sidesteps `intersect_signatures` failures triggered by *forward-ref annotations* in the file's import graph rather than by argument-type construction. Both can fire on the same project; prefer (A) or (B) over (7) when you can build the stub.

---

## Pattern 6: Auditwall pre-import for native dependencies (cross-reference)

If the project imports cairocffi/cairosvg (e.g. for PDF/SVG generation), psycopg2, cryptography, or any other CFFI-bound native library, you'll see `SideEffectDetected` during settings/model loading. The fix lives in **`crosshair-sqlalchemy/references/plugin-patterns.md` Pattern 1**.

Short version for Django-only projects:

```python
import importlib
from crosshair import auditwall as _auditwall

_auditwall.disable_auditwall()
try:
    for _mod in ("cairocffi", "cairosvg", "cryptography",
                 "django.contrib.auth.hashers"):
        try:
            importlib.import_module(_mod)
        except ImportError:
            pass
    import ctypes.util as _u
    _u.find_library("c")
finally:
    _auditwall._ENABLED = True   # NB: engage_auditwall() does NOT re-arm
```

Add this block at the **end** of the plugin, after registry patches and ORM stub loading.

---

## Pattern 7: Function-level vs whole-file targeting (cross-reference)

If `crosshair check path/to/file.py` exits with `ValueError: wrong parameter order...` from `intersect_signatures`, or `NameError: name 'X' is not defined` from a forward-reference annotation, target the function by qualified name instead:

```bash
crosshair check 'mathesar.utils.users.change_password' --extra_plugin ...
```

Function-level targeting only generates proxies for the function's direct argument types, sidestepping CrossHair's attempt to walk every class in the file's import graph.

If the same `wrong parameter order` error fires when CrossHair tries to construct a *function argument* of a Django Model type (rather than a forward-ref class in the import graph), function-level targeting won't help because the offending class IS the function's arg type. See **Pattern 5g** for the model-arg variant and its workarounds.

Most often hit on files that transitively import SQLAlchemy. Full discussion in **`crosshair-sqlalchemy/references/plugin-patterns.md` Pattern 2**.

---

## Pattern 8: Stubbing connection helpers — patch BOTH the source module AND every importer

When code under analysis routes through a free function like `db.connection.exec_msar_func(conn, ...)` or `db.connection.mathesar_connection(...)` that ultimately does `psycopg.connect()` / `conn.execute(...)`, stubbing only the *source* module is **not enough**. Symptom: even after `db.connection.mathesar_connection = _stub_fn`, the analyzed function still calls the original and hits a side-effect / native-lib error.

### Why

`from db.connection import mathesar_connection` (a common pattern at the top of model files) **binds the symbol into the importing module's namespace** at module load time. Overwriting `db.connection.mathesar_connection` later doesn't change the importer's already-captured reference. Every module that did `from X import Y` holds its own copy of the binding.

### Fix

After patching the source module, re-bind in every known caller. For Django ORMs the usual suspects are `<app>.models.base` (where the `@property connection` etc. are defined) and any service-layer modules.

```python
# Source-of-truth patch:
from db import connection as _db_conn
_db_conn.mathesar_connection = _stub_mathesar_connection
_db_conn.exec_msar_func = _stub_exec_msar_func

# Re-bind in every module that did `from db.connection import <name>`.
# Find them with: grep -r "from db.connection import" mathesar/
try:
    from mathesar.models import base as _mathesar_base
    _mathesar_base.mathesar_connection = _stub_mathesar_connection
except ImportError:
    pass
```

### Stub shapes

A typical `_StubConnection` / `_StubCursor` pair that covers `with conn as c: c.execute(sql, args).fetchone()` and `conn.cursor()` flows:

```python
class _StubCursor:
    row_factory = None
    def fetchone(self):
        return (proxy_for_type(dict, 'sql_row'),)
    def fetchall(self):
        return []
    def __iter__(self):
        return iter([])
    def __enter__(self):
        return self
    def __exit__(self, *_a):
        return None

class _StubConnection:
    def __enter__(self):
        return self
    def __exit__(self, *_a):
        return None
    def execute(self, *_a, **_kw):
        return _StubCursor()
    def cursor(self, *_a, **_kw):
        return _StubCursor()
    def close(self):
        pass
```

Use `proxy_for_type(dict, ...)` for `fetchone()[0]` when the SQL function returns JSON — but **this is too loose** if callers do nested subscript like `current_role["parent_roles"][0]["name"]`. A plain symbolic `dict` is empty, so `["parent_roles"]` raises `KeyError` — a false-positive counterexample that's just stub looseness.

**Tighter pattern — permissive JSON value.** When the SQL helper returns dynamic JSON of unknown shape and callers may walk arbitrary key paths, use a permissive class that never raises on subscript:

```python
class _AnyJsonValue:
    """Permissive symbolic JSON value: subscriptable, iterable, comparable."""
    __slots__ = ('_name', '_depth')
    _DEPTH_LIMIT = 4

    def __init__(self, name='json_val', depth=0):
        self._name = name
        self._depth = depth

    def _child(self, suffix):
        if self._depth >= self._DEPTH_LIMIT:
            return proxy_for_type(Any, f"{self._name}_{suffix}_leaf")
        return _AnyJsonValue(f"{self._name}_{suffix}", self._depth + 1)

    def __getitem__(self, key):
        return self._child(f"sub_{key}" if isinstance(key, (str, int)) else "sub")

    def __iter__(self):
        if self._depth >= self._DEPTH_LIMIT:
            return iter([])
        return iter([self._child("iter0")])

    def __contains__(self, _k):
        return proxy_for_type(bool, f"{self._name}_contains")

    def __eq__(self, _o):
        return proxy_for_type(bool, f"{self._name}_eq")

    def __ne__(self, o):
        return not self.__eq__(o)

    def __hash__(self):
        return id(self)

    def __bool__(self):
        return True

    def __str__(self):
        return proxy_for_type(str, f"{self._name}_str")

    def __len__(self):
        return proxy_for_type(int, f"{self._name}_len")

    def get(self, key, default=None):
        return self._child(f"get_{key}")

    def keys(self):
        return iter([proxy_for_type(str, f"{self._name}_key")])

    def values(self):
        yield self._child("val")

    def items(self):
        yield (proxy_for_type(str, f"{self._name}_k"), self._child("v"))
```

Then have `_StubCursor.fetchone()` return `(_AnyJsonValue('msar_func_row'),)`. The depth limit prevents runaway recursion if user code iterates deeply.

**When this isn't enough.** For msar functions with strict typed outputs (e.g. `int`, `bool`, `(int, int)`), you can branch on `func_name` in the stub and return tighter shapes. The permissive class is the default fallback; per-function shapes are escalation when needed.

### When to apply

Look for project code shaped like `with model.connection as conn: conn.execute(...)` or service-layer wrappers around the DB driver. If `mathesar_connection`-style helpers exist, this pattern is the cheapest way to stop CrossHair from doing real `psycopg.connect()` calls without rewriting the helpers' bodies.

Pairs with **Pattern 5g** (model `__init__` bypass): once `proxy_for_type(SomeModel)` works, this pattern keeps the model's `@property connection` from blowing up when accessed.

---

## Pattern 9: Stub Django built-in models too — auto-generated stubs only cover project models

Stub generators (e.g. `/generate-stubs`) scan the project's `models.py` files and install `MockManager` on every project model. But Django itself ships several models that user code commonly hits:

- `django.contrib.sessions.models.Session`
- `django.contrib.auth.models.Group`, `Permission`
- `django.contrib.contenttypes.models.ContentType`
- `django.contrib.sites.models.Site`
- `django.contrib.admin.models.LogEntry`

**Symptom:** `ImproperlyConfigured: settings.DATABASES is improperly configured` when CrossHair analyzes a function that does e.g. `Session.objects.get(session_key=...)`. The unstubbed `Session.objects` is a real Django `Manager` that tries to talk to the configured database.

**Fix:** add explicit stubs for the built-in models the project actually uses, alongside the auto-generated ones:

```python
def install_stubs() -> None:
    # ... project models ...

    # Django built-ins used by the project
    try:
        from django.contrib.sessions.models import Session
        Session.objects = MockManager(Session)
        Session.save = mock_save
        Session.delete = mock_delete
    except ImportError:
        pass

    try:
        from django.contrib.auth.models import Group, Permission
        Group.objects = MockManager(Group)
        Permission.objects = MockManager(Permission)
    except ImportError:
        pass
```

**Caveat — reverse-relation accessors:** `session.downloadlink_set.add(*links)` does **not** route through the stubbed `Session.objects`. It uses a separate Django descriptor (the reverse-side `ManyRelatedManager`) attached to the related-model class. The MockManager M2M mutators (`add`/`set`/`remove`/`clear`) only fire if you also wire `_patch_reverse_relations` to install MockManagers on those descriptors — see `crosshair-django/references/reverse-relations.md`. Without that wiring, calls like `session.downloadlink_set.add(...)` will hit `ValueError: Cell is empty` or similar Django-internal errors and the function is effectively uncontractable without the full plumbing.

**How to find which built-ins to add:** grep for `from django.contrib.<x>.models import` across the project. Each model name imported is a candidate.

---

## Putting it all together — full plugin skeleton

```python
# crosshair_django_setup.py
import os
import importlib

# 1. Pre-set environment so settings load doesn't trip auditwall (Pattern 1)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
os.environ.setdefault("SECRET_KEY", "crosshair-fixed-secret-not-for-production")

# 2. Import stub classes from a real module (Pattern 4 — exec scope gotcha)
from _crosshair_registry_patch import _RegistryStubAppConfig
from django.apps import apps as _apps

# 3. Patch the Apps class (Patterns 2 + 3)
_INSTALLED_APP_LIES = frozenset({
    "allauth.account", "allauth.socialaccount",
    "django.contrib.sites", "django.contrib.contenttypes", "django.contrib.auth",
})

def _patched_get_containing_app_config(self, object_name, _Stub=_RegistryStubAppConfig):
    # ... see Pattern 3
    ...

def _patched_get_app_config(self, app_label, _Stub=_RegistryStubAppConfig):
    ...

def _patched_is_installed(self, app_name, _Lies=_INSTALLED_APP_LIES):
    ...

_apps.__class__.get_containing_app_config = _patched_get_containing_app_config
_apps.__class__.get_app_config = _patched_get_app_config
_apps.__class__.is_installed = _patched_is_installed
_apps.apps_ready = _apps.models_ready = _apps.ready = True

# 4. Auto-load ORM stubs + runtime patches (Patterns 5, 5b, 5c)
importlib.import_module("_crosshair_stubs")
# _crosshair_stubs.py should also call install_runtime_patches() to install
# the typing.get_type_hints swallow, cache no-op, and transaction.atomic
# passthrough — see Patterns 5b/5c above for the code.

# 5. Pre-import native dependencies with auditwall off (Pattern 6)
from crosshair import auditwall as _auditwall

_auditwall.disable_auditwall()
try:
    for _mod_name in (
        "ctypes", "ctypes.util",
        "cryptography",
        "django.contrib.auth.hashers",
        "django.contrib.auth.password_validation",
        "cairocffi", "cairosvg",
    ):
        try:
            importlib.import_module(_mod_name)
        except ImportError:
            pass

    try:
        import ctypes.util as _ctypes_util
        _ctypes_util.find_library("c")
    except Exception:
        pass
finally:
    _auditwall._ENABLED = True
```

For mixed Django + SQLAlchemy projects (e.g. Mathesar), append the SQLAlchemy block from `crosshair-sqlalchemy/plugin-patterns.md` to the end of this skeleton.

---

## When to update this file

If you encounter a new Django-specific failure or a new package whose `is_installed`-style check needs an allow-list entry, add it here. The patterns above came from concrete failures in NetBox and Mathesar; future entries should also cite the symptom that prompted them.
