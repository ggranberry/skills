# Phase 9: Find Bugs

## Step 1: Run CrossHair (Bash)

Collect the list of contracted files from the contract plan:

```bash
grep '^### ' .claude/artifacts/crosshair-bugs/contract-plan.md | \
  sed 's/^### //' | sort -u > /tmp/contracted_files.txt
```

Run CrossHair on each file with stubs loaded:

```bash
while IFS= read -r file; do
  echo "=== Checking: $file ==="
  crosshair check "$file" \
    --per_condition_timeout 30 \
    --analysis_kind PEP316 \
    2>&1
  echo ""
done < /tmp/contracted_files.txt | tee .claude/artifacts/crosshair-bugs/crosshair-raw-output.txt
```

## Step 2: Analyze Results

Spawn as: `Task(subagent_type="Plan")`

Analyze CrossHair output and produce a bug report.

### Instructions

1. Read `.claude/artifacts/crosshair-bugs/crosshair-raw-output.txt`
2. Read `.claude/artifacts/crosshair-bugs/contract-plan.md` (for context on what each contract checks)

For each counterexample CrossHair found:
- Identify the function and which contract was violated (pre/post/inv)
- Show the counterexample inputs CrossHair produced
- Explain what the bug means in plain language
- Assess severity: is this a real bug, an edge case, or a likely false positive from an over-strict contract?

### Output

Write to `.claude/artifacts/crosshair-bugs/bugs-report.md`:

```markdown
# CrossHair Bug Report

## Summary
- X counterexamples found across Y files
- Z likely real bugs, W likely false positives

## Bugs Found

### 1. [file:function_name] — [short description]
**Contract violated:** `pre: from_food != to_food`
**Counterexample:** `merge(food_id, food_id)`
**Explanation:** When from_food == to_food, SQLAlchemy's identity map returns the same
object for both lookups. session.delete(from_model) deletes the food.
**Severity:** Real bug — data loss.

### 2. ...

## Likely False Positives
- [file:function_name] — contract may be too strict because [reason]

## Files With No Violations
- [list of clean files]
```

Present findings clearly so the user can act on real bugs and adjust over-strict contracts.

## Important: Preserve Contracts

Do NOT remove PEP 316 contracts from source files after analysis. The contracts are valuable beyond a single CrossHair run:
- They document function expectations as executable specifications
- They enable re-running CrossHair after code changes to catch regressions
- They can be tightened or loosened based on the bug report findings

Only remove a contract if the user explicitly asks you to.
