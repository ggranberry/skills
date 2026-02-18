# Phase 1: Explore — Discover Contract Candidates

Spawn as: `Task(subagent_type="Explore")`

Perform a broad, mechanical sweep of the project to produce a manifest of all functions and methods that could potentially receive contracts. Do NOT judge whether a function is "contract-worthy" — that decision belongs to the Planner in Phase 2.

## Discovery Strategy

### Step 1: Find the source root

Read `.claude/artifacts/crosshair-bugs/orm-detection.json` to get the list of model files. Determine the project's source root: the top-level package directory that contains the model files. For example, if model files are at `mealie/db/models/recipe/recipe.py`, the source root is `mealie/`.

### Step 2: Scan for Python files

Starting from the source root, find all `.py` files that contain function or method definitions (`def `). Include sibling directories at the same level if they appear to be part of the same project (share the same parent, contain `__init__.py`).

### Step 3: Apply mechanical exclusions

Read `.claude/skills/generate-contracts/references/exclusions.md` and apply all exclusion rules. These are purely mechanical — directory exclusions, file exclusions, trivial-body exclusions, etc.

**Key principle:** When in doubt, INCLUDE. The Planner filters in Phase 2.

### Step 4: Extract function metadata

For each non-excluded Python file, extract every non-excluded function and method definition:

- **name**: Qualified name (`ClassName.method_name` for methods, `function_name` for top-level)
- **signature**: Parameter list as written in source
- **line_number**: Line where `def` appears
- **line_count**: Number of lines in the function body (from `def` to the last line before the next definition or dedent)
- **has_existing_docstring**: Whether the function already has a docstring

Do NOT include full source code. The manifest must be lightweight.

## Output Format

Write to `.claude/artifacts/crosshair-bugs/contract-targets.json`:

```json
{
  "source_root": "mealie/",
  "total_files_scanned": 142,
  "total_functions_found": 387,
  "total_functions_excluded": 203,
  "files": [
    {
      "path": "mealie/repos/repository_foods.py",
      "functions": [
        {
          "name": "RepositoryFood.merge",
          "signature": "(self, from_food: UUID4, to_food: UUID4)",
          "line_number": 45,
          "line_count": 22,
          "has_existing_docstring": false
        },
        {
          "name": "RepositoryFood.by_group",
          "signature": "(self, group_id: UUID4, search: str | None = None)",
          "line_number": 70,
          "line_count": 8,
          "has_existing_docstring": false
        }
      ]
    }
  ]
}
```

**Summary counts** at the top level let the orchestrator estimate batching without parsing all entries.
