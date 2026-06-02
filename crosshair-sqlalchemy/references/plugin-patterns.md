# CrossHair Plugin Patterns for SQLAlchemy + Native Drivers

Patterns for the CrossHair plugin file when SQLAlchemy is in the import graph. Many of these are also useful for any project with CFFI-bound native dependencies (cairocffi, cryptography, oracledb, etc.) — see `crosshair-django/plugin-patterns.md` for the Django-specific subset.

---

## Pattern 1: Pre-import drivers and CFFI bindings with auditwall disabled

**Problem.** CrossHair arms its `sys.audithook` (auditwall) **before** exec'ing the plugin. Native drivers do these things during their own import:

- `psycopg2` writes to `/tmp/<temp>` while loading `libpq.so`
- `oracledb.thin_mode` shells out to OS for SSL config
- `cryptography.hazmat.bindings._rust` triggers `dlopen` chains
- `cairocffi.__init__` calls `ctypes.util.find_library("cairo")` → forks `/sbin/ldconfig -p`

Result: `SideEffectDetected: subprocess.Popen` or `SideEffectDetected: open(... 'x')` aborts analysis before any user code runs.

**Fix.** In the plugin, disable the wall, do the imports, then re-enable:

```python
import importlib
from crosshair import auditwall as _auditwall

_auditwall.disable_auditwall()
try:
    for _mod_name in (
        "ctypes", "ctypes.util",
        "cryptography", "cryptography.hazmat.backends.openssl",
        "psycopg", "psycopg2",
        "oracledb",       # if used
        "pymysql",        # if used
        "asyncpg",        # if used
        "sqlalchemy", "sqlalchemy.engine", "sqlalchemy.orm",
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

**Two gotchas:**
1. `engage_auditwall()` only **adds** another audithook — it doesn't re-enable a previously disabled wall. You must set `_auditwall._ENABLED = True` directly.
2. Add modules iteratively. Each time you see a `SideEffectDetected` traceback, the named module gets added to the pre-import list. The error message tells you exactly what's needed.

---

## Pattern 1b: Patch `typing.get_type_hints` to swallow forward-ref NameErrors

**Problem.** Even with all drivers pre-imported, CrossHair calls `typing.get_type_hints()` to discover annotations on classes during proxy generation. Many classes in SQLAlchemy and Python 3.14 stdlib have string forward refs that are not resolvable in their defining module:

```
NameError: name 'FromClause' is not defined
NameError: name 'TypeEngine' is not defined
NameError: name 'ColumnElement' is not defined
NameError: name 'ClassVar' is not defined        # Python 3.14 stdlib _colorize.py
```

These are **latent bugs** in stdlib/SQLAlchemy that don't matter at runtime (the classes are never instantiated through that annotation path) but kill CrossHair, which insists on resolving every annotation for proxy generation.

**Fix.** In your stubs/runtime-patches module, wrap `typing.get_type_hints` to return `{}` when forward-ref resolution fails:

```python
import typing

_real_get_type_hints = typing.get_type_hints


def _safe_get_type_hints(obj, globalns=None, localns=None, include_extras=False):
    try:
        return _real_get_type_hints(
            obj, globalns, localns, include_extras=include_extras
        )
    except (NameError, AttributeError, TypeError):
        return {}


typing.get_type_hints = _safe_get_type_hints

# CRITICAL: CrossHair imported get_type_hints with `from typing import ...`
# at its own module load, so we must rebind it on those modules too.
for _mod_name in (
    "crosshair.core",
    "crosshair.libimpl.builtinslib",
    "crosshair.dynamic_typing",
):
    try:
        _mod = __import__(_mod_name, fromlist=["get_type_hints"])
        if hasattr(_mod, "get_type_hints"):
            _mod.get_type_hints = _safe_get_type_hints
    except ImportError:
        pass
```

**Critical gotcha:** `from typing import get_type_hints` imports the *function object*, not the *attribute access*. Reassigning `typing.get_type_hints` doesn't affect importers that already grabbed a reference. CrossHair's `core.py`, `libimpl/builtinslib.py`, and `dynamic_typing.py` all do this — patch each one explicitly.

Returning `{}` is safe because CrossHair only uses the result to know which fields to symbolize. An empty dict means "no fields to symbolize" — the class will still be proxyable for argument generation, just with fewer constraints.

This pattern unblocks whole-file scans on every file that transitively imports SQLAlchemy types in their annotations. It's strictly better than Pattern 2 (function-level targeting) because it lets you scan the whole file for contracts.

---

## Pattern 2: Function-level targeting bypasses SQLAlchemy forward-ref failures

**Problem.** SQLAlchemy uses string-typed forward references in many of its annotations:

```python
# in sqlalchemy/sql/selectable.py (paraphrased)
class FromClause(...):
    selectable: "FromClause"  # forward ref evaluated only on demand

