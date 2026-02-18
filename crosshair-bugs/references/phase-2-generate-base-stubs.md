# Phase 2: Generate Base Stubs

Spawn as: `Task(subagent_type="general-purpose")`

Create base CrossHair stub file.

## Instructions

1. Read `.claude/artifacts/crosshair-bugs/orm-detection.json`
2. Identify ORM type and model files
3. Read template: `.claude/skills/generate-stubs/templates/[orm]_stubs.py.jinja`
4. For each model file, extract:
   - Class name (e.g., User)
   - Module path (e.g., conduit.user.models)
5. Fill template with model info
6. Write to `_crosshair_stubs.py`
7. Validate: `python -m py_compile _crosshair_stubs.py`

Do NOT add constraints — just the base stub structure.
