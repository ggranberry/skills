# Phase 4b: Apply Constraints

Spawn as: `Agent(subagent_type="general-purpose")`

Implement constraint application based on the plan.

## Instructions

1. Read `.claude/artifacts/crosshair-bugs/plans/constraint-plan.md`
2. Read `_crosshair_stubs.py`
3. Add required imports from plan
4. Implement `_apply_constraints()` function per the plan
5. Update terminal methods (`.first()`, `.get()`, etc.) to call `_apply_constraints`
6. Write updated `_crosshair_stubs.py`
7. Validate: `python -m py_compile _crosshair_stubs.py`

## Critical: exception handling

Every `try` that wraps a `space.add(...)`, `proxy_for_type(...)`, or `context_statespace()` call **must** use `except BaseException:` — not `except Exception:`.

`crosshair.util.CrossHairInternal` (raised by e.g. `space.add` on a concrete boolean, by `proxy_for_type` outside a statespace, or by descriptor patches on symbolic mismatches) extends `ControlFlowException` → `BaseException`. A plain `except Exception:` lets it bubble up to CrossHair's main loop and aborts analysis with a misleading traceback that looks like a contract violation. Confirmed against crosshair v0.0.102 (`util.py:683` `class ControlFlowException(BaseException)`).

Apply the same pattern to any try/except in MockManager / MockQuerySet terminal methods that call `proxy_for_type` — these can be called from module-import time (when Django forms instantiate ModelChoiceField with `queryset=Foo.objects.none().all()`) where no statespace exists.