class TypedColumn(...):
    type_: "TypeEngine"
```

When CrossHair tries to generate a symbolic proxy for one of these classes, it calls `typing.get_type_hints(cls)`, which evaluates the forward refs in the class's module namespace. SQLAlchemy lazy-imports many of these names, so `get_type_hints()` raises:

```
NameError: name 'FromClause' is not defined
NameError: name 'TypeEngine' is not defined
NameError: name 'ColumnElement' is not defined
```

This kills whole-file scans (`crosshair check db/queries.py`) before any contracts are evaluated.

**Fix.** Target the function by qualified name instead of the file:

```bash
# Whole-file scan: trips on SQLAlchemy forward refs
crosshair check db/queries.py --extra_plugin crosshair_sqlalchemy_setup.py

# Function-level: bypasses module-wide proxy generation
crosshair check 'db.queries.build_select' --extra_plugin crosshair_sqlalchemy_setup.py
```

Function-level targeting only generates proxies for the function's direct argument types, sidestepping CrossHair's attempt to walk every class in the file's import graph.

When generating `run_crosshair.sh` in Phase 9 of `crosshair-bugs`, prefer function-level targets for any module that imports SQLAlchemy directly. The contracts-targets manifest can be enumerated by qualified name from the contracts plan.

A related failure on Python 3.14:

```
NameError: name 'ClassVar' is not defined
  File "/usr/lib/python3.14/_colorize.py", line 124, in __annotate__
```

The 3.14 stdlib `_colorize` module declares `__dataclass_fields__: ClassVar[dict[str, Field[str]]]` as an annotation but doesn't import `ClassVar`. Same workaround: use function-level targets for any file whose import chain reaches `_colorize`.

---

## Pattern 3: Engine / Connection / Session / Query stubs

CrossHair can't symbolically construct live database connections. Provide stubs that return symbolic values, similar to Django's `MockManager` / `MockQuerySet`:

```python
# _crosshair_sa_stubs.py
from typing import Any, Generic, List, Optional, Tuple, TypeVar

from crosshair.core_and_libs import proxy_for_type

T = TypeVar('T')


class MockResult(Generic[T]):
    """Mock SQLAlchemy CursorResult / Result."""

    def __init__(self, row_type: type = tuple):
        self.row_type = row_type

    def fetchone(self) -> Optional[T]:
        return proxy_for_type(Optional[self.row_type], 'sa_result_fetchone')

    def fetchall(self) -> List[T]:
        return proxy_for_type(List[self.row_type], 'sa_result_fetchall')

    def scalar(self) -> Any:
        return proxy_for_type(Any, 'sa_result_scalar')

    def scalar_one(self) -> Any:
        return proxy_for_type(Any, 'sa_result_scalar_one')

    def scalar_one_or_none(self) -> Optional[Any]:
        return proxy_for_type(Optional[Any], 'sa_result_scalar_one_or_none')

    def __iter__(self):
        return iter([])

    def keys(self) -> List[str]:
        return []


class MockConnection:
    """Mock Engine / Connection."""

    def execute(self, *args, **kwargs) -> MockResult:
        return MockResult()

    def scalar(self, *args, **kwargs) -> Any:
        return proxy_for_type(Any, 'sa_conn_scalar')

    def begin(self):
        return self  # context manager

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MockSession:
    """Mock Session for ORM-style code."""

    def query(self, *args, **kwargs) -> 'MockQuery':
        return MockQuery()

    def execute(self, *args, **kwargs) -> MockResult:
        return MockResult()

    def add(self, obj): pass
    def add_all(self, objs): pass
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass
    def refresh(self, obj): pass


