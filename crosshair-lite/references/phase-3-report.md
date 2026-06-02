# Phase 3: Report

Parse CrossHair outputs, classify results, analyze counterexamples, and compile both a human-readable report and a machine-readable JSON coverage file.

## Step 1: Parse and Classify Outputs

Read all `.claude/artifacts/crosshair-lite/crosshair/crosshair-output-*.txt` files. Classify each file's output into one of:

- **clean** — CrossHair ran successfully with no counterexamples (output is empty or contains only "no counterexamples found" messages)
- **counterexample** — CrossHair found one or more contract violations (output contains counterexample lines with function arguments)
- **execution-error** — CrossHair failed to execute the file (output contains `ImportError`, `ModuleNotFoundError`, `AttributeError`, traceback, or other Python exceptions indicating the code couldn't be symbolically analyzed)
- **timeout** — All conditions timed out without reaching a conclusion (output contains only timeout messages, no counterexamples and no errors)

For each counterexample found, extract:
- **Source file** and **line number**
- **Function name** (and class, if a method)
- **Contract violated** — the exact `pre:` / `post:` / `inv:` expression
- **Counterexample inputs** — the argument values CrossHair produced

Build a list of counterexample records.

---

## Step 2: Analyze Counterexamples (Parallel)

If there are no counterexamples, skip to Step 3.

Spawn one `general-purpose` agent per counterexample, all in parallel (single message).

Each agent receives:
- The counterexample record (file, line, function, contract, inputs)
- Path to the source file

Each agent must:
1. Read `~/.claude/skills/crosshair-lite/references/phase-3-analysis-guide.md`
2. Read the source file (focusing on the function in question and its callers)
3. Apply the classification questions from the analysis guide
4. Return a structured result:

```
FILE: <source file>
FUNCTION: <function name>
CONTRACT: <violated contract expression>
COUNTEREXAMPLE: <inputs CrossHair produced>
VERDICT: Real bug | False positive
SEVERITY: Critical | High | Medium | Low | False positive
REASONING: <2-4 sentences applying the classification questions>
SUGGESTED ACTION: <fix, tighten/loosen contract, or note environment limitation>
```

---

## Step 3: Compile Reports

Write two output files. Read `contract-files.json` for file/contract counts.

### 3a: Human-Readable Report

Write to `.claude/artifacts/crosshair-lite/crosshair/bugs-report.md`:

```markdown
# CrossHair Lite Report

## Coverage Summary

| Metric | Count |
|--------|-------|
| Files scanned for contracts | 142 |
| Files with PEP 316 contracts | 24 |
| Total contracts found | 87 |
| Files attempted (CrossHair ran) | 24 |
| Files succeeded (clean or counterexample) | 18 |
| Files with execution errors | 4 |
| Files timed out | 2 |
| **Success rate** | **75.0%** |
| **Error rate (likely need stubs)** | **16.7%** |

## Summary
- X counterexamples found across Y files
- Z likely real bugs (A critical, B high, C medium, D low)
- W likely false positives

## Bugs Found

### 1. [file:function_name] — [short description]
**Contract violated:** `pre: from_food != to_food`
**Counterexample:** `merge(food_id=1, food_id=1)`
**Reasoning:** When from_food == to_food, the function ...
**Severity:** Critical — data loss.
**Suggested action:** Add guard `if from_food == to_food: return` at function entry.

### 2. ...

## False Positives

### 1. [file:function_name] — [short description]
**Contract violated:** `post: __return__ is not None`
**Counterexample:** `get_item(id=999)`
**Reasoning:** Environment limitation — function calls external service that CrossHair cannot model.
**Suggested action:** This function needs stubs. Candidate for crosshair-bugs.

## Execution Errors
- `path/to/file.py` — ImportError: No module named 'django.db'
- `path/to/other.py` — AttributeError: 'NoneType' object has no attribute 'query'

## Files With No Violations
- path/to/clean_file.py
- path/to/another_clean.py
```

### 3b: Machine-Readable JSON

Write to `.claude/artifacts/crosshair-lite/crosshair/coverage-report.json`:

```json
{
  "summary": {
    "files_scanned": 142,
    "files_with_contracts": 24,
    "total_contracts": 87,
    "files_attempted": 24,
    "files_succeeded": 18,
    "files_with_errors": 4,
    "files_with_timeouts": 2,
    "success_rate": 0.75,
    "error_rate": 0.167,
    "counterexamples_found": 7,
    "likely_real_bugs": 3,
    "likely_false_positives": 4
  },
  "coverage": {
    "attempted": {
      "description": "Files with PEP 316 contracts that CrossHair was run on",
      "count": 24,
      "files": ["path/to/file1.py", "path/to/file2.py"]
    },
    "succeeded": {
      "description": "Files where CrossHair ran without execution errors",
      "count": 18,
      "files": ["path/to/file1.py", "path/to/file2.py"]
    },
    "failed": {
      "description": "Files where CrossHair hit execution errors (likely need stubs)",
      "count": 4,
      "files": [
        {
          "path": "path/to/file3.py",
          "error_summary": "ImportError: No module named 'django.db'",
          "contracts_in_file": 3
        }
      ]
    },
    "timed_out": {
      "description": "Files where all conditions timed out",
      "count": 2,
      "files": ["path/to/file5.py"]
    }
  },
  "counterexamples": [
    {
      "id": 1,
      "file": "myapp/utils/pricing.py",
      "function": "calculate_discount",
      "class_name": null,
      "line": 42,
      "contract": "post: __return__ >= 0",
      "inputs": "calculate_discount(price=-1, rate=0.5)",
      "verdict": "Real bug",
      "severity": "medium",
      "reasoning": "Negative price not guarded by precondition...",
      "suggested_action": "Add pre: price >= 0"
    }
  ],
  "false_positives": [
    {
      "file": "myapp/services/email.py",
      "function": "send_welcome",
      "line": 15,
      "contract": "post: __return__ is not None",
      "inputs": "send_welcome(user=User(...))",
      "reason": "environment_limitation",
      "reasoning": "Function calls external SMTP service"
    }
  ],
  "clean_files": [
    "path/to/clean_file.py",
    "path/to/another_clean.py"
  ],
  "error_files": [
    {
      "path": "path/to/file3.py",
      "error_summary": "ImportError: No module named 'django.db'"
    }
  ]
}
```

### Field Definitions

- `summary.success_rate`: `files_succeeded / files_attempted` (0.0–1.0)
- `summary.error_rate`: `files_with_errors / files_attempted` (0.0–1.0) — the key metric showing how many contracts couldn't run without stubs
- `coverage.attempted`: Files that had PEP 316 contracts and were run through CrossHair
- `coverage.succeeded`: Subset of attempted where CrossHair produced usable output (clean or counterexample)
- `coverage.failed`: Subset of attempted where CrossHair hit execution errors (likely need stubs from crosshair-bugs)
- `coverage.timed_out`: Subset of attempted where all conditions timed out
- Counterexamples are numbered with sequential `id` starting at 1, sorted by severity (critical first)

## Ordering

- Sort counterexamples/bugs by severity: critical first, then high, medium, low
- Within the same severity, group by file
- List all false positives after bugs
- List clean files last, alphabetically

## Important: Preserve Contracts

Do NOT remove PEP 316 contracts from source files after analysis. The contracts are valuable beyond a single CrossHair run:
- They document function expectations as executable specifications
- They enable re-running CrossHair after code changes to catch regressions
- They can be tightened or loosened based on findings

Only remove a contract if the user explicitly asks you to.
