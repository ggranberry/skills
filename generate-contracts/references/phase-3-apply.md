# Phase 3: Apply Contracts

Spawn as: `Task(subagent_type="general-purpose")`

Add PEP 316 docstring contracts to a single source file based on one or more plan files.

## Inputs

The orchestrator passes you:
- **Source file path** — the file to modify
- **Plan file paths** — one or more `.claude/artifacts/crosshair-bugs/contract-plan-*.md` files, all targeting this source file (multiple when the file was chunked into several planner assignments)

## Instructions

1. Read all plan files passed to you.
2. Read the source file.
3. Apply all contracts from all plan files to the source file:
   a. For each CLASS with invariants:
      - If the class has an existing docstring, append `inv:` lines after the description
        (separated by a blank line)
      - If the class has no docstring, add a docstring with just the `inv:` lines
   b. For each FUNCTION with pre/post conditions:
      - If the function has an existing docstring, append `pre:`/`post:` lines after the
        description (separated by a blank line)
      - If the function has no docstring, add a docstring with just the `pre:`/`post:` lines
4. Write the updated source file.
5. Validate: `python -m py_compile <file>`
6. For each FUNCTION with planned `assert` statements:
   - Add the assertion at the location described in the plan (e.g., "end of loop body",
     "after the delete call")
   - Do NOT remove any existing `assert` statements

## Docstring rules

- Use triple double quotes
- Place contracts after any existing description text, separated by a blank line
- Put `pre:` lines before `post:` lines
- One condition per line
- Preserve existing indentation
- Do NOT modify function/method bodies — only add/update docstrings and planned assertions

## Error handling

If `py_compile` fails:
- Check for syntax errors in condition expressions
- Check docstring quoting and indentation
- Fix and re-validate before marking plans as applied

## Marking plans as applied

After successfully applying all contracts and validating, append the following to **each** plan file:

```
## Applied
```

This marks the plan as processed so future sessions skip it.