class MockQuery:
    """Mock Query for legacy SQLAlchemy 1.x API."""

    def filter(self, *a, **k): return self
    def filter_by(self, **k): return self
    def order_by(self, *a): return self
    def limit(self, n): return self
    def offset(self, n): return self
    def all(self) -> list: return proxy_for_type(list, 'sa_query_all')
    def first(self) -> Optional[Any]: return proxy_for_type(Optional[Any], 'sa_query_first')
    def one(self) -> Any: return proxy_for_type(Any, 'sa_query_one')
    def one_or_none(self) -> Optional[Any]: return proxy_for_type(Optional[Any], 'sa_query_one_or_none')
    def count(self) -> int: return proxy_for_type(int, 'sa_query_count')
    def __iter__(self): return iter([])


def install_stubs():
    """Patch SQLAlchemy classes to return mocks under symbolic execution."""
    try:
        import sqlalchemy.engine
        sqlalchemy.engine.Engine.connect = lambda self: MockConnection()
        sqlalchemy.engine.Connection.execute = MockConnection.execute
    except (ImportError, AttributeError):
        pass

    try:
        import sqlalchemy.orm
        # Patch sessionmaker to return MockSession
        original_call = sqlalchemy.orm.sessionmaker.__call__
        sqlalchemy.orm.sessionmaker.__call__ = lambda self, *a, **k: MockSession()
    except (ImportError, AttributeError):
        pass


install_stubs()
```

Load this from your plugin via `importlib.import_module("_crosshair_sa_stubs")`.

The exact stubs depend on which SQLAlchemy API surface the project uses. Cover the entry points (`session.query`, `conn.execute`, `engine.connect`, the result fetchers) and let the rest fall through to default `proxy_for_type` behavior.

---

## Pattern 4: Skipping native bind-param adapters

**Problem.** Some SQLAlchemy bind-param adapters wrap values via psycopg2 type extensions:

```python
from psycopg2.extras import Json
conn.execute(text(":data"), {"data": Json(some_dict)})
```

Under symbolic execution, `Json.__init__` calls into native `_psycopg.so` and crashes.

**Fix.** In the stubs file, replace the adapter with a passthrough:

```python
try:
    import psycopg2.extras
    psycopg2.extras.Json = lambda x: x   # passthrough — no native call
except ImportError:
    pass
```

Apply the same pattern for `Numeric` decimals, `Range`, or any `extras.*` you encounter.

---

## Pattern 5: Repository / DAO class hierarchy patches

**Problem.** Most non-trivial SQLAlchemy projects wrap their ORM access in repository or DAO classes — `RepositoryGeneric`, `BaseRepository`, `RecipeDAO`, etc. — typically parameterized over a Pydantic schema and an ORM model. Their constructors take complex args:

```python
class RepositoryGeneric[Schema: BaseModel, Model: SqlAlchemyBase]:
    def __init__(self, session: Session, primary_key: str,
                 sql_model: type[Model], schema: type[Schema]) -> None: ...

class GroupRepositoryGeneric[...](RepositoryGeneric[...]):
    def __init__(self, ..., *, group_id: UUID4 | None | NotSet) -> None: ...

class RepositoryRecipes(GroupRepositoryGeneric[Recipe, RecipeModel]): ...
```

When a contracted method on one of these classes has any `pre: self.group_id is not None` style condition, CrossHair tries to construct the repo instance symbolically. It can't pick valid combinations of `Session + type + type + UUID`, so every contracted method reports **"Unable to meet precondition"** — without the method body ever running.

**Symptom.** `crosshair check` on a repository module produces N lines of:

```
mealie/repos/repository_recipes.py:387: info: Unable to meet precondition.
mealie/repos/repository_users.py:18: info: Unable to meet precondition.
```

…and no actual analysis happens.

**Fix.** Patch every repo class's `__init__` to a no-op that populates state-bearing attrs with `proxy_for_type` proxies. Pre-resolve `(schema, model)` from each subclass's generic args via `typing.get_args(cls.__orig_bases__[i])` — those are concrete classes used in `select(self.model)` and `self.schema.model_validate(...)`, so they need real types, not proxies.

```python
class _MockLogger:
    """No-op logger for Repository instances under CrossHair."""
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def debug(self, *a, **k): pass
    def exception(self, *a, **k): pass
    def critical(self, *a, **k): pass


