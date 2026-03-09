# Phase 1: Explore — Discover Contract Candidates

Discover all functions/methods that could receive contracts. This phase has two steps: first verify which packages to scan, then run the explore script.

## Step 1: Verify Source Packages

Before running the script, determine the correct source packages to scan.

1. **List the top-level directories** in the project root:
   ```bash
   ls -d */
   ```

2. **Read `orm-detection.json`** (if it exists) to see which packages contain models:
   ```bash
   cat .claude/artifacts/crosshair-bugs/orm-detection.json
   ```

3. **Classify each directory.** For every top-level directory, decide if it's:
   - **Source package** — contains the project's business logic, models, views, services, etc.
   - **Infrastructure** — project config (e.g., Django `settings.py`), deployment scripts, tooling, docs
   - **Excluded by default** — tests, migrations, node_modules, .venv, etc. (the script handles these)

   Look at what's inside ambiguous directories before deciding — a directory named `core/` might be business logic or might be framework wiring. Check for `__init__.py` and skim a few `.py` files if unclear.

4. **Identify project-specific subdirectory exclusions.** Some source packages contain subdirectories that shouldn't be scanned (management commands, data import scripts, API schema examples, fixture generators, etc.). List these for `--exclude-dirs`.

## Step 2: Run the Explore Script

Run with the verified packages and exclusions:

```bash
python .claude/skills/generate-contracts/scripts/explore-contracts.py \
  --packages <package1> <package2> ... \
  --exclude-dirs <dir1> <dir2> ... \
  --output .claude/artifacts/crosshair-bugs/contract-targets.json
```

If you're confident the auto-detection will get it right (small project, obvious package structure), you can omit `--packages` and let the script auto-detect, then verify the `source_packages` field in the output matches your expectations.

### Auto-Detection (when --packages is omitted)

The script auto-detects source packages by:
1. Scanning for top-level directories with `__init__.py`
2. Supplementing with packages found in `orm-detection.json`
3. Filtering out common non-source directories (scripts, tools, docs, deploy, etc.)

## Step 3: Verify the Output

After running, check the summary output. If a package was missed or an unwanted one was included, re-run with explicit `--packages`.

The script always excludes standard non-source directories (tests, migrations, __pycache__, node_modules, .venv, etc.) — see the script's `DEFAULT_EXCLUDED_DIRS` for the full list.

## Output Format

Written to `.claude/artifacts/crosshair-bugs/contract-targets.json`:

```json
{
  "source_packages": ["myapp", "core", "utils"],
  "total_files_scanned": 142,
  "total_functions_found": 387,
  "total_functions_excluded": 203,
  "total_functions_included": 184,
  "files": [
    {
      "path": "myapp/repos/repository_foods.py",
      "functions": [
        {
          "name": "RepositoryFood.merge",
          "signature": "(self, from_food: UUID4, to_food: UUID4)",
          "line_number": 45,
          "line_count": 22,
          "has_existing_docstring": false
        }
      ]
    }
  ]
}
```

Summary counts at the top level let the orchestrator estimate batching without parsing all entries.
