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
- Required `--unblock` flags for subprocess, socket, and OS calls
- Permanent noise to accept (ctypes/ldconfig `SideEffectDetected`)

---

## Contract Patterns

When Phase 6 planner agents write `pre:` conditions for Django/DRF code, they must also read:

**Reference:** `.claude/skills/crosshair-django/references/precondition-patterns.md`

This covers:
- `isinstance`/`hasattr` patterns for Django models, querysets, DRF views, DRF fields, request objects, template contexts, and SQL compilers
- `isdecimal()` vs `isdigit()` — Unicode digit false positives
- String `post:` length pitfalls (`str.upper()` on Unicode)

---

## Integration

`crosshair-bugs` integrates this skill at two points:

| Phase | Hook |
|-------|------|
| Phase 9 (Find Bugs) | Read `preflight.md` before generating the run script; include `--extra_plugin` and `--unblock` flags in generated commands |
| Phase 6 (Plan Contracts) | Each planner reads `precondition-patterns.md` alongside the PEP 316 guide |

See `crosshair-bugs/references/phase-9-find-bugs.md` and `crosshair-bugs/references/phases-5-8-generate-contracts.md` for the exact integration points.
