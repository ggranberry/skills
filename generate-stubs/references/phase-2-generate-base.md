# Phase 2: Generate Base Stub File

Spawn as: `Task(subagent_type="general-purpose")`

Create the base stub file from a template. Do NOT add constraint logic — that comes in Phase 3.

## Inputs

1. ORM type and schema JSON from Phase 1
2. Template: `.claude/skills/generate-stubs/templates/{{ orm }}_stubs.py.jinja`

## Instructions

1. Read the appropriate template for the detected ORM
2. Fill template with:
   - project_name
   - timestamp (current time)
   - models (for import statements and MockQuery setup)
   - session_module, session_name
   - crud_mixin_module (if present)
3. Write to `_crosshair_stubs.py`
4. Validate: `python -m py_compile _crosshair_stubs.py`

## Output

`_crosshair_stubs.py` with:
- MockQuery/MockQuerySet classes (chainable + terminal methods)
- MockSession/MockManager classes
- `install_stubs()` function to monkey-patch models
- Placeholder for constraint application (filled in Phase 4)