def _install_repository_patches():
    from typing import Optional, get_args
    from uuid import UUID
    from sqlalchemy.orm import Session
    # Import the project's repo base class — adjust import path
    from mealie.repos.repository_generic import (
        RepositoryGeneric, GroupRepositoryGeneric, HouseholdRepositoryGeneric,
    )

    # State-bearing attrs that repo methods read — symbolic when tracing
    REPO_STATE_FIELDS = {
        'session': Session,
        '_group_id': Optional[UUID],
        '_household_id': Optional[UUID],
        'user_id': Optional[UUID],
        'primary_key': str,
    }

    def _all_subclasses(cls):
        subs = set(cls.__subclasses__())
        for s in list(subs):
            subs.update(_all_subclasses(s))
        return subs

    repo_classes = {RepositoryGeneric, GroupRepositoryGeneric, HouseholdRepositoryGeneric}
    repo_classes |= _all_subclasses(RepositoryGeneric)

    # Pre-resolve (schema, model) per repo class from __orig_bases__
    repo_generics: dict[type, tuple] = {}
    for cls in repo_classes:
        for base in getattr(cls, '__orig_bases__', ()):
            try:
                args = get_args(base)
            except Exception:
                continue
            if len(args) >= 2 and isinstance(args[0], type) and isinstance(args[1], type):
                repo_generics[cls] = (args[0], args[1])
                break

    def _repo_init(self, *args, **kwargs):
        try:
            from crosshair.statespace import context_statespace
            from crosshair.core_and_libs import proxy_for_type
            space = context_statespace()
            is_tracing = space is not None
        except BaseException:
            is_tracing = False

        if is_tracing:
            for attr, py_type in REPO_STATE_FIELDS.items():
                try:
                    val = proxy_for_type(py_type, f'repo_{attr}')
                    object.__setattr__(self, attr, val)
                except Exception:
                    pass

        # Bind concrete schema/model classes from generic args
        sg = repo_generics.get(type(self))
        if sg is not None:
            schema_cls, model_cls = sg
            try:
                object.__setattr__(self, 'schema', schema_cls)
                object.__setattr__(self, 'model', model_cls)
            except Exception:
                pass

        # Caller-supplied kwargs override proxies
        for k, v in kwargs.items():
            try:
                object.__setattr__(self, k, v)
            except Exception:
                pass

        # No-op logger so logger.info / logger.error don't crash
        try:
            object.__setattr__(self, 'logger', _MockLogger())
        except Exception:
            pass

    for cls in repo_classes:
        cls.__init__ = _repo_init
```

**Result.** Methods that previously reported "Unable to meet precondition" now actually execute. They typically produce a mix of `Not confirmed`, real-looking `error: AttributeError: 'Repo' has no attribute 'X'` (when the repo accesses an attr we didn't include in `REPO_STATE_FIELDS` — add it and re-run), and `error: ValidationError: ... for SchemaName` (Pydantic mismatch; expected stub artifact — see `symbolic-stubs.md`).

**Tips:**
- Iterate on `REPO_STATE_FIELDS` as new "no attribute X" errors appear. Add `Optional[<py_type>]` for nullable fields, concrete types otherwise.
- Use `__getattr__` instead of pre-population if the repo's attribute surface is too wide to enumerate — see the `MockUser` example in `crosshair-bugs/references/symbolic-stubs.md`.
- Functions with `pre: self.group_id is not None` may still report "Unable to meet precondition" if `_group_id` is `Optional[UUID]` and CrossHair can't construct a non-None `UUID` symbolically. See the UUID caveat in `Pattern 2b` (Layer 2b in the Django template).

---

## Pattern 2b caveat: symbolic UUIDs and SQLAlchemy filters

The Django template's UUID patch (`uuid.UUID.__init__` → `__dict__["int"] = int`) lets CrossHair construct symbolic `UUID` instances and satisfy preconditions like `self.group_id is not None`. In **pure Django** projects this works cleanly.

**In SQLAlchemy projects, enabling the UUID patch can crash analysis** of any function that uses a UUID column in a filter expression. Specifically:

```python
stmt = select(UserToRecipe).filter(UserToRecipe.user_id == user_id)
```

When `user_id` is a symbolic UUID, SQLAlchemy's `Column.__eq__` walks into `sqlalchemy/sql/annotation.py` to annotate the comparison. The annotation machinery makes branching decisions on the symbolic UUID's contents, and CrossHair reports `NotDeterministic: Wrong node type (is ParallelNode, expected WorstResultNode)` — fatal to the whole file's analysis.

> **Try Pattern 6 first.** This `NotDeterministic` shares its root cause with the general lazy-annotation-memoization problem (Pattern 6). Pre-warming the expression caches — which warms the UUID columns too — may let you **keep** the UUID patch *and* analyze UUID-filtered files, rather than trading one for the other. Fall back to disabling the patch only if `NotDeterministic` blocks with a `sqlalchemy/.../annotation.py` stack tail persist after prewarming.

**Workaround.** Gate the UUID patch behind a per-project flag and leave it off by default in SQLAlchemy projects:

```python
_ENABLE_UUID_PATCH = False   # toggle per project
if _ENABLE_UUID_PATCH:
    _install_uuid_patch()
