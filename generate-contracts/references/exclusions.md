# Mechanical Exclusions for Phase 1 Discovery

These exclusions are applied during the Explore phase to filter out functions and files that mechanically cannot benefit from contracts. Every rule here must be objective and deterministic — no subjective judgment.

**Default policy: If in doubt, INCLUDE.** The Planner will filter in Phase 2.

## Directory Exclusions

Skip entire directories:

- `tests/`, `test/` — test code, not business logic
- `migrations/`, `alembic/` — auto-generated migration files
- `static/`, `templates/`, `assets/` — non-Python assets
- `__pycache__/`, `.mypy_cache/`, `.pytest_cache/` — build/cache artifacts
- `node_modules/`, `.venv/`, `venv/` — dependency directories
- `.git/`, `.claude/` — tooling directories

## File Exclusions

Skip entire files:

- `__init__.py` — typically just re-exports
- `conftest.py` — test configuration
- `setup.py`, `setup.cfg`, `pyproject.toml` — packaging
- `manage.py` — CLI entry point boilerplate
- Files matching `*_test.py`, `test_*.py` — test files outside test directories

## Function/Method Exclusions

Skip individual functions or methods that match ANY of these:

### Dunder methods
- `__repr__`, `__str__`, `__hash__`, `__eq__`, `__lt__`, `__le__`, `__gt__`, `__ge__`, `__bool__`, `__len__`, `__contains__`
- `__init__` methods where every statement is `self.x = <param>` (pure field assignment). Exclude these. If `__init__` contains any other statements (conditionals, loops, function calls, computed values), INCLUDE it.

### Trivial bodies
- Single-line `return` (e.g., `return self.name`)
- Single-line `pass` or `...`
- Single-line `raise NotImplementedError`
- Property getters that just return a field

### Decorators that indicate non-business-logic
- `@property` with a trivial getter (single return)
- `@staticmethod` that's a one-liner
- `@validator` / `@field_validator` / `@model_validator` — Pydantic validators (schema layer, not business logic)

### Config and schema classes
- Classes that inherit from `BaseSettings`, `BaseModel` (Pydantic) and contain ONLY field declarations (no methods with logic)
- Enum classes with only value declarations
- Dataclasses with only field declarations and no methods

## Line Count Threshold

- Skip functions with **1 line** of body (after removing docstrings, comments, and blank lines)
- Include everything with 2+ lines of logic — the Planner decides if it's contract-worthy
