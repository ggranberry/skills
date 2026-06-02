# Counterexample Analysis Guide

Reference for classifying CrossHair counterexamples as real bugs or false positives in stub-free mode.

## Before Classifying

In crosshair-lite there are no database stubs. This means:
- Counterexamples involving DB/network/filesystem calls are likely execution errors, not real findings
- Focus your analysis on whether the counterexample exposes a genuine logic error in pure code
- If the counterexample only triggers because CrossHair couldn't model an external dependency, classify as false positive (environment limitation)

---

## Classification Questions

Work through these questions for each counterexample. Most false positives are eliminated by Q1–Q3; genuine bugs survive all four.

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

### Q3 — Is this an environment limitation?

Since crosshair-lite runs without stubs, CrossHair may hit paths it cannot model:

- **Import failures** — module requires DB connection, network service, or framework setup at import time
- **Unmodeled external calls** — function calls a DB/network/cache method that CrossHair cannot symbolically execute
- **Framework state** — function depends on global state (e.g., Django settings, request context) that doesn't exist during symbolic execution

If the violation only occurs because CrossHair couldn't model an external dependency → **false positive (environment limitation)**. Note the specific dependency.

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
| False Positive | Unreachable path, over-strict contract, or environment limitation |

---

## Common False Positive Patterns

- **Framework validation covers it** — input is rejected by a serializer, form, or schema layer before reaching the function
- **DB constraint prevents it** — the counterexample object can't exist (unique violation, missing FK, check constraint)
- **Environment limitation** — CrossHair couldn't model an external dependency (DB, network, cache) and produced an impossible execution path
- **Postcondition assumes ordering** — checks `result[0]` but function can return an empty sequence
- **Contract too strict** — precondition rejects inputs the function handles correctly (e.g., `pre: x > 0` but zero is fine)
- **Exception correctly caught** — the function handles the path gracefully and the contract didn't account for that branch
