---
name: crosshair-stub-effectiveness
description: Measure how much an existing CrossHair ORM-stub module pulls its weight on a Python project — what fraction of contracted functions need the stubs to run, and what fraction of past bugs were only reachable because the stubs made the function symbolically executable in the first place. Use after crosshair-bugs or crosshair-lite has been set up. Not for writing stubs or finding bugs — for auditing whether existing stubs are earning their cost.
---

# CrossHair Stub Effectiveness

Static analyzer that answers "are the smart ORM stubs we wrote actually doing work?"

It produces two complementary metrics:
- **Metric A — stub-reach**: for each contracted function, classify whether reaching its body symbolically requires the smart ORM stubs, or just an import-time scaffold, or no Django/ORM machinery at all.
- **Metric B — stub-attribution** (optional): for each past CrossHair finding, classify whether removing the smart stubs would have prevented CrossHair from reaching the bug. A finding is `stubbed_model`-attributable when the function's signature or body needs the stubs to be reachable — even if the *triggering* primitive CrossHair printed in the counterexample is just an int or str. See `references/findings-schema.md` for the decision procedure.

The output tells you whether the stubs are earning their runtime cost via reach, via bug discovery, or whether a thinner shim would do.

## Artifacts

All outputs are persisted to `.claude/artifacts/crosshair-stub-effectiveness/`:

```
crosshair-stub-effectiveness/
├── stub-inventory.json           # Phase 1 — models + factory attrs extracted from the stub file
├── stub-effectiveness.json       # Phase 3 — per-file & per-function classification + summary
└── stub-effectiveness-report.md  # Phase 4 — human-readable report
```

## Prerequisites

- The project already has CrossHair set up (either via crosshair-bugs or crosshair-lite).
- A `contract-files.json` exists from crosshair-lite Phase 1 at `.claude/artifacts/crosshair-lite/contract-files.json`. If not, run the crosshair-lite Phase 1 first or pass `--contract-files` to point elsewhere.
- The project has a Python file that installs / declares the ORM stubs (e.g. `_crosshair_stubs.py`).

## Setup

```bash
mkdir -p .claude/artifacts/crosshair-stub-effectiveness
```

## Workflow

**Copy this checklist into your response at the start and check off each phase as it completes:**

```
Phase Progress:
- [ ] Phase 1: Inventory the stubs
- [ ] Phase 2: Locate contract files
- [ ] Phase 3: Analyze stub-reach (Metric A)
- [ ] Phase 4: Attribute findings (Metric B, optional)
- [ ] Phase 5: Report
```

### Phase 1: Inventory the stubs

Parse the project's stub file to extract:
- The list of stubbed model class names
- Attribute names that stub-generated mock instances expose (so the AST analyzer can detect `<param>.<stub_attr>` patterns)
- Plural-form hints for QuerySet-typed parameters

1. **Ask the user** for the stub file path:
   > "What's the path to the file that installs your CrossHair ORM stubs? (e.g. `_crosshair_stubs.py`, `crosshair_stubs/__init__.py`)"

2. Run the inventory script:
   ```bash
   python3 ~/.claude/skills/crosshair-stub-effectiveness/scripts/inventory_stubs.py \
     <stub_file_path> \
     --output .claude/artifacts/crosshair-stub-effectiveness/stub-inventory.json
   ```

3. Report the summary (number of stubbed models, factory models, attrs collected). If detection misses models you know are stubbed, the user can supply an override config — see `references/inventory-overrides.md`.

### Phase 2: Locate contract files

Reuse the crosshair-lite Phase 1 artifact:

```bash
ls .claude/artifacts/crosshair-lite/contract-files.json
```

- If it exists, use it.
- If not, invoke the crosshair-lite Phase 1 finder first, then return here.

### Phase 3: Analyze stub-reach (Metric A)

Run the AST analyzer:

```bash
python3 ~/.claude/skills/crosshair-stub-effectiveness/scripts/analyze_stub_effectiveness.py \
  --inventory .claude/artifacts/crosshair-stub-effectiveness/stub-inventory.json \
  --contract-files .claude/artifacts/crosshair-lite/contract-files.json \
  --output .claude/artifacts/crosshair-stub-effectiveness/stub-effectiveness.json
```

