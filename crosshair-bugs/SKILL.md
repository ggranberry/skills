---
name: crosshair-bugs
description: Find bugs using CrossHair symbolic execution. Orchestrates ORM detection, stub generation, schema extraction, constraint application, and contract generation.
---

# CrossHair Bugs

Top-level orchestrator that prepares a codebase for CrossHair symbolic execution by generating database stubs with schema constraints and adding PEP 316 contracts to business logic.

## Artifacts

All intermediate outputs are persisted to `.claude/artifacts/crosshair-bugs/`:

| File | Phase | Contents |
|------|-------|----------|
| `orm-detection.json` | 1 | ORM type, model files |
| `schema-constraints.json` | 3 | Models with column constraints |
| `constraint-plan.md` | 4a | Planner's reasoning and plan |
| `contract-targets.json` | 5 | Classes and functions to receive PEP 316 contracts (includes source) |
| `contract-plan.md` | 6 | Planned pre/post/inv contracts per target |
| `bugs-report.md` | 9 | CrossHair counterexamples and bug findings |

## Workflow Overview

```
/crosshair-bugs

  Phase 1: detect-orm (Bash)
     └─> Run detection script
     └─> Write .claude/artifacts/crosshair-bugs/orm-detection.json

  Phase 2: generate-stubs base (Generator agent)
     └─> Read orm-detection.json
     └─> Create _crosshair_stubs.py (no constraints)

  Phase 3: parse-migrations (Explore agent)
     └─> Read orm-detection.json for model files
     └─> Write .claude/artifacts/crosshair-bugs/schema-constraints.json

  Phase 4a: Plan constraints (Planner agent)
     └─> Read schema-constraints.json
     └─> Write .claude/artifacts/crosshair-bugs/constraint-plan.md

  Phase 4b: Apply constraints (Generator agent)
     └─> Read constraint-plan.md
     └─> Update _crosshair_stubs.py

  Phase 5: generate-contracts / Explore (Explore agent)
     └─> Fan out from model files, embed source in artifact
     └─> Write .claude/artifacts/crosshair-bugs/contract-targets.json

  Phase 6: generate-contracts / Plan (Planner agent)
     └─> Read contract-targets.json + schema-constraints.json + SKILL.md best practices
     └─> Write .claude/artifacts/crosshair-bugs/contract-plan.md

  Phase 7: generate-contracts / Apply (Generator agent)
     └─> Read contract-plan.md
     └─> Add PEP 316 docstring contracts (pre:/post:/inv:) to source files

  Phase 8: generate-contracts / Validate (Bash)
     └─> crosshair check with 1s timeout to confirm contracts parse

  Phase 9: Find bugs (Bash + Planner agent)
     └─> Run CrossHair with real timeouts on all contracted files
     └─> Collect counterexamples
     └─> Write .claude/artifacts/crosshair-bugs/bugs-report.md
```

## Instructions

### Setup

First, ensure artifacts directory exists:

```bash
mkdir -p .claude/artifacts/crosshair-bugs
```

### Phase 1: Detect ORM

```bash
bash .claude/skills/detect-orm/scripts/detect-orm.sh > .claude/artifacts/crosshair-bugs/orm-detection.json
```

The JSON contains:
```json
{
  "orms_detected": [{"orm": "sqlalchemy", "confidence": "high"}],
  "model_files": ["conduit/user/models.py", "conduit/articles/models.py"]
}
```

### Phase 2: Generate Base Stubs

Spawn Generator agent:

```
Task(subagent_type="generator", prompt="""
Create base CrossHair stub file.

1. Read .claude/artifacts/crosshair-bugs/orm-detection.json
2. Identify ORM type and model files
3. Read template: .claude/skills/generate-stubs/templates/[orm]_stubs.py.jinja
4. For each model file, extract:
   - Class name (e.g., User)
   - Module path (e.g., conduit.user.models)
5. Fill template with model info
6. Write to _crosshair_stubs.py
7. Validate: python -m py_compile _crosshair_stubs.py

Do NOT add constraints - just the base stub structure.
""")
```

### Phase 3: Extract Schema Constraints

Spawn Explore agent:

```
Task(subagent_type="Explore", prompt="""
Extract database constraints from model files.

1. Read .claude/artifacts/crosshair-bugs/orm-detection.json for model file list
2. For each model file, extract columns and constraints:
   - nullable (true/false, default true)
   - unique (true/false)
   - primary_key (true/false)
   - foreign_key (reference string)
   - check (constraint expression)
   - enum (list of values)
   - type with length (e.g., String(100))

3. Write to .claude/artifacts/crosshair-bugs/schema-constraints.json:
{
  "models": [
    {
      "class": "User",
      "module": "conduit.user.models",
      "table": "users",
      "columns": {
        "id": {"type": "Integer", "primary_key": true},
        "email": {"type": "String(100)", "nullable": false, "unique": true},
        "age": {"type": "Integer", "nullable": true, "check": "age >= 0"},
        "status": {"type": "Enum", "values": ["active", "inactive"]}
      }
    }
  ]
}
""")
```

### Phase 4a: Plan Constraint Application

Spawn Planner agent:

