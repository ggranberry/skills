---
name: crosshair-lite
description: Lightweight CrossHair bug finder that skips ORM stubbing. Runs CrossHair directly on files with existing PEP 316 contracts, records successes and failures, and reports coverage (files attempted vs succeeded). Use crosshair-bugs instead for full database-aware symbolic execution. Not for unit testing, linting, or static type checking.
---

# CrossHair Lite

Lightweight bug finder that runs CrossHair symbolic execution on files that already have PEP 316 contracts, without database stubs. Finds contract files, runs CrossHair, and reports which files succeeded vs failed (needed stubs).

## Artifacts

All outputs are persisted to `.claude/artifacts/crosshair-lite/`:

```
crosshair-lite/
├── contract-files.json              # Phase 1 — discovered files with contracts
└── crosshair/
    ├── run_crosshair.sh             # Phase 2 — generated run script
    ├── crosshair-output-*.txt       # Phase 2 — raw CrossHair output per file
    ├── bugs-report.md               # Phase 3 — human-readable report
    └── coverage-report.json         # Phase 3 — machine-readable metrics
```

## Setup

```bash
mkdir -p .claude/artifacts/crosshair-lite/crosshair
```

## Workflow

**Copy this checklist into your response at the start and check off each phase as it completes:**

```
Phase Progress:
- [ ] Phase 1: Find contract files
- [ ] Phase 2: Run CrossHair
- [ ] Phase 3: Report
```

### Phase 1: Find Contract Files

Discover all Python files that already contain PEP 316 contracts (`pre:`, `post:`, `inv:` directives in docstrings).

1. Verify which top-level directories are source packages by listing them, then run:
   ```bash
   python3 ~/.claude/skills/crosshair-lite/scripts/find_contract_files.py \
     --packages <verified-packages> \
     --exclude-dirs <project-specific-dirs> \
     --output .claude/artifacts/crosshair-lite/contract-files.json
   ```

2. Read the output and report the summary to the user (files found, contract counts).

### Phase 2: Run CrossHair

1. **Ask the user** for the venv path:
   > "What is the path to the Python venv that has both crosshair and your project's dependencies installed? (e.g. `/home/user/project/venv`)"

2. **Generate the run script:**
   ```bash
   python3 ~/.claude/skills/crosshair-lite/scripts/generate_crosshair_lite_run.py <venv>
   ```

3. **Run CrossHair in parallel:** Read `run_crosshair.sh` and spawn one `run_in_background=true` Bash call per line, all in the same message. **Do NOT run `run_crosshair.sh` directly with bash** — that creates output file race conditions.

4. **Wait for every task notification** before proceeding to Phase 3.

### Phase 3: Report

Follow `~/.claude/skills/crosshair-lite/references/phase-3-report.md`.

## Resuming

- Phase 1 can be re-run at any time (overwrites `contract-files.json`)
- Phase 2: Re-run the generate script — it automatically skips files whose output already exists. Delete specific output files to force a re-check.
- Phase 3 can be re-run from existing output files.

## Post-Analysis

Do NOT remove PEP 316 contracts after analysis. Contracts serve as executable specifications and enable re-running CrossHair after code changes.
