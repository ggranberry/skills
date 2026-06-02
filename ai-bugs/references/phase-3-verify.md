# Phase 3: Verify Findings

Spawn verification agents to filter false positives from Phase 2 findings.

## Step 1: Collect raw findings

Read all `findings/raw-<slug>.json` files. Collect files that have at least one finding. If zero findings across all files, skip to Phase 4 and write an empty report.

## Step 2: Spawn verification agents

Spawn one `general-purpose` agent per file that has findings, all in parallel (single message).

**File-existence tracking:** Skip files where `findings/verified-<slug>.json` already exists. Delete to re-verify.

Each verification agent receives:

```
You are a bug verification agent. Your job is to critically examine each reported finding and determine whether it is a real bug or a false positive. Be skeptical — assume findings are false positives until proven otherwise.

Read the source file at `{FILE_PATH}`.

Here are the findings to verify:
{FINDINGS_JSON}

For each finding, apply these classification questions IN ORDER. Most false positives are eliminated by Q1–Q2.

### Q1 — Is this reachable?

Could these exact conditions occur in normal usage of this function? Consider:
- Would typical callers pass these inputs?
- Are there upstream validators, type checks, or preconditions that prevent this?
- Is this a public API or an internal helper with controlled callers?
- Does the function signature (type hints, defaults) suggest what inputs are expected?

If unreachable in practice → false positive (unreachable path).

### Q2 — Does the code already handle it?

Re-read the function carefully:
- Is there a try/except, if-guard, or assertion that catches this case?
- Does a decorator, wrapper, or base class handle it?
- Did the finding agent miss existing defensive code?
- Does the framework handle this automatically?

If already handled → false positive (already guarded).

### Q3 — What is the actual effect?

If the bug triggers, what happens?
- Data loss, corruption, or silent incorrect write → Critical
- Wrong return value that propagates to callers → High
- Unhandled exception with clear traceback (not silent) → Medium
- Cosmetic issue or caught by downstream validation → Low
- No observable harm → False positive

### Q4 — Can you construct a proof?

Write a minimal code snippet (3-5 lines) that would trigger this bug. If you cannot construct a concrete, runnable proof, downgrade to low confidence or false positive.

---

Return your results as a JSON object (and nothing else):

{
  "file": "{FILE_PATH}",
  "verified_findings": [
    {
      "function": "function_name",
      "line": 42,
      "class_name": "ClassName or null",
      "bug_class": "logic_errors",
      "description": "What the bug is",
      "trigger": "function_call(arg=value)",
      "proof_snippet": "svc = Service()\nresult = svc.func(bad_input)  # returns wrong value",
      "verdict": "real_bug",
      "severity": "critical|high|medium|low",
      "reasoning": "Q1: reachable — public API, no validation. Q2: no guard. Q3: data loss. Q4: proof constructed.",
      "suggested_action": "Add guard clause or fix the condition"
    }
  ],
  "false_positives": [
    {
      "function": "function_name",
      "line": 88,
      "bug_class": "edge_cases",
      "description": "Original finding description",
      "verdict": "false_positive",
      "reason": "already_guarded|unreachable|no_harm|cannot_prove",
      "reasoning": "Q1/Q2 explanation of why this is not a real bug"
    }
  ]
}
```

## Step 3: Write verified findings

After each verification agent returns, write its output to `findings/verified-<slug>.json`.

## Severity Scale

| Severity | Criteria |
|----------|----------|
| Critical | Data loss, security issue, silent incorrect write |
| High | Wrong return value or inconsistent state that propagates |
| Medium | Unhandled edge case with observable wrong behavior, not data-destroying |
| Low | Real but low risk, covered by upstream validation |
| False Positive | Unreachable path, already guarded, no observable harm, or cannot construct proof |
