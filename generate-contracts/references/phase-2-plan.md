# Phase 2: Plan Contracts (Single File Focus)

Spawn as: `Task(subagent_type="general-purpose")`

Triage contract candidates and design PEP 316 contracts for a single file.

## Contents

- [Inputs](#inputs)
- [Critical: Read Before You Judge](#critical-read-before-you-judge)
- [Instructions](#instructions)
  - [Step 1: Read the Full File](#step-1-read-the-full-file)
  - [Step 2: Triage](#step-2-triage)
  - [Step 3: Design Contracts](#step-3-design-contracts)
- [Output](#output)

## Inputs

1. Read your assignment from `.claude/artifacts/crosshair-bugs/planner-assignments.json` — find the entry matching your assigned `id`
2. Read `.claude/artifacts/crosshair-bugs/schema-constraints.json` — database schema constraints
3. Read `.claude/skills/generate-contracts/references/pep316-guide.md` — contract syntax and best practices
4. Read `.claude/skills/generate-contracts/references/assertions.md` — using `assert` for intermediate value checks
5. **Read the entire source file** for your assignment — you must read every function before triaging any of them

## Critical: Read Before You Judge

You are assigned **one file** (or one chunk of a large file). You MUST read the full source of every function in your assignment before making any triage decisions. Do NOT label a function "trivial" based on its name or line count — read the body.

Common mistakes to avoid:
- Labeling a 30-line function "trivial-transform" without reading it
- Labeling a function "framework-glue" when it has complex pure-logic branches
- Labeling a function "thin-wrapper" when it does validation or transformation before delegating

## Instructions

### Step 1: Read the Full File

Read the entire source file (or the functions in your chunk). Understand:
- What the module does at a high level
- How functions relate to each other (callers/callees)
- Where the interesting logic lives vs. where the boilerplate is

### Step 2: Triage

For each function in your assignment, classify it:

**CONTRACT** — Function has meaningful abstract properties worth verifying:
- Non-trivial state mutations (DB writes, collection modifications)
- Business rules that constrain inputs or outputs
- Data transformations with invariants (e.g., merge must preserve all references)
- Conditional logic where branches have different correctness criteria
- Functions where the type signature is more permissive than the actual preconditions

**SKIP** — Function does NOT benefit from contracts. Every SKIP must have a reason from this list:
- `thin-wrapper`: Delegates entirely to another function with no added logic
- `framework-glue`: Wires framework components together (route registration, middleware setup)
- `pure-delegation`: Calls a single repo/service method and returns its result
- `config-only`: Only reads/sets configuration values
- `trivial-transform`: Simple data reshaping with no business rules (e.g., dict-to-model)
- `already-typed`: Function's correctness is fully captured by its type signature
- `no-observable-property`: No abstract property can be stated without restating the implementation

**Be aggressive about including.** When uncertain, classify as CONTRACT — a contract that turns out to be weak is better than a missed bug.

### Step 3: Design Contracts

For each CONTRACT function, design pre/post conditions and invariants following the PEP 316 guide.

**Quality rules for contracts — violations of these make the contract worthless:**

1. **Never restate a parameter's type as a precondition.** `pre: isinstance(captcha_payload, str)` is useless when the signature already declares `captcha_payload: str`. Preconditions must add information the type system cannot express — narrowing constraints (non-empty, positive, within a range), cross-parameter rules, or required dict keys.

2. **Never restate the return type as a postcondition.** `post: isinstance(__return__, bool)` is useless — the type annotation already says this. A contract must test a *property* of the return value, not its type.

3. **Never restate the function body.** If a function is `return len(self.queue) == 0`, then `post: __return__ == (len(self.queue) == 0)` is tautological — it can never find a bug. Instead, relate the result to other observable state (e.g., `post: __return__ == (self.count() == 0)`), or skip the function.

4. **Prefer contracts that relate output to input.** The best postconditions say "given input X, the output has property Y" — not "the output has property Y in isolation."

5. **Prefer contracts that could actually fail.** Ask yourself: "Is there any realistic implementation of this function that would satisfy the type signature but violate this contract?" If the answer is no, the contract is too weak.

6. **Don't contract one-liner functions.** If the function body is a single expression, skip it — any meaningful contract would just restate the expression. Exception: one-liners with complex expressions (multiple conditionals, list comprehensions with filtering).

7. **Target functions where types are more permissive than preconditions.** Functions that accept `dict[str, Any]` but actually require specific keys, or `Sequence[Any]` but actually require non-empty sequences — these are prime targets because CrossHair can find inputs that satisfy the types but break the function.

**For classes with CONTRACT methods**, determine class invariants:
- Derive from non-nullable schema columns → `inv: self.field is not None`
- Only include fields that are truly always non-None after construction
- Don't invariant-check nullable fields or optional relationships

**For each CONTRACT function**, determine pre/post conditions:

**Preconditions (pre:)** — what must be true for the function to behave correctly:
- Parameter validity (not None when required)
- Business rules the schema can't express (e.g., cannot follow yourself)
- Required dict keys that the type signature doesn't enforce
- NOT type checks, NOT framework state, NOT constraints already in stubs

**Postconditions (post:)** — what the function guarantees when it returns:
- Return value properties (use `__return__` to reference it)
- State changes on self or parameters
- Relationships between input and output
- NOT implementation details, NOT timing, NOT restating the body
- **Never use `post: __return__ is not None` as the sole postcondition** — see pep316-guide.md

**Assertions for intermediate values:**

For CONTRACT functions that contain loops or multi-step mutations, consider whether `assert` statements inside the body would help CrossHair check intermediate values. Loop invariants (assertions at the start/end of a loop body) are the highest-value target. See `assertions.md` for guidance.

- Note any existing `assert` statements — do NOT plan to remove them
- If a function would benefit from assertions, include them in the plan alongside the docstring contracts

For each contract, provide:
- The exact PEP 316 line(s) to add
- Any `assert` statements to add inside the function body (with placement description)
- Brief rationale (one line explaining why)
- Any contracts you considered but rejected, with reason

## Output

Write to `.claude/artifacts/crosshair-bugs/<output_file>` (from your assignment in planner-assignments.json):

```markdown
# Contract Plan — <filename>

## Triage Summary
- Total functions in file: 45
- CONTRACT: 18
- SKIP: 27

## Skipped Functions

| Function | Lines | Reason |
|----------|-------|--------|
| get_all_recipes | 3 | pure-delegation |
| EmailService.send | 12 | framework-glue |
| ... | ... | ... |

## Class Invariants

### RecipeModel
- `inv: self.name is not None` — schema: nullable=false
- REJECTED: `inv: self.description is not None` — schema: nullable=true

## Function Contracts

### RepositoryFood.merge(self, from_food, to_food)
**Preconditions:**
- `pre: from_food != to_food` — merging a food into itself loses data
**Postconditions:**
- `post: ...` — ...
**Rejected:**
- `post: isinstance(__return__, bool)` — just restates return type

### <next function>
...

## Edge Cases and Notes
- [any targets where contracts are unclear or require discussion]
```

Do NOT write code — just the plan in markdown.
