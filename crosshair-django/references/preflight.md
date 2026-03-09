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

## Step 5: Accept ctypes/ldconfig `SideEffectDetected` as Permanent Noise

Some Django/system calls (particularly those that load shared libraries via `ctypes` or invoke `ldconfig`) produce `SideEffectDetected` errors that cannot be suppressed with `--unblock`. These are permanent noise:

```
SideEffectDetected: ctypes.CDLL(...)
SideEffectDetected: subprocess.run(['ldconfig', ...])
```

**Do not treat these as bugs or false positives.** They are framework-level library loading that CrossHair cannot model. When classifying counterexamples in Phase 9, mark any finding whose root cause is a `ctypes`/`ldconfig` side effect as **infrastructure noise** and exclude it from the bug report.

---

## Checklist

Before running CrossHair on a Django project:

- [ ] All `requirements*.txt` installed into CrossHair venv
- [ ] `crosshair_django_setup.py` created with correct `DJANGO_SETTINGS_MODULE` and project config env var
- [ ] Testing settings module confirmed (no live DB/Redis required at import)
- [ ] `--extra_plugin crosshair_django_setup.py` added to every `crosshair check` command
- [ ] `--unblock` flags added for subprocess.Popen, os.posix_spawn, socket.connect, socket.getaddrinfo
- [ ] ctypes/ldconfig side effects noted as permanent noise (not classified as bugs)