```

The net trade is usually negative: enabling the patch resolves 2–3 UUID-typed UMPs but loses all analysis on the (typically larger) set of files that filter by UUID columns.

**Additional UUID gotcha** (applies regardless of whether you ship the patch): `UUID` uses `__slots__`, not `__dict__`. The Django template's `self.__dict__["int"] = int` line fails on Python 3.12+ UUID with `AttributeError: 'UUID' object has no attribute '__dict__'`. Use `object.__setattr__(self, "int", int)` instead — works for slot members.

Also: `UUID.__getstate__` does `if self.is_safe != SafeUUID.unknown:` — a symbolic-vs-enum comparison that trips "Numeric operation on symbolic" during CrossHair's argument deepcopy. Patch `__deepcopy__` to return `self` (UUIDs are immutable) in addition to patching `__init__`:

```python
import uuid as _uuid

def _patched_uuid_deepcopy(self, memo):
    return self

_uuid.UUID.__deepcopy__ = _patched_uuid_deepcopy
```

---

## Pattern 6: Pre-warm expression caches to eliminate `NotDeterministic` aborts

**Symptom.** CrossHair prints a debug block then aborts a contract position:

```
*** Begin Not Deterministic Debug ***
...
Previous stack tail:
  .../crosshair/enforce.py:112
  .../sqlalchemy/sql/annotation.py:171
  .../sqlalchemy/sql/elements.py:5271
  .../sqlalchemy/orm/properties.py:382
Reason: Wrong node type (is ParallelNode, expected WorstResultNode)
*** End Not Deterministic Debug ***
.../daos/foo.py:49: error: NotDeterministic: Found a different execution paths after making the same decisions
```

The tell is a **`Previous stack tail` running through `sqlalchemy/sql/annotation.py` and `sqlalchemy/orm/properties.py`**. The cost is *lost coverage* — that contract position is never checked, pass or fail. It is not a bug and not a false positive.

**Root cause.** CrossHair verifies each path by **re-executing it** and requiring identical decisions both times. SQLAlchemy builds column-comparison expressions lazily: the *first* time code constructs `Model.col == x` (or `.in_()`, `.like()`, `.is_()`, …) it computes and **memoizes** an annotated clause element (`ColumnProperty` `@memoized_property` + the global annotation cache in `sql/annotation.py`). On CrossHair's replay the cache is warm, so SQLAlchemy takes the *read-cache* branch instead of the *compute* branch — a different internal decision tree — and CrossHair declares `NotDeterministic`. The DAO/repo body triggers it merely by constructing a query; the symbolic value never even has to reach SQLAlchemy. (The Pattern 2b caveat's UUID-filter `NotDeterministic` is the **same root cause**, just reached via a UUID column.)

**Fix.** Force that memoization to happen **once, at plugin/stub install time, outside any CrossHair statespace.** Walk every mapped class's columns and touch the operators the code uses. Both of CrossHair's iterations then hit the warm path.

```python
def prewarm_expression_caches(model_classes) -> int:
    """Pre-build SQLAlchemy column expressions so their lazy annotation/clause
    memoization fires BEFORE CrossHair starts exploring (eliminates the
    'Wrong node type' NotDeterministic aborts). Side-effect-free; ~a few seconds."""
    try:
        from sqlalchemy import inspect as sqla_inspect
        from sqlalchemy.orm import configure_mappers
    except Exception:
        return 0
    try:
        configure_mappers()
    except Exception:
        pass
    warmed = 0
    for cls in model_classes:
        try:
            columns = list(sqla_inspect(cls).columns)
        except Exception:
            continue
        for col in columns:
            try:
                attr = getattr(cls, col.key)
            except Exception:
                continue
            for build in (
                lambda a: a == None, lambda a: a != None,        # noqa: E711
                lambda a: a.is_(None), lambda a: a.isnot(None),
                lambda a: a.in_([]), lambda a: a.like(""),
                lambda a: a.asc(), lambda a: a.desc(),
                lambda a: a.__clause_element__(),
            ):
                try:
                    build(attr)
                except Exception:
                    pass
            warmed += 1
    return warmed
