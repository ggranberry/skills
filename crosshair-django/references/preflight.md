# CrossHair Django Pre-flight

Run these steps before generating the CrossHair run script. Skipping any step is the most common cause of cascading import errors and false positives.

---

## Step 1: Install All Project Dependencies into the CrossHair Venv

The single largest source of CrossHair noise in Django projects is missing packages. When an import fails, CrossHair cannot analyze the importing file — and every file that transitively imports it also fails. This cascades widely.

```bash
<venv>/bin/pip install -r requirements.txt
```

If the project has multiple requirements files (e.g. `requirements-dev.txt`, `requirements-optional.txt`), install them all. Do not rely on the project's existing venv — CrossHair needs its own copy with crosshair itself installed.

**Verify:** After installing, run a quick sanity check:

```bash
<venv>/bin/python -c "import django; import rest_framework; print('OK')"
```

---

## Step 2: Create the `crosshair_django_setup.py` Plugin

CrossHair must call `django.setup()` before analyzing any file that imports Django models, signals, or apps. Without this, every `AppRegistryNotReady` error is a false import failure.

Create `crosshair_django_setup.py` in the project root (or the directory you'll run crosshair from):

```python
# crosshair_django_setup.py
# CrossHair plugin: initializes Django before symbolic analysis.
import os
import django

# Set both the generic Django settings variable and any project-specific
# config env var the settings file reads at import time.
# Example for NetBox — adjust for your project:
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
os.environ.setdefault("NETBOX_CONFIGURATION", "netbox.configuration_testing")

# Only call setup() once even if the plugin is imported multiple times.
try:
    django.setup()
except RuntimeError:
    pass  # Already set up
```

**Project-specific env vars:** Check the project's `settings.py` (or equivalent) for any `os.environ.get(...)` calls at module level that affect which config file loads. All of those must be set here. For NetBox the key one is `NETBOX_CONFIGURATION`.

**Testing settings module:** Point `DJANGO_SETTINGS_MODULE` (or the equivalent) at a testing settings module that:
- Does NOT require a live PostgreSQL connection at import time
- Does NOT require a live Redis connection at import time
- Has `DEBUG = True` and permissive `ALLOWED_HOSTS`

NetBox uses `netbox.configuration_testing` for this purpose.

---

## Step 3: Pass `--extra_plugin` to Every CrossHair Command

Every `crosshair check` invocation must include:

```bash
--extra_plugin crosshair_django_setup.py
```

The `generate_crosshair_run.py` script already supports this flag — pass it as an argument:

```bash
python3 /home/jerj/.claude/skills/crosshair-bugs/scripts/generate_crosshair_run.py <venv> \
  --extra_plugin crosshair_django_setup.py
```

If the generate script does not yet support `--extra_plugin`, add the flag manually to the generated shell commands.

---

## Step 4: Add Standard `--unblock` Flags

Django and its dependencies perform OS and network calls during setup. Without these flags, CrossHair raises `SideEffectDetected` and aborts analysis.

Add to every `crosshair check` invocation:

```
--unblock subprocess.Popen
--unblock os.posix_spawn
--unblock socket.connect
--unblock socket.getaddrinfo
```

Full example invocation:

```bash
<venv>/bin/crosshair check path/to/file.py \
  --extra_plugin crosshair_django_setup.py \
  --unblock subprocess.Popen \
  --unblock os.posix_spawn \
  --unblock socket.connect \
  --unblock socket.getaddrinfo \
  --per_condition_timeout 30 \
  --analysis_kind PEP316 \
  > .claude/artifacts/crosshair-bugs/crosshair/crosshair-output-<slug>.txt 2>&1
```

---

## Step 5: Pre-import side-effect-laden modules in the plugin

`SideEffectDetected` errors from `ctypes`/`ldconfig`/`subprocess.Popen`/`/tmp` writes during native library loading (cairocffi, psycopg2, cryptography, SQLAlchemy dialects) are **not** permanent noise — they can be eliminated by pre-importing those modules with auditwall disabled inside the plugin.

See **`plugin-patterns.md` → Pattern 1** for the full code template. The short version: at the end of the plugin, do:

```python
from crosshair import auditwall as _auditwall
import importlib

_auditwall.disable_auditwall()
try:
    for _mod in ("cairocffi", "cairosvg", "psycopg2", "cryptography",
                 "sqlalchemy", "django.contrib.auth.hashers"):
        try:
            importlib.import_module(_mod)
        except ImportError:
            pass
    import ctypes.util as _ctypes_util
    _ctypes_util.find_library("c")
finally:
    _auditwall._ENABLED = True   # NB: engage_auditwall() does NOT re-arm
```

After this fix, `--unblock subprocess.Popen` and `--unblock os.posix_spawn` are usually unnecessary. If you still see a side-effect error, the traceback names the offending module — add it to the pre-import list.

Only treat `SideEffectDetected` as permanent noise when:
- The error originates from inside CrossHair-instrumented user code (not module import), AND
- Pre-importing the source module did not help.

---

## Checklist

Before running CrossHair on a Django project:

- [ ] All `requirements*.txt` installed into CrossHair venv
- [ ] `crosshair_django_setup.py` created with correct `DJANGO_SETTINGS_MODULE` and project config env var
- [ ] Testing settings module confirmed (no live DB/Redis required at import)
- [ ] `--extra_plugin crosshair_django_setup.py` added to every `crosshair check` command
- [ ] `--unblock` flags added for subprocess.Popen, os.posix_spawn, socket.connect, socket.getaddrinfo
- [ ] **Multiple `--unblock` events go after a SINGLE `--unblock` flag**, terminated with `--` before TARGET (see Pitfall below)
- [ ] ctypes/ldconfig side effects noted as permanent noise (not classified as bugs)

---

## Pitfall: `--unblock` argparse quirk

`crosshair check` defines `--unblock EVENT [EVENT ...]` with `nargs='+'`. Two failure modes that look completely different both trace back to this:

**Failure mode A — silent override:**
```bash
# Only the LAST --unblock=... takes effect; earlier ones are silently ignored.
crosshair check --unblock=open --unblock=subprocess.Popen target.py
```
Symptom: `ValueError: Unable to configure handler 'X'` from Django logging during plugin import (because `--unblock=open` was overridden by the later `--unblock=subprocess.Popen`).

**Failure mode B — TARGET consumed as event:**
```bash
# `target.py` is parsed as a third event; argparse complains TARGET is missing.
crosshair check --unblock open subprocess.Popen target.py
```
Symptom: `crosshair check: error: the following arguments are required: TARGET`.

**Right form:**
```bash
crosshair check \
  --extra_plugin crosshair_django_setup.py \
  --per_path_timeout 300 \
  --analysis_kind PEP316 \
  --unblock open subprocess.Popen -- \
  target.py
```

The `--` ends event collection so the positional argument is parsed correctly. In a Python runner script:

```python
cmd = [
    venv_python, "-m", "crosshair", "check",
    "--extra_plugin", plugin,
    "--per_path_timeout", "300",
    "--analysis_kind", "PEP316",
    "--unblock", "open", "subprocess.Popen", "--",
    str(target),
]
```

The `--` costs nothing and avoids both failure modes.