This produces a per-function classification:
- `stub_required` — body touches `<Model>.objects` (or equivalent ORM pattern), takes a stubbed-model parameter, iterates a QuerySet-typed parameter, or reads `<param>[<stubbed_model_lower>]` subscripts.
- `stub_unreached_but_imported` — function body uses only primitives, but its module imports the ORM/framework. Needs the import-time scaffold but not the smart MockManager/MockQuerySet machinery.
- `stub_irrelevant` — pure-Python module, no ORM or framework imports at all.

### Phase 4: Attribute findings to stubs (Metric B, optional)

If the project has a curated list of past CrossHair findings (e.g. in memory or a separate JSON), classify each by **whether the smart stubs are what made the bug reachable** — not by the literal value-type CrossHair printed in the counterexample. A finding whose counterexample prints `"x='\x00'"` can still be `stubbed_model` if the function under analysis takes a stubbed-model argument or its body calls `Model.objects.X(...)` / walks a FK / iterates a related manager on the path to the bug. See `references/findings-schema.md` for the decision procedure.

1. **Ask the user** whether they have a findings list to attribute:
   > "Do you have a list of past CrossHair findings to attribute? (yes / no / I'll provide a file path)"

2. If yes, accept either a path to a findings JSON (schema in `references/findings-schema.md`) or inline data. Update `stub-effectiveness.json`'s `findings_attribution` field via:

   ```bash
   python3 ~/.claude/skills/crosshair-stub-effectiveness/scripts/attribute_findings.py \
     --findings <path-or-inline-json> \
     --effectiveness .claude/artifacts/crosshair-stub-effectiveness/stub-effectiveness.json
   ```

3. If no, skip — the report will show only Metric A.

### Phase 5: Report

Generate the markdown report from the JSON:

```bash
python3 ~/.claude/skills/crosshair-stub-effectiveness/scripts/generate_report.py \
  --effectiveness .claude/artifacts/crosshair-stub-effectiveness/stub-effectiveness.json \
  --output .claude/artifacts/crosshair-stub-effectiveness/stub-effectiveness-report.md
```

Read the report and surface the headlines to the user:
- Stub-reach: `<N>/<total>` functions require the smart stubs (`<pct>%`)
- The bucket distribution: how many functions need *only* the import-time scaffold
- Bug attribution: stub-enabled vs stub-independent ratio over real bugs (only if Phase 4 ran). "Stub-enabled" = the function couldn't have been symbolically executed without the smart stubs, even if the printed counterexample value is a primitive.
- One-sentence verdict: "stubs are earning their keep via reach" / "via bug discovery" / "could be slimmed to an import-only shim"

## Resuming

- Phase 1 can be re-run any time (overwrites `stub-inventory.json`).
- Phase 3 can be re-run after the inventory or contract-files change.
- Phase 4 is additive — re-running re-classifies the findings list without re-running Metric A.
- Phase 5 is idempotent — regenerates the report from the current JSON.

## What this skill does NOT do

- It does not run CrossHair. Use crosshair-bugs or crosshair-lite for that first.
- It does not write or modify stubs. Use generate-stubs.
- It does not attempt to *find* new bugs. It analyzes coverage and attribution of existing work.
- The Metric B findings list is hand-curated — there's no automated way to introspect CrossHair's symbolic value lineage. The attribution helper just lets you record categorizations consistently.

## ORM support

The analyzer's heuristics cover:
- **Django**: `<Model>.objects.<method>(...)`, `<param>.<field>_set.all()`, `attrs['<model_lower>']` DRF subscript.
- **SQLAlchemy**: `session.query(<Model>)`, `<Model>.query.<method>`, `select(<Model>)`.
- **Generic**: parameter annotations/names matching a stubbed model class, attribute access on a variable whose name matches a stubbed-model singular, iteration over a parameter whose name matches a stubbed-model plural.

For other ORMs (Tortoise, Peewee, etc.), augment the analyzer's `ORM_TERMINAL_METHODS` set in `analyze_stub_effectiveness.py` or pass a project-specific override in `stub-inventory.json` via the `extra_orm_patterns` field.
