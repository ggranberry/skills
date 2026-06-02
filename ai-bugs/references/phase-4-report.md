# Phase 4: Compile Report

Read all `findings/verified-<slug>.json` files and compile the final bug report.

## Step 1: Aggregate

Read all verified findings files. Collect:
- Total files analyzed (from `file-targets.json`)
- Files with findings vs clean files
- Real bugs by severity
- False positives by reason

## Step 2: Write report

Write to `.claude/artifacts/ai-bugs/bugs-report.md` using this format:

```markdown
# AI Bug Analysis Report

## Summary
- X files analyzed, Y files with findings
- A likely real bugs (B critical, C high, D medium, E low)
- F likely false positives

## Bugs Found

### 1. [file:class_name.function_name] — [short description]
**Bug class:** Logic error
**Line:** 42
**Trigger:** `merge_foods(from_id=5, to_id=5)`
**Proof:**
\```python
svc = FoodService()
svc.merge_foods(from_id=5, to_id=5)  # deletes the only record
\```
**Reasoning:** When from_id == to_id, the function fetches the same record for both,
then deletes from_record (which IS to_record). Data loss.
**Severity:** Critical — data loss.
**Suggested action:** Add guard `if from_id == to_id: return` at function entry.

### 2. ...

## False Positives

### 1. [file:function_name] — [short description]
**Bug class:** Edge cases
**Reason:** Already guarded — line 90 checks for None before proceeding.

### 2. ...

## Files Analyzed With No Findings
- path/to/clean_file.py
- path/to/another_clean.py
```

## Step 3: Write JSON report

Write to `.claude/artifacts/ai-bugs/bugs-report.json` with this schema:

```json
{
  "summary": {
    "files_analyzed": 42,
    "files_with_findings": 8,
    "total_bugs": 12,
    "total_false_positives": 5,
    "bugs_by_severity": {
      "critical": 1,
      "high": 3,
      "medium": 5,
      "low": 3
    },
    "bugs_by_class": {
      "logic_errors": 4,
      "edge_cases": 3,
      "data_integrity": 2,
      "error_handling": 3
    }
  },
  "bugs": [
    {
      "id": 1,
      "file": "path/to/file.py",
      "function": "merge_foods",
      "class_name": "FoodService",
      "line": 42,
      "bug_class": "logic_errors",
      "severity": "critical",
      "description": "When from_id equals to_id, deletes the target record",
      "trigger": "merge_foods(from_id=5, to_id=5)",
      "proof_snippet": "svc = FoodService()\nsvc.merge_foods(from_id=5, to_id=5)",
      "reasoning": "Q1: reachable. Q2: no guard. Q3: data loss. Q4: proof constructed.",
      "suggested_action": "Add guard if from_id == to_id: return"
    }
  ],
  "false_positives": [
    {
      "file": "path/to/file.py",
      "function": "get_item",
      "line": 88,
      "bug_class": "edge_cases",
      "description": "Original finding description",
      "reason": "already_guarded",
      "reasoning": "Line 90 checks for None before proceeding"
    }
  ],
  "clean_files": [
    "path/to/clean_file.py"
  ]
}
```

Bugs are numbered with sequential `id` starting at 1, sorted by severity (critical first).

## Ordering

- Sort bugs by severity: critical first, then high, medium, low.
- Within the same severity, group by file.
- List all false positives after bugs.
- List clean files last, alphabetically.
