# Phase 2: Analyze

Spawn specialized bug-finding agents per file to look for four classes of bugs.

## Step 1: Read targets

Read `.claude/artifacts/ai-bugs/file-targets.json` to get the list of files.

## Step 2: Batch and spawn agents

**Batching:** Process files in batches of 10. For each batch, spawn agents in parallel (single message).

**Per file:** Spawn 4 `general-purpose` agents in parallel, one per bug class:
1. Logic Errors
2. Edge Cases
3. Data Integrity
4. Error Handling

Each agent receives this prompt template (fill in the blanks):

```
You are a Python bug-finding agent specializing in {BUG_CLASS}.

Read the file at `{FILE_PATH}`.
Then read your analysis instructions from `/home/jerj/.claude/skills/ai-bugs/references/phase-2-agent-prompts.md` — read ONLY the "{BUG_CLASS_HEADING}" section.

Follow those instructions to analyze the file. For each bug you find, construct a concrete trigger — specific argument values or conditions that would expose the bug.

Return your findings as a JSON object (and nothing else) in this exact format:

{
  "file": "{FILE_PATH}",
  "bug_class": "{BUG_CLASS_KEY}",
  "findings": [
    {
      "function": "function_name",
      "line": 42,
      "class_name": "ClassName or null",
      "description": "What the bug is",
      "trigger": "function_call(arg=value) that triggers it",
      "expected_behavior": "What should happen",
      "actual_behavior": "What actually happens",
      "confidence": "high|medium|low"
    }
  ]
}

If you find no bugs in your class, return an empty findings array. Do NOT invent bugs.
```

Bug class mappings:
| Bug Class | BUG_CLASS_KEY | BUG_CLASS_HEADING |
|-----------|---------------|-------------------|
| Logic Errors | `logic_errors` | Logic Errors Agent |
| Edge Cases | `edge_cases` | Edge Cases Agent |
| Data Integrity | `data_integrity` | Data Integrity Agent |
| Error Handling | `error_handling` | Error Handling Agent |

## Step 3: Merge findings per file

After all 4 agents return for a file, merge their findings into a single `findings/raw-<slug>.json`:

```json
{
  "file": "path/to/file.py",
  "findings": [
    // ... all findings from all 4 agents, with bug_class preserved on each
  ],
  "analyzed_at": "ISO timestamp"
}
```

## File-existence progress tracking

Skip files where `findings/raw-<slug>.json` already exists. Delete specific files to force re-analysis.

## Batching for large projects

For projects with more than 10 files, process in batches of 10 to keep the number of concurrent agents manageable (40 agents per batch). Wait for each batch to complete before starting the next.