```
Task(subagent_type="planner", prompt="""
Plan how to apply database constraints to CrossHair symbolic variables.

1. Read .claude/artifacts/crosshair-bugs/schema-constraints.json
2. Read _crosshair_stubs.py to understand current structure

For each constraint type, plan the translation:

| Constraint | CrossHair Code |
|------------|----------------|
| nullable=false | space.add(result.field is not None) |
| check: "age >= 0" | space.add(result.age >= 0) |
| enum: ["a","b"] | space.add(z3.Or(result.x == 'a', result.x == 'b')) |
| String(N) | space.add(len(result.field) <= N) |

3. Write plan to .claude/artifacts/crosshair-bugs/constraint-plan.md:

# Constraint Application Plan

## Imports Needed
- from crosshair.statespace import context_statespace
- import z3 (if enums present)

## _apply_constraints Function Structure
[describe the function]

## Per-Model Constraints

### User
- email: not null → space.add(result.email is not None)
- age: check → space.add(result.age >= 0)

### Article
...

## Integration Points
- Update .first() to call _apply_constraints(result, self.model_type)
- Update .get() similarly
- etc.

Do NOT write code - just the plan in markdown.
""")
```

### Phase 4b: Apply Constraints

Spawn Generator agent:

```
Task(subagent_type="generator", prompt="""
Implement constraint application based on plan.

1. Read .claude/artifacts/crosshair-bugs/constraint-plan.md
2. Read _crosshair_stubs.py
3. Add required imports from plan
4. Implement _apply_constraints() function per the plan
5. Update terminal methods (.first(), .get(), etc.) to call _apply_constraints
6. Write updated _crosshair_stubs.py
7. Validate: python -m py_compile _crosshair_stubs.py
""")
```

### Phases 5–8: Generate Contracts

These phases are defined in the `generate-contracts` skill
(`.claude/skills/generate-contracts/SKILL.md`). Follow that skill's workflow:

- **Phase 5** → generate-contracts Phase 1 (Explore: find targets, embed source)
- **Phase 6** → generate-contracts Phase 2 (Plan: design PEP 316 contracts)
- **Phase 7** → generate-contracts Phase 3 (Apply: add docstring contracts to source)
- **Phase 8** → generate-contracts Phase 4 (Validate: `crosshair check` syntax smoke test)

All artifacts are written to the same `.claude/artifacts/crosshair-bugs/` directory.

### Phase 9: Find Bugs

Run CrossHair with real timeouts to find contract violations. This is the actual
bug-finding step.

First, collect the list of contracted files from the contract plan:

```bash
# Extract file paths from contract-plan.md section headings
grep '^### ' .claude/artifacts/crosshair-bugs/contract-plan.md | \
  sed 's/^### //' | sort -u > /tmp/contracted_files.txt
```

Run CrossHair on each file with stubs loaded:

```bash
# Run CrossHair on each contracted file
# --per_condition_timeout 30: give each contract 30s of analysis
# --analysis_kind PEP316: target PEP 316 docstring contracts
while IFS= read -r file; do
  echo "=== Checking: $file ==="
  crosshair check "$file" \
    --per_condition_timeout 30 \
    --analysis_kind PEP316 \
    2>&1
  echo ""
done < /tmp/contracted_files.txt | tee .claude/artifacts/crosshair-bugs/crosshair-raw-output.txt
```

Then spawn a Planner agent to analyze the raw output into a structured bug report:

```
Task(subagent_type="planner", prompt="""
Analyze CrossHair output and produce a bug report.

1. Read .claude/artifacts/crosshair-bugs/crosshair-raw-output.txt
2. Read .claude/artifacts/crosshair-bugs/contract-plan.md (for context on what each contract checks)

For each counterexample CrossHair found:
- Identify the function and which contract was violated (pre/post/inv)
- Show the counterexample inputs CrossHair produced
- Explain what the bug means in plain language
- Assess severity: is this a real bug, an edge case, or a likely false positive from
  an over-strict contract?

Write to .claude/artifacts/crosshair-bugs/bugs-report.md:

# CrossHair Bug Report

## Summary
- X counterexamples found across Y files
- Z likely real bugs, W likely false positives

## Bugs Found

### 1. [file:function_name] — [short description]
**Contract violated:** `post: __return__ is not None`
**Counterexample:** `make_article(title='', body=None, description='test')`
**Explanation:** When body is None, the function still attempts to create an article
but the database rejects the null body, causing an unhandled exception.
**Severity:** Real bug — body should be validated before creation.

### 2. ...

## Likely False Positives
- [file:function_name] — contract may be too strict because [reason]

## Files With No Violations
- [list of clean files]

Present findings clearly so the user can act on real bugs and adjust over-strict contracts.
""")
```

## Output

After all phases complete:
- `.claude/artifacts/crosshair-bugs/orm-detection.json`
- `.claude/artifacts/crosshair-bugs/schema-constraints.json`
- `.claude/artifacts/crosshair-bugs/constraint-plan.md`
- `_crosshair_stubs.py` with full constraint support
- `.claude/artifacts/crosshair-bugs/contract-targets.json`
- `.claude/artifacts/crosshair-bugs/contract-plan.md`
- Modified source files with PEP 316 docstring contracts
- `.claude/artifacts/crosshair-bugs/bugs-report.md` — the final deliverable

## Resuming

If a phase fails, you can resume from artifacts:
- Phase 2+ can read `orm-detection.json`
- Phase 4+ can read `schema-constraints.json`
- Phase 4b can read `constraint-plan.md`
- Phase 6+ can read `contract-targets.json`
- Phase 7+ can read `contract-plan.md`
- Phase 8 can re-run after fixing contracts
- Phase 9 can re-run after adjusting contracts or stubs

## Sub-skills Used

| Skill | Phase | Purpose |
|-------|-------|---------|
| detect-orm | 1 | Identify ORM and model files |
| generate-stubs | 2 | Base stub templates |
| parse-migrations | 3 | Constraint extraction patterns |
| generate-contracts | 5–8 | PEP 316 contract discovery, planning, application, validation |
