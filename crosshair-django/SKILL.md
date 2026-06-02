---
name: crosshair-django
description: Django/DRF-specific setup and contract patterns for CrossHair symbolic execution. Use when crosshair-bugs detects Django ORM. Covers venv pre-flight, django.setup() plugin, unblock flags, and precondition patterns for Django models, DRF serializers, and request objects. Not a standalone bug-finder — called from crosshair-bugs.
---

# CrossHair Django

Django-specific patterns for CrossHair symbolic execution. This skill captures idioms discovered across multiple NetBox analysis sessions to eliminate false-positive noise caused by missing Django setup, missing packages, and unmodeled ORM types.

## When to Use

`crosshair-bugs` calls this skill automatically when Phase 1 (`orm-detection.json`) identifies Django as the ORM. It is not invoked for SQLAlchemy, Peewee, or other ORMs.

---

## Pre-flight

Before generating the CrossHair run script or running any analysis, follow the setup guide:

**Reference:** `.claude/skills/crosshair-django/references/preflight.md`

This covers:
- Installing all project dependencies into the CrossHair venv
- Creating the `crosshair_django_setup.py` plugin (sets `DJANGO_SETTINGS_MODULE` + project config env var, calls `django.setup()`)
- Choosing a testing settings module that avoids live DB/Redis
- Pre-importing side-effect-laden modules in the plugin
- When `--unblock` flags are still needed

---

## Foundational rule for any stub

**Stubs must return `proxy_for_type(...)`, not concrete values.** A stub that hardcodes `is_authenticated = True` silently disables symbolic execution for every code path that branches on it.

**Reference:** `.claude/skills/crosshair-bugs/references/symbolic-stubs.md`

This rule applies to every Mock class in this skill (`MockManager`, `MockQuerySet`, `MockUser`, `MockRequest`, etc.). Read `symbolic-stubs.md` before writing any new stub or extending an existing one.

---

## Plugin patterns

When the basic plugin from `preflight.md` isn't enough — e.g. import errors from `allauth.SOCIALACCOUNT_ENABLED`, `SideEffectDetected` from cairocffi/psycopg2, `AppRegistryNotReady` despite `django.setup()`, or whole-file `crosshair check` runs that fail with internal CrossHair errors before reaching contracts — read:

**Reference:** `.claude/skills/crosshair-django/references/plugin-patterns.md`

