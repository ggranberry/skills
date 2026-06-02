# Phase 1: Discover Targets

## Step 1: Run the discovery script

From the project root:

```bash
python3 /home/jerj/.claude/skills/ai-bugs/scripts/discover_targets.py
```

This writes `.claude/artifacts/ai-bugs/file-targets.json`.

## Step 2: Review the output

Read `file-targets.json` and sanity-check:
- Are the right source directories included?
- Are tests, migrations, and venvs excluded?
- Is the file count reasonable for the project?

## Step 3: Re-run with flags if needed

If the project has unusual structure:

```bash
# Only scan specific packages
python3 /home/jerj/.claude/skills/ai-bugs/scripts/discover_targets.py --include-dirs src app

# Exclude additional directories
python3 /home/jerj/.claude/skills/ai-bugs/scripts/discover_targets.py --exclude-dirs vendor generated

# Skip files already analyzed (resume)
python3 /home/jerj/.claude/skills/ai-bugs/scripts/discover_targets.py --skip-existing
```
