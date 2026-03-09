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

## For Django: Create Registry Patch Files

If the ORM is Django (check `.claude/artifacts/crosshair-bugs/orm-detection.json`), also perform these steps **after** writing `_crosshair_stubs.py`:

### 1. Determine the Django settings module

Run:
```bash
grep -o "DJANGO_SETTINGS_MODULE[^'\"]*['\"][^'\"]*" manage.py | head -1
```
Extract the value (e.g. `myapp.settings.development`). If `manage.py` doesn't have it, check `.env` files or `pyproject.toml` for `DJANGO_SETTINGS_MODULE`.

### 2. Copy the registry patch module (verbatim, no rendering)

```bash
cp ~/.claude/skills/generate-stubs/templates/crosshair_registry_patch.py _crosshair_registry_patch.py
```

### 3. Render the CrossHair plugin template

Read `~/.claude/skills/generate-stubs/templates/crosshair_django_setup.py.jinja`, replace `{{ django_settings_module }}` with the value found in step 1, and write to `crosshair_django_setup.py` in the project root.

### 4. Validate both files

```bash
python -m py_compile _crosshair_registry_patch.py crosshair_django_setup.py
```

### Why these files are needed

- **Why not `django.setup()`**: Loads all INSTALLED_APPS, runs every `AppConfig.ready()` hook, configures logging — none of this is needed for symbolic execution.
- **The exec() scoping gotcha**: CrossHair `exec()`s the plugin inside `main()` without an explicit namespace. Class bodies in that context cannot see exec-local names for default arg evaluation (Python 3 limitation). The registry stubs **must** live in a real importable module (`_crosshair_registry_patch.py`), not defined inline in the plugin.
- **The all_models reference trick**: `_RegistryStubAppConfig.import_models()` stores a live reference to `apps.all_models[label]` (a dict). As Django imports real model files during the analysis import chain, they call `register_model()` which populates this same dict. Stub configs automatically see real models as they appear.
