# Phase 9: Counterexample Analysis Guide

Reference for classifying CrossHair counterexamples as real bugs or false positives.

## Before Classifying

Read `_crosshair_stubs.py` to understand what ORM behaviors the stubs model and — critically — what they *don't*. Stub gaps are the most common source of false positives. Keep this in mind throughout classification.

---

## Classification Questions

Work through these questions for each counterexample. Most false positives are eliminated by Q1–Q3; genuine bugs survive all five.

### Q1 — Are the inputs reachable in production?

Could these exact inputs reach this function in a real running system? Consider:

- Would a framework validator (serializer, form, schema layer) reject them earlier?
- Would a database constraint (unique, not-null, check, FK) prevent them from existing?
- Would a caller's own preconditions or business rules block them?

If the inputs cannot exist in production → **likely false positive (unreachable path)**.

### Q2 — Is the contract correct?

Re-read the contract and the function side by side:

- Does the precondition correctly express what callers must guarantee? Overly strict preconditions reject inputs the function handles fine.
- Does the postcondition correctly express what the function always guarantees? Overly strict postconditions fail on valid outputs.
- Was the contract inferred from a partial reading and missed an edge case?

If the contract mis-states the function's real requirements → **false positive (over-strict contract)**. Note what the contract should say instead.

### Q3 — Is the stub behavior realistic?

Stubs replace the database. They can diverge from real ORM behavior in ways that create impossible paths. Common gaps:

- **None on miss** — stub returns `None` where the real ORM would raise a not-found exception
- **Identity map** — stub returns distinct objects for two queries with the same primary key; real ORMs return the same object
- **Missing cascade** — stub doesn't propagate deletes or updates that the real DB would
- **Constraint not enforced** — stub allows object combinations that DB constraints would prevent

Read `_crosshair_stubs.py` to confirm which behaviors are actually modeled before concluding a violation is real.

If the violation only occurs because the stub diverges → **false positive (stub gap)**. Note the specific limitation.

### Q4 — Does error handling make it safe?

Check whether the function catches the violation path:

- **Caught and returns a correct result** — the error handling is the intended behavior; not a bug. Check that the function's contract accounts for this.
- **Caught and returns an incorrect/empty result** — silent failure; still a bug even if no exception propagates.
- **Caught and silently swallows** — potential bug if callers expect success to mean the operation completed.
- **Uncaught** — evaluate effect in Q5.

If the function handles the path correctly with no harmful result → **not a bug**. If it catches but silently produces wrong data → **real bug (silent failure)**.

### Q5 — What is the effect?

Assume the violation reaches the caller. What happens?

- **Data loss** — wrong record deleted, field silently overwritten, record orphaned
- **Incorrect state** — object left inconsistent, invariant broken for subsequent callers
- **Wrong return value** — caller receives incorrect data and acts on it
- **Wrong exception type** — exception raised but callers expect a different type
- **No observable harm** — violation is cosmetic or never observed

Effect determines severity (see scale below). No observable harm → downgrade to low or investigate further.

---

## Severity Scale

| Severity | Criteria |
|----------|----------|
| Critical | Data loss, security issue, silent incorrect write |
| High | Wrong return value or inconsistent state that propagates |
| Medium | Unhandled edge case with observable wrong behavior, not data-destroying |
| Low | Gap already covered by upstream validation — real but low risk |
| False Positive | Unreachable path, over-strict contract, or stub gap |

---

## Common False Positive Patterns

- **Framework validation covers it** — input is rejected by a serializer, form, or schema layer before reaching the function
- **DB constraint prevents it** — the counterexample object can't exist (unique violation, missing FK, check constraint)
- **Identity map not modeled** — stub returns two objects for the same PK; real ORM returns one
- **Postcondition assumes ordering** — checks `result[0]` but function can return an empty sequence
- **Stub returns None on miss** — real ORM raises a not-found exception; stub returns `None`, triggering a `NoneType` error
- **Contract too strict** — precondition rejects inputs the function handles correctly (e.g., `pre: x > 0` but zero is fine)
- **Exception correctly caught** — the function handles the path gracefully and the contract didn't account for that branch