This covers:
- **Pattern 0** — `TEST=True` env var to disable background-thread decorators (`maintain_models`, `wire_analytics`, etc.). Threads spawned by these decorators run outside CrossHair's per-thread state space and crash with `AttributeError: '_thread._local' object has no attribute 'space'`, flooding output and stalling analysis. Required for analyzing any RPC endpoint decorated with such wrappers.
- **Pattern 1** — `SECRET_KEY` env var to skip auto-generation file writes
- **Pattern 2** — `apps.is_installed()` allow-list for feature-flag apps (allauth)
- **Pattern 3** — Stubbing `apps.get_containing_app_config` and `get_app_config` to skip full `django.setup()`
- **Pattern 4** — exec scope gotcha (CrossHair `exec()`s the plugin; class bodies can't see exec-local names — use a sibling module)
- **Pattern 5** — ORM stub auto-loading via `importlib.import_module`
- **Pattern 5b** — `django.core.cache.cache` no-op stub (defeats `NotDeterministic` in rate-limit decorators)
- **Pattern 5c** — `django.db.transaction.atomic` passthrough (no DATABASES engine needed)
- **Pattern 5d** — FK descriptor `__get__` patch so `instance.fk_field` returns a symbolic proxy instead of a DB query (use `field.name`, not `get_cache_name()`; patch both `ForwardManyToOneDescriptor` and `ForwardOneToOneDescriptor`)
- **Pattern 5e** — `timezone.now` patch must return `proxy_for_type(datetime)`, not concrete; mismatched types break `dt - timedelta`. `tzinfo.utcoffset(dt)` C-level check is unfixable; document as FP.
- **Pattern 5f** — `register_type(HttpRequest, factory)` to pre-populate user/session/POST/GET/META/headers/method/path/body so views with `def view(request: HttpRequest, ...)` are analyzable. Several attrs are properties (body, scheme, content_type, encoding) that need `instance.__dict__[k] = v` writes to bypass the property setter.
- **Pattern 5g** — `proxy_for_type(SomeDjangoModel)` crashes with `ValueError: wrong parameter order: keyword-only parameter before variadic positional parameter` because Django's synthesized `__init__` signature can't be intersected by `inspect.Signature`. Three workarounds: (A) `register_type` + `__new__` bypass for whole-codebase analysis, (B) build `SimpleNamespace` mocks field-by-field for targeted iteration stubs, (C) `pre: arg is None` to skip the model-arg branch entirely. Fires during analysis AND during `deep_realize` for counterexample formatting.
- **Pattern 6** — Auditwall pre-import for native dependencies (cross-reference to SQLAlchemy skill)
- **Pattern 7** — Function-level targeting bypasses CrossHair internal bugs (cross-reference)
- **Pattern 8** — Stubbing free-function connection helpers (e.g. `db.connection.exec_msar_func`, `mathesar_connection`): patching the source module is not enough — `from X import Y` captures the original at the importer's load time, so every module that did `from X import Y` must be re-bound too. Includes `_StubConnection` / `_StubCursor` shapes for the `with conn: c.execute(sql).fetchone()` pattern. Pairs with Pattern 5g so `@property connection` accesses don't `psycopg.connect()`.
- **Pattern 9** — Stub Django built-in models (`Session`, `Group`, `Permission`, `ContentType`, `Site`, `LogEntry`) explicitly. Stub generators only walk project `models.py` files, so calls like `Session.objects.get(...)` hit a real Django `Manager` and raise `ImproperlyConfigured: settings.DATABASES`. Includes the caveat that reverse-relation accessors (`session.downloadlink_set.add(...)`) still need `_patch_reverse_relations` wiring — `MockManager.add()` alone isn't reached by the descriptor.
- A complete plugin skeleton combining all patterns

---

## Contract Patterns

When Phase 6 planner agents write `pre:` conditions for Django/DRF code, they must also read:

**Reference:** `.claude/skills/crosshair-django/references/precondition-patterns.md`

This covers:
- `isinstance`/`hasattr` patterns for Django models, querysets, DRF views, DRF fields, request objects, template contexts, and SQL compilers
- `isdecimal()` vs `isdigit()` — Unicode digit false positives
- String `post:` length pitfalls (`str.upper()` on Unicode)

---

## Reverse relations & queryset projections

The auto-generated `_crosshair_stubs.py` covers more than `Model.objects.*`: reverse FK / M2M / OneToOne accessors (`project.check_set`, `user.profile`), forward M2M fields, queryset iteration (`for x in qs`), and field-typed `values_list(..., flat=True)` projections all work symbolically. Before contracting code that uses any of these, check what the stubs do and don't model:

**Reference:** `.claude/skills/crosshair-django/references/reverse-relations.md`

This covers:
- What `_patch_reverse_relations` patches (and what it skips — `related_name='+'`)
- Which `MockQuerySet` / `MockManager` methods are available (chainables, terminals, M2M mutators, iteration)
- The Django-field → Python-type mapping used by `values_list(flat=True)`
- Known limits (multi-field tuples, OneToOne constraint application, M2M write-state assertions)
- Cross-reference to the runtime code in `generate-stubs/templates/django_stubs.py.jinja`

---

## Integration

`crosshair-bugs` integrates this skill at two points:

| Phase | Hook |
|-------|------|
| Phase 9 (Find Bugs) | Read `preflight.md` before generating the run script; include `--extra_plugin` and `--unblock` flags in generated commands |
| Phase 6 (Plan Contracts) | Each planner reads `precondition-patterns.md` alongside the PEP 316 guide |

See `crosshair-bugs/references/phase-9-find-bugs.md` and `crosshair-bugs/references/phases-5-8-generate-contracts.md` for the exact integration points.
