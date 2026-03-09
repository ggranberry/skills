# Phase 9: Find Bugs

## Step 0: Django Setup (if ORM is Django)

If `orm-detection.json` identifies Django as the ORM, **complete the following before asking for the venv path:**

1. Read and follow `.claude/skills/crosshair-django/references/preflight.md` in full.
2. Confirm the pre-flight checklist is complete (dependencies installed, `crosshair_django_setup.py` created, testing settings confirmed).
3. When generating the run script in Step 2, pass `--extra_plugin crosshair_django_setup.py` to `generate_crosshair_run.py`. The script already supports this flag. Also ensure the four `--unblock` flags from the preflight are included in every generated `crosshair check` command.

Skip this step for non-Django ORMs.

---

## Step 1: Ask the user for the venv path

Before generating the run script, ask:

> "What is the path to the Python venv that has both crosshair and your project's dependencies installed? (e.g. `/home/user/project/venv`)"

Use the response as `<venv>`. The crosshair binary will be `<venv>/bin/crosshair`. Do not attempt to auto-detect it.

## Step 2: Generate the run script

Run this from the project root, passing the venv path as an argument:

```bash
python3 /home/jerj/.claude/skills/crosshair-bugs/scripts/generate_crosshair_run.py <venv>
```

The script prints the list of files it will run and any it skipped (output already exists). Review before continuing.

Output filenames use the full path slug to avoid basename collisions — `core/views.py` becomes `crosshair-output-core-views.py.txt`, not `crosshair-output-views.py.txt`.

**For large projects (more than ~30 files):** pass `--batch-size N` to group files into numbered batch scripts (`run_crosshair_1.sh`, `run_crosshair_2.sh`, ...) where each batch runs its files sequentially. Spawn one background task per batch instead of per file. A batch size of 10–15 keeps the number of concurrent tasks manageable while still providing parallelism across batches.

```bash
python3 /home/jerj/.claude/skills/crosshair-bugs/scripts/generate_crosshair_run.py <venv> --batch-size 10
```

## Step 2: Run CrossHair (Parallel)

**Do NOT run `run_crosshair.sh` directly with `bash` or with `&` backgrounding.** That approach creates output files immediately when the shell opens the redirect target, before the process has written anything — making it impossible to know when analysis is actually complete.

Instead, **read `run_crosshair.sh` and spawn one `run_in_background=true` Bash tool call per line**, all in the same message. Each call runs exactly one command, e.g.:

```bash
venv/bin/crosshair check api/serializers.py --extra_plugin crosshair_django_setup.py \
  --per_condition_timeout 30 --analysis_kind PEP316 \
  > .claude/artifacts/crosshair-bugs/crosshair/crosshair-output-api-serializers.py.txt 2>&1
```

Each call gets its own task ID. **Wait for every task notification (completed or failed) before proceeding to Step 3.** A file existing in the artifacts directory does not mean the process has finished writing to it.

**Resuming:** Re-run the generate script — it automatically skips files whose output already exists. Delete specific output files to force a re-check.

## Step 3: Parse Counterexamples

Read all `.claude/artifacts/crosshair-bugs/crosshair/crosshair-output-*.txt` files. For each counterexample found, extract:

- **Source file** and **line number**
- **Function name** (and class, if a method)
- **Contract violated** — the exact `pre:` / `post:` / `inv:` expression
- **Counterexample inputs** — the argument values CrossHair produced

Build a list of counterexample records. If there are no counterexamples across all files, skip to Step 5 and write an empty report.

## Step 4: Analyze Each Counterexample (Parallel)

Spawn one `general-purpose` agent per counterexample, all in parallel (single message).

Each agent receives:
- The counterexample record (file, line, function, contract, inputs)
- Path to the source file
- Path to the matching contract plan file (find `contract-plan-<basename>.md` under `.claude/artifacts/crosshair-bugs/plans/`)

Each agent must:
1. Read `.claude/skills/crosshair-bugs/references/phase-9-analysis-guide.md`
2. Read the source file (focusing on the function in question and its callers)
3. Read the contract plan file (for context on why the contract was written)
4. Read `_crosshair_stubs.py` (to understand what ORM behaviors are and aren't modeled)
5. Apply the classification questions from the analysis guide
6. Return a structured result:

```
FILE: <source file>
FUNCTION: <function name>
CONTRACT: <violated contract expression>
COUNTEREXAMPLE: <inputs CrossHair produced>
VERDICT: Real bug | False positive
SEVERITY: Critical | High | Medium | Low | False positive
REASONING: <2-4 sentences applying the classification questions>
SUGGESTED ACTION: <fix, tighten/loosen contract, or update stub>
```

## Step 5: Compile Report

Write to `.claude/artifacts/crosshair-bugs/crosshair/bugs-report.md` using results from all analysis agents:

```markdown
# CrossHair Bug Report

## Summary
- X counterexamples found across Y files
- Z likely real bugs (A critical, B high, C medium, D low)
- W likely false positives

## Bugs Found

### 1. [file:function_name] — [short description]
**Contract violated:** `pre: from_food != to_food`
**Counterexample:** `merge(food_id=1, food_id=1)`
**Reasoning:** When from_food == to_food, the ORM identity map returns the same object for both lookups. Deleting from_model also destroys to_model.
**Severity:** Critical — data loss.
**Suggested action:** Add guard `if from_food == to_food: return` at function entry.

### 2. ...

## False Positives

### 1. [file:function_name] — [short description]
**Contract violated:** `post: __return__ is not None`
**Counterexample:** `get_item(id=999)`
**Reasoning:** Stub returns `None` on miss; real ORM raises a not-found exception. The contract is correct but the stub doesn't model this path.
**Suggested action:** Update stub to raise the not-found exception instead of returning `None`.

## Files With No Violations
- [list of clean files]
```

## Important: Preserve Contracts

Do NOT remove PEP 316 contracts from source files after analysis. The contracts are valuable beyond a single CrossHair run:
- They document function expectations as executable specifications
- They enable re-running CrossHair after code changes to catch regressions
- They can be tightened or loosened based on the bug report findings

Only remove a contract if the user explicitly asks you to.
