---
name: ai-bugs
description: Find bugs in Python files using AI multi-agent analysis. Use when asked to find bugs without CrossHair, or for AI-based bug hunting. Spawns specialized agents per file for logic errors, edge cases, data integrity, and error handling, then verifies findings. Not for unit testing, linting, or static type checking.
---

# AI Bugs

Multi-agent AI bug finder. Spawns specialized bug-hunting agents per Python file, then verification agents to filter false positives.

**IMPORTANT:** Do NOT invoke any other skills during this workflow. Do not use `crosshair-bugs`, `detect-orm`, `generate-stubs`, `generate-contracts`, `parse-migrations`, or `crosshair-django`. This skill is fully self-contained.

## Artifacts

All intermediate outputs are persisted to `.claude/artifacts/ai-bugs/`:

```
ai-bugs/
├── file-targets.json              # Phase 1 — discovered Python files
├── findings/
│   ├── raw-<slug>.json            # Phase 2 — raw findings per file
│   └── verified-<slug>.json       # Phase 3 — verified findings per file
├── bugs-report.md                 # Phase 4 — final report (human-readable)
└── bugs-report.json               # Phase 4 — final report (machine-readable)
```

## Setup

```bash
mkdir -p .claude/artifacts/ai-bugs/findings
```

## Workflow

**Copy this checklist into your response at the start and check off each phase as it completes:**

```
Phase Progress:
- [ ] Phase 1: Discover targets
- [ ] Phase 2: Analyze (per-file bug-finding agents)
- [ ] Phase 3: Verify findings
- [ ] Phase 4: Compile report
```

Each phase reads a reference file with its full prompt. This keeps the orchestrator lightweight.

### Phase 1: Discover Targets

Follow `.claude/skills/ai-bugs/references/phase-1-discover.md`

### Phase 2: Analyze

Follow `.claude/skills/ai-bugs/references/phase-2-analyze.md`

### Phase 3: Verify Findings

Follow `.claude/skills/ai-bugs/references/phase-3-verify.md`

### Phase 4: Compile Report

Follow `.claude/skills/ai-bugs/references/phase-4-report.md`

## Resuming

If a phase fails, you can resume from artifacts:
- Phase 2+ can read `file-targets.json`
- Phase 3+ can read `findings/raw-*.json`
- Phase 4 can read `findings/verified-*.json`

**Phase 2 uses file-existence progress tracking:** files with existing `findings/raw-<slug>.json` are skipped. Delete specific files to force re-analysis. Phase 3 similarly skips files with existing `findings/verified-<slug>.json`.