```

**Discover the classes model-agnostically** instead of hardcoding a list — from the declarative base / registry so it ports to any project:

```python
# SQLAlchemy 1.4+/2.x: every mapped class is reachable from the registry.
model_classes = [m.class_ for m in Base.registry.mappers]      # plain SQLAlchemy
# Flask-SQLAlchemy:    [m.class_ for m in db.Model.registry.mappers]
```

Call it right after you install the Session/Query stubs, e.g. `prewarm_expression_caches([m.class_ for m in Base.registry.mappers])`.

**Validation (Apache Superset, 34 models / 6 ORM-heavy DAO files).** Fresh matched A/B, identical settings, prewarm the only difference. NotDeterministic aborts per file went `annotation_layer 3→0, theme 3→0, database 1→0, report 2→0, tasks 1→0, tag 1→0` — **11 → 0, 100% eliminated.** No collateral: `tag.py` produced the identical real-findings set before and after, only the ND line disappeared; a deliberate-violation control confirmed the previously-aborted paths are now genuinely analyzed (CrossHair caught a planted false postcondition on the once-ND path).

**Try this before disabling the UUID patch (Pattern 2b).** Since Pattern 2b's `NotDeterministic` shares this root cause, prewarming the UUID columns (the `prewarm` loop already covers them) may let you *keep* the UUID patch and still analyze UUID-filtered files. Validated on non-UUID columns; treat the UUID case as "worth trying" rather than guaranteed.

**Generalization (any CrossHair + SQLAlchemy project).** This is not project-specific. Any contracted function that builds `Model.column == x`-style queries hits it. The broader principle: **CrossHair requires determinism, so any library with "first call differs from later calls" lazy caching can trigger `NotDeterministic` — pre-warm those caches before analysis begins.** SQLAlchemy is the most common offender; the same move applies to other memoizing libraries.

**Caveat — a second ND flavor.** Mock query terminals (`MockQuery.first()/.scalar()`) that mint a fresh `proxy_for_type(...)` per call can produce a *different* `NotDeterministic` whose `Previous stack tail` runs through `crosshair/objectproxy.py` (not `sqlalchemy/...`). Pre-warming does not address that one; if it appears, memoize the proxy result per `MockQuery` call-site (cache it on the instance) so repeated terminal calls return the same object. In the Superset validation this flavor did **not** survive once expression caches were warmed, so prewarm alone may suffice — add the proxy memoization only if `objectproxy.py`-stack ND blocks remain.

---

## Putting it all together — full plugin skeleton

```python
# crosshair_sqlalchemy_setup.py
import importlib
from crosshair import auditwall as _auditwall

# 1. Pre-import drivers + SQLAlchemy with auditwall off
_auditwall.disable_auditwall()
try:
    for _mod_name in (
        "ctypes", "ctypes.util",
        "cryptography",
        "psycopg", "psycopg2",
        "sqlalchemy", "sqlalchemy.engine", "sqlalchemy.orm",
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

# 2. Install Engine/Connection/Session stubs
_stubs = importlib.import_module("_crosshair_sa_stubs")

# 3. Pre-warm SQLAlchemy expression caches (Pattern 6) — eliminates the
#    NotDeterministic aborts from lazy annotation/clause memoization.
try:
    _stubs.prewarm_expression_caches(
        [m.class_ for m in _stubs.Base.registry.mappers]  # or db.Model.registry
    )
except Exception:
    pass
```

For mixed Django + SQLAlchemy projects (e.g. Mathesar), append the SQLAlchemy block to the existing `crosshair_django_setup.py` — see `crosshair-django/references/plugin-patterns.md` for the Django side.

---

## When to update this file

Add new entries when you encounter:
- A new SQLAlchemy-driven `NameError` from `get_type_hints()` (note the missing forward-ref name)
- A new native driver that needs pre-importing
- A new stub method that's commonly called but not yet covered (`Result.scalar_subquery`, `Session.merge`, etc.)
- A `NotDeterministic: Wrong node type` abort — read the `Previous stack tail`: a `sqlalchemy/.../annotation.py` tail is Pattern 6 (prewarm); a `crosshair/objectproxy.py` tail is the proxy-realization flavor (memoize `proxy_for_type` per `MockQuery` call-site, see Pattern 6 caveat)

Cite the symptom that prompted the addition so future debuggers can recognize the same failure.
