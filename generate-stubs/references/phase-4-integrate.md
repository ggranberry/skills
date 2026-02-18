# Phase 4: Integrate Constraints

Spawn as: `Task(subagent_type="general-purpose")`

Add the constraint code from Phase 3 to the stub file.

## Instructions

1. Read `_crosshair_stubs.py`
2. Insert the `_apply_constraints` function from the Phase 3 plan
3. Update terminal methods (`.first()`, `.get()`, etc.) to call `_apply_constraints`
4. Add any required imports
5. Re-validate: `python -m py_compile _crosshair_stubs.py`
