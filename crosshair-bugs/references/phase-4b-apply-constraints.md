# Phase 4b: Apply Constraints

Spawn as: `Task(subagent_type="general-purpose")`

Implement constraint application based on the plan.

## Instructions

1. Read `.claude/artifacts/crosshair-bugs/plans/constraint-plan.md`
2. Read `_crosshair_stubs.py`
3. Add required imports from plan
4. Implement `_apply_constraints()` function per the plan
5. Update terminal methods (`.first()`, `.get()`, etc.) to call `_apply_constraints`
6. Write updated `_crosshair_stubs.py`
7. Validate: `python -m py_compile _crosshair_stubs.py`
