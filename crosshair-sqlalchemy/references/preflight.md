# CrossHair SQLAlchemy Pre-flight

Run these steps before generating the CrossHair run script for a SQLAlchemy project. Skipping any step is the most common cause of cascading import errors and false-positive side-effect alerts.

---

## Step 1: Install all project dependencies into the CrossHair venv

The single largest source of CrossHair noise is missing packages. SQLAlchemy projects typically need at minimum:

```bash
<venv>/bin/pip install -r requirements.txt
```

If the project pins driver packages separately (`requirements-postgres.txt`, `requirements-mysql.txt`, etc.), install them all. SQLAlchemy itself is pure Python, but its drivers (psycopg2, asyncpg, oracledb, pymysql, mysqlclient) load native code at import time.

**Verify:**

```bash
<venv>/bin/python -c "import sqlalchemy; print(sqlalchemy.__version__)"
<venv>/bin/python -c "import psycopg2"  # or whichever driver(s) the project uses
```

---

## Step 2: Create or augment the CrossHair plugin

CrossHair plugins are exec'd via `--extra_plugin`. The plugin must:

1. Disable CrossHair's auditwall, pre-import side-effect-laden modules, then re-enable auditwall.
2. (Optional) Install ORM stubs for Engine/Connection/Session/Query.

For pure-SQLAlchemy projects, create `crosshair_sqlalchemy_setup.py`:

```python
# crosshair_sqlalchemy_setup.py
import importlib
from crosshair import auditwall as _auditwall

# Pre-import side-effect-laden modules with auditwall off.
# CrossHair arms its auditwall BEFORE exec'ing this plugin, so the only
# way to import these without tripping it is to disable the wall first.
_auditwall.disable_auditwall()
try:
    for _mod_name in (
        "ctypes", "ctypes.util",
        "cryptography", "cryptography.hazmat.backends.openssl",
        "psycopg", "psycopg2",
        "oracledb",            # if used
        "pymysql",             # if used
        "asyncpg",             # if used
        "sqlalchemy",
        "sqlalchemy.engine",
        "sqlalchemy.orm",
    ):
        try:
            importlib.import_module(_mod_name)
        except ImportError:
            pass  # Driver not installed in this env — skip.

    # Force ctypes.util.find_library to fork its ldconfig now (with the wall off)
    # so it doesn't trip on the first lazy invocation later.
    try:
        import ctypes.util as _ctypes_util
        _ctypes_util.find_library("c")
    except Exception:
        pass
finally:
    _auditwall._ENABLED = True   # NB: engage_auditwall() does NOT re-arm
```

For projects that **mix Django and SQLAlchemy** (e.g. Mathesar), put the SQLAlchemy block at the end of the existing `crosshair_django_setup.py`, after the Django registry patches and ORM stub import. Order matters: Django's stubs need to be installed before SQLAlchemy's introspection runs.

---

## Step 3: Pass `--extra_plugin` to every CrossHair command

```bash
<venv>/bin/crosshair check path/to/file.py \
  --extra_plugin crosshair_sqlalchemy_setup.py \
  --per_condition_timeout 30 \
  --analysis_kind PEP316
```

If the project has its own driver native-loader cycle (e.g. `oracledb.thick_mode` requiring `libclntsh`), add `oracledb` to the pre-import list and re-test before adding `--unblock` flags.

---

## Step 4: Add `--unblock` flags only for residual cases

After Step 2, most `subprocess.Popen` and `os.posix_spawn` events should disappear. If they don't, the traceback names the unimported source — add it to the pre-import block in Step 2 and rerun. Use `--unblock` only as a last resort:

```
--unblock subprocess.Popen
--unblock os.posix_spawn
--unblock socket.connect
--unblock socket.getaddrinfo
```

---

## Step 4b: Alternative — auto-load via `.pth` file

If the project doesn't want a long `--extra_plugin` arg on every CrossHair invocation, or the project tooling already wraps `crosshair check` in scripts that can't easily pass plugins, an alternative is to drop a `.pth` file in the CrossHair venv's site-packages that auto-imports the plugin at interpreter startup:

```bash
echo 'import crosshair_sqlalchemy_setup' \
  > <venv>/lib/python3.12/site-packages/_crosshair_sqlalchemy_autoload.pth
```

`site.py` honors `.pth` files containing `import <module>` lines on every interpreter startup, *before* CrossHair's `main()` runs. The plugin loads automatically; `--extra_plugin` becomes optional.

Caveat: this approach loads the plugin for *every* invocation of the venv's Python (including ad-hoc `<venv>/bin/python -c "..."` smoke tests). For most setups that's fine — `install_stubs()` is idempotent and adds <1s to startup — but if the project's tooling runs the same venv outside CrossHair, prefer the explicit `--extra_plugin` form.

Common silent failure to watch for: a `_crosshair_stubs.py` file existing at the repo root but never being imported (no `.pth`, no `--extra_plugin`, no test/conftest importing it). The stubs file's `install_stubs()` never runs, so all the `Model.query = MockQuery(...)` patches are inert, and every contracted ORM function falls back to the real SQLAlchemy machinery. Diagnose by checking whether the `print("... stubs installed ...")` line in `install_stubs()` appears in any CrossHair output.

---

## Step 4c: Suppress `logging` under tracing

CrossHair patches `time.time()` to return a `RealBasedSymbolicFloat`. Python's `logging.formatTime()` does `int(record.created)` on that, which raises `TypeError: 'RealBasedSymbolicFloat' object cannot be interpreted as an integer` — once per `logger.info()` call inside an analyzed function. For projects with chatty logging, this produces megabytes of TypeError tracebacks per CrossHair run and can fill the disk before CrossHair completes.

Fix: disable logging in the plugin, after the pre-import block:

```python
import logging
logging.disable(logging.CRITICAL)
```

This sets the threshold so no `Logger.<level>()` call produces a record. Safe under CrossHair because logging side effects are never part of the contract anyway.

---

## Step 5: Function-level targeting for whole-file scan failures

If `crosshair check path/to/file.py` exits with one of:

- `NameError: name 'FromClause' is not defined`
- `NameError: name 'TypeEngine' is not defined`
- `NameError: name 'ColumnElement' is not defined`
- `ValueError: wrong parameter order: keyword-only parameter before variadic positional parameter`

…this is CrossHair tripping on SQLAlchemy's heavy use of string-forward-ref annotations during proxy generation. The whole-file scan walks every class in the import graph; targeted scans only proxy the specific function's argument types and bypass the failure.

```bash
# Whole-file: trips internal bug
<venv>/bin/crosshair check db/queries.py --extra_plugin ...

# Function-level: works
<venv>/bin/crosshair check 'db.queries.build_select' --extra_plugin ...
```

When generating `run_crosshair.sh` in Phase 9, prefer function-level targets for SQLAlchemy modules whose whole-file scans fail.

---

## Checklist

Before running CrossHair on a SQLAlchemy project:

- [ ] All `requirements*.txt` installed into CrossHair venv (including driver packages)
- [ ] Plugin file pre-imports drivers with auditwall disabled (`_auditwall._ENABLED = True` to re-arm)
- [ ] Plugin loaded via `--extra_plugin` OR auto-loaded via a `.pth` file in venv site-packages
- [ ] Plugin calls `logging.disable(logging.CRITICAL)` to suppress symbolic-time-formatting noise
- [ ] For mixed Django+SQLAlchemy projects: Django pre-flight done first, SQLAlchemy block added to existing plugin
- [ ] `run_crosshair.sh` uses function-level targets for SQLAlchemy modules that fail whole-file scans
- [ ] `--unblock` flags only used for residual side effects after Step 2
