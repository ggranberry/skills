---
name: generate-stubs
description: Generate CrossHair stubs for ORM database calls. Use when preparing for CrossHair symbolic execution or asked to create database stubs. Not for mocking in unit tests or generating test fixtures.
---

# Generate Stubs

Generates Python stub files that replace ORM database calls with symbolic values for CrossHair analysis.

## Purpose

CrossHair performs symbolic execution but cannot analyze real database calls. These stubs:

1. **Replace ORM methods** (`.first()`, `.all()`, `.get()`) with symbolic returns via `proxy_for_type()`
2. **Apply database constraints** to the symbolic state space via `context_statespace().add()`

This ensures CrossHair explores code paths with realistic database values that respect schema constraints.

## Workflow

### Phase 1: Explore (Gather ORM + Schema)

Follow `.claude/skills/generate-stubs/references/phase-1-explore.md`

### Phase 2: Generate Base Stubs

Follow `.claude/skills/generate-stubs/references/phase-2-generate-base.md`

### Phase 3: Plan Constraints

Follow `.claude/skills/generate-stubs/references/phase-3-plan-constraints.md`

### Phase 4: Integrate Constraints

Follow `.claude/skills/generate-stubs/references/phase-4-integrate.md`

## Templates

Templates are in `.claude/skills/generate-stubs/templates/`:

- `sqlalchemy_stubs.py.jinja` — SQLAlchemy/Flask-SQLAlchemy
- `django_stubs.py.jinja` — Django ORM

## Output

Final `_crosshair_stubs.py` contains:
- Symbolic query/session classes
- Constraint application function
- Auto-install on import

Usage:
```python
# In conftest.py or test setup
import _crosshair_stubs  # Auto-installs stubs
```
