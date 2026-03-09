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

## For Django: Create Registry Patch Files

If the ORM is Django, also perform these steps **after** writing `_crosshair_stubs.py`:

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

## Output

`_crosshair_stubs.py` with:
- MockQuery/MockQuerySet classes (chainable + terminal methods)
- MockSession/MockManager classes
- `install_stubs()` function to monkey-patch models
- Placeholder for constraint application (filled in Phase 4)

For Django projects, also:
- `_crosshair_registry_patch.py` — pure Python stub classes (no Django deps), importable module
- `crosshair_django_setup.py` — CrossHair `--extra_plugin` that patches the Django app registry
