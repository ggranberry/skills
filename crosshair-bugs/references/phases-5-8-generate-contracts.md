# Phases 5–8: Generate Contracts

Adds PEP 316 docstring contracts to business logic classes and functions so CrossHair can verify them symbolically against database stubs.

## Context Isolation

Each phase runs as a separate agent with its own context:

| Phase | Reads | Does NOT read |
|-------|-------|---------------|
| Phase 5 (Explore) | orm-detection.json, source files (via explore-contracts.py script) | schema-constraints.json, pep316-guide.md |
| Phase 5.5 (Chunk) | contract-targets.json | Everything else — just a Python script |
| Phase 6 (Plan) | planner-assignments.json (its assignment), schema-constraints.json, pep316-guide.md, **one source file**. Writes plan to `contract-plan-*.md`. | exclusions.md (already applied in Phase 5) |
| Phase 7 (Apply) | contract-plan-*.md, source files (to edit) | contract-targets.json, schema-constraints.json |
| Phase 8 (Validate) | Modified source files (via CrossHair CLI) | Everything else — this is just a bash command |

**Phase 5 outputs a lightweight manifest** (file paths, function names, signatures, line counts) — no embedded source. **Phase 5.5 splits the manifest into per-file assignments.** **Phase 6 reads one source file per agent**, giving full attention to every function. Phase 6 is the **only** phase that reads the PEP 316 guide.

---

## Phase 5: Explore (Discover Contract Candidates)

Discover all functions that could receive contracts. First verify which top-level packages are source code vs. infrastructure by listing directories and checking `orm-detection.json`, then run the explore script with the correct `--packages` and `--exclude-dirs`.

```bash
python .claude/skills/generate-contracts/scripts/explore-contracts.py \
  --packages <verified-packages> \
  --exclude-dirs <project-specific-dirs> \
  --output .claude/artifacts/crosshair-bugs/contract-targets.json
```

Read and follow `.claude/skills/generate-contracts/references/phase-1-explore.md` for the full verification + run workflow.

---

## Phase 5.5: Chunk Targets into Planner Assignments

Run the chunking script to split the Phase 5 manifest into per-file planner assignments. Each assignment scopes a single planner to one file (or one chunk of a large file).

```bash
python .claude/skills/generate-contracts/scripts/chunk-targets.py \
  --max-functions 30 \
  --targets .claude/artifacts/crosshair-bugs/contract-targets.json \
  --output .claude/artifacts/crosshair-bugs/planner-assignments.json
```

**Why one file per planner:** When planners are given batches of many files, they spread their attention too thin — complex functions get dismissed as "trivial" while simple functions get tautological contracts that just restate the return type or function body. One file per planner ensures every function gets careful reading.

**Large file chunking:** Files with more than `--max-functions` candidates (default 30) are split into chunks. Each chunk gets its own planner agent. This prevents any single planner from being overwhelmed by a file like `event_queue.py` with 40+ functions.

The script outputs `planner-assignments.json`:
```json
{
  "max_functions_per_assignment": 30,
  "total_assignments": 12,
  "total_functions": 182,
  "assignments": [
    {
      "id": "topic.py",
      "file": "zerver/lib/topic.py",
      "functions": ["generate_topic_history_from_db_rows", "..."],
      "function_count": 6,
      "output_file": "contract-plan-topic.py.md"
    }
  ]
}
```

---

## Phase 6: Plan Contracts (One Planner Per File — Batched)

There are typically hundreds of assignments. Each session processes a **batch**; progress is tracked automatically by checking which `contract-plan-*.md` files exist on disk.

1. **Get the next batch:**
   ```bash
   python .claude/skills/generate-contracts/scripts/batch-progress.py \
     --batch-size 10 \
     --artifacts-dir .claude/artifacts/crosshair-bugs/plans/
   ```
   The script prints a progress summary to stderr and outputs the next batch of assignments as JSON to stdout. If the batch is empty, all assignments are planned — move to Phase 7.

2. **Spawn planner agents** for every assignment in the batch, in parallel. Each agent focuses on **one file** (or one chunk of a large file) and produces its own plan file.

3. **Repeat** step 1–2 until the batch is empty or the session is ending.

The planner first triages each function as CONTRACT or SKIP (with reason), then designs contracts only for CONTRACT functions. Skipped functions are recorded in the output for auditability.

**This is the only phase that reads the PEP 316 guide** at `.claude/skills/generate-contracts/references/pep316-guide.md`.

**If the ORM is Django**, each planner agent must also read `.claude/skills/crosshair-django/references/precondition-patterns.md` alongside the PEP 316 guide. These patterns prevent the most common symbolic noise false positives in Django/DRF code: incorrect type guards for model instances, querysets, requests, and DRF views/fields; `isdigit()` vs `isdecimal()` for string-to-int coercions; and Unicode-unsafe string length postconditions.

Read and follow the prompt in `.claude/skills/generate-contracts/references/phase-2-plan.md`.

Each planner writes output to `.claude/artifacts/crosshair-bugs/plans/<output_file>` (from its assignment).

> **Do NOT skip assignments or cherry-pick "high-value" files.** The batch script decides ordering. Process every assignment it returns.

---

## Phase 7: Apply Contracts (Parallel by Source File)

Spawn one apply agent per unique source file — all in parallel in a single message. Grouping by source file prevents write conflicts when a large file was chunked into multiple plan files.

1. **Find pending work:** Read `planner-assignments.json`. For each assignment, check if its `output_file` exists under `.claude/artifacts/crosshair-bugs/plans/` and does NOT end with `## Applied`. Those are pending.

2. **Group by source file:** Collect all pending assignments and group them by `file`. Each group becomes one apply-agent's work.

3. **Spawn all apply agents in parallel** (single message, one Agent per unique source file). Pass the agent the list of plan file paths for its source file.

4. Each agent appends `## Applied` to its plan files after successfully applying them.

Read and follow the prompt in `.claude/skills/generate-contracts/references/phase-3-apply.md`.

---

## Phase 8: Validate Contract Syntax

Quick smoke test to confirm CrossHair can find and parse the contracts. This is NOT a bug-finding run — just a syntax check.

```bash
crosshair check <file> \
  --per_condition_timeout 1 \
  --analysis_kind PEP316 \
  2>&1
```

Run this on each file modified in Phase 7. Timeouts and "no violation found" are both fine — they mean the contract was parsed successfully.

---

## Resuming Phases 5–8

Progress is tracked by **file existence** — no separate state file needed:

- **Phase 6:** `batch-progress.py` diffs `planner-assignments.json` against existing `contract-plan-*.md` files. Assignments whose plan file already exists are skipped automatically.
- **Phase 7:** Plan files without a `## Applied` section at the end are pending. Already-applied plans are skipped.

Artifact dependencies:
- Phase 5.5+ can read `contract-targets.json`
- Phase 6+ can read `planner-assignments.json`
- Phase 7 can read `contract-plan-*.md`
