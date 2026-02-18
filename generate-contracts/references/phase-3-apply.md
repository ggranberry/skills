# Phase 3: Apply Contracts

Spawn as: `Task(subagent_type="general-purpose")`

Add PEP 316 docstring contracts to source files based on the plan.

## Instructions

1. Read `.claude/artifacts/crosshair-bugs/contract-plan.md`
2. For each file in the plan:
   a. Read the source file
   b. For each CLASS with invariants:
      - If the class has an existing docstring, append `inv:` lines after the description
        (separated by a blank line)
      - If the class has no docstring, add a docstring with just the `inv:` lines
   c. For each FUNCTION with pre/post conditions:
      - If the function has an existing docstring, append `pre:`/`post:` lines after the
        description (separated by a blank line)
      - If the function has no docstring, add a docstring with just the `pre:`/`post:` lines
   d. Write the updated file
   e. Validate: `python -m py_compile <file>`

   f. For each FUNCTION with planned `assert` statements:
      - Add the assertion at the location described in the plan (e.g., "end of loop body",
        "after the delete call")
      - Do NOT remove any existing `assert` statements

## Docstring rules

- Use triple double quotes
- Place contracts after any existing description text, separated by a blank line
- Put `pre:` lines before `post:` lines
- One condition per line
- Preserve existing indentation
- Do NOT modify function/method bodies — only add/update docstrings

## Error handling

If `py_compile` fails:
- Check for syntax errors in condition expressions
- Check docstring quoting and indentation
- Fix and re-validate before moving to next file
