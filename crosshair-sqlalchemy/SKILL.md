---
name: crosshair-sqlalchemy
description: SQLAlchemy-specific setup and contract patterns for CrossHair symbolic execution. Use when crosshair-bugs detects SQLAlchemy. Covers driver pre-loading, Engine/Connection/Session stubs, forward-ref NameErrors from string-typed annotations, and contract patterns for Query/Select/CursorResult. Not a standalone bug-finder — called from crosshair-bugs.
---

# CrossHair SQLAlchemy

SQLAlchemy-specific patterns for CrossHair symbolic execution. Captures fixes for native driver side effects (psycopg2 binary loader, oracledb, etc.), CrossHair internal failures triggered by SQLAlchemy's heavy use of string forward-reference annotations (`Optional["FromClause"]`), and stub patterns for the SQLAlchemy ORM hierarchy.

## When to Use

`crosshair-bugs` calls this skill automatically when Phase 1 (`orm-detection.json`) identifies SQLAlchemy as the ORM (or when both Django and SQLAlchemy are present, as in projects like Mathesar that mix the two).

It is not invoked for pure-Django projects, Peewee, or other ORMs.

---

## Pre-flight

Before generating the CrossHair run script or running any analysis, follow the setup guide:

**Reference:** `.claude/skills/crosshair-sqlalchemy/references/preflight.md`

This covers:
- Installing all project dependencies into the CrossHair venv (psycopg, psycopg2, oracledb, etc.)
- Creating or augmenting the `crosshair_*_setup.py` plugin to pre-import native drivers with auditwall disabled
- Required `--unblock` flags (and how Pattern 1 below makes most of them unnecessary)
- Cross-references to `crosshair-django/preflight.md` for projects that mix Django + SQLAlchemy (like Mathesar)

---

## Foundational rule for any stub

**Stubs must return `proxy_for_type(...)`, not concrete values.** A stub method that hardcodes a return value silently disables symbolic execution for every code path that branches on it.

**Reference:** `.claude/skills/crosshair-bugs/references/symbolic-stubs.md`

This rule applies to every stub class in this skill (`MockResult`, `MockConnection`, `MockSession`, `MockQuery`). Read `symbolic-stubs.md` before writing or extending any stub.

---

## Plugin patterns

When the basic setup isn't enough — `SideEffectDetected` from psycopg2/oracledb during dlopen, `NameError: name 'FromClause' is not defined` mid-analysis, whole-file scans that fail with `intersect_signatures` ValueError before reaching contracts — read:

**Reference:** `.claude/skills/crosshair-sqlalchemy/references/plugin-patterns.md`

This covers:
- **Pattern 1** — Pre-import native drivers (psycopg2, oracledb, pymysql, asyncpg) with auditwall disabled
- **Pattern 1b** — Patch `typing.get_type_hints` to swallow forward-ref `NameError`s (the **strictly better** alternative to function-level targeting)
- **Pattern 2** — Function-level targeting (fallback for whole-file scan failures when 1b isn't enough)
- **Pattern 2b caveat** — Why the Django UUID patch can crash SQLAlchemy filter analysis (and the `__slots__` / `__deepcopy__` fixups needed regardless)
- **Pattern 3** — Engine / Connection / Session / Query stubs (analog to Django's `MockManager`)
- **Pattern 4** — Skipping native bind-param adapters (`psycopg2.extras.Json`, `Numeric` decimals) under symbolic execution
- **Pattern 5** — Repository / DAO class hierarchy patches (resolves "Unable to meet precondition" on contracted repo methods by patching the repo `__init__` chain and pre-resolving `(schema, model)` from `__orig_bases__`)
- **Pattern 6** — Pre-warm expression caches to eliminate `NotDeterministic` aborts (the `Wrong node type … is ParallelNode` failures whose stack tail runs through `sqlalchemy/sql/annotation.py`); warms every mapped column's operators at install time. Validated 11→0 on Superset. Try before disabling the UUID patch (Pattern 2b).
- A complete plugin skeleton

---

## Contract patterns

When Phase 6 planner agents write `pre:` conditions for SQLAlchemy code:

**Reference:** `.claude/skills/crosshair-sqlalchemy/references/precondition-patterns.md`

This covers:
- `hasattr` guards for `Engine`, `Connection`, `Session`, `Query`, `Select`, `CursorResult`
- When to use `sqlalchemy.types.TypeEngine` vs duck-typing
- Expression construction safety (`column.in_([])` symbolic-list pitfall)
- `Result.scalar_one()` / `scalar_one_or_none()` postcondition patterns

---

## Integration

`crosshair-bugs` integrates this skill at two points:

| Phase | Hook |
|-------|------|
| Phase 9 (Find Bugs) | Read `preflight.md` before generating the run script; include `--extra_plugin` and pre-import block |
| Phase 6 (Plan Contracts) | Each planner reads `precondition-patterns.md` alongside the PEP 316 guide |

For projects that use **both Django and SQLAlchemy** (e.g. Mathesar, where Django runs the application layer and SQLAlchemy handles direct database introspection), invoke both skills' pre-flight steps in order: `crosshair-django/preflight.md` first (to set up Django), then this skill's preflight (to pre-load SQLAlchemy drivers).
