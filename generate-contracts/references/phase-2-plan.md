# Phase 2: Plan Contracts

Spawn as: `Task(subagent_type="Plan")`

Triage contract candidates and design PEP 316 contracts for the ones worth contracting.

## Inputs

1. Read `.claude/artifacts/crosshair-bugs/contract-targets.json` — the manifest from Phase 1 (file paths + function metadata, NO source code)
2. Read `.claude/artifacts/crosshair-bugs/schema-constraints.json` — database schema constraints
3. Read `.claude/skills/generate-contracts/references/pep316-guide.md` — contract syntax and best practices
4. Read `.claude/skills/generate-contracts/references/assertions.md` — using `assert` for intermediate value checks
5. Read source files directly for functions in your assigned batch

## Instructions

### Step 1: Triage

For each function in the manifest (or your assigned batch), read its source code and classify it:

**CONTRACT** — Function has meaningful abstract properties worth verifying:
- Non-trivial state mutations (DB writes, collection modifications)
- Business rules that constrain inputs or outputs
- Data transformations with invariants (e.g., merge must preserve all references)
- Conditional logic where branches have different correctness criteria

**SKIP** — Function does NOT benefit from contracts. Every SKIP must have a reason from this list:
- `thin-wrapper`: Delegates entirely to another function with no added logic
- `framework-glue`: Wires framework components together (route registration, middleware setup)
- `pure-delegation`: Calls a single repo/service method and returns its result
- `config-only`: Only reads/sets configuration values
- `trivial-transform`: Simple data reshaping with no business rules (e.g., dict-to-model)
- `already-typed`: Function's correctness is fully captured by its type signature
- `no-observable-property`: No abstract property can be stated without restating the implementation

**Be aggressive about including.** When uncertain, classify as CONTRACT — a contract that turns out to be weak is better than a missed bug.

### Step 2: Design Contracts

For each CONTRACT function, design pre/post conditions and invariants following the PEP 316 guide.

**For classes with CONTRACT methods**, determine class invariants:
- Derive from non-nullable schema columns → `inv: self.field is not None`
- Only include fields that are truly always non-None after construction
- Don't invariant-check nullable fields or optional relationships

**For each CONTRACT function**, determine pre/post conditions:

**Preconditions (pre:)** — what must be true for the function to behave correctly:
- Parameter validity (not None when required)
- Business rules the schema can't express (e.g., cannot follow yourself)
- NOT type checks, NOT framework state, NOT constraints already in stubs

**Postconditions (post:)** — what the function guarantees when it returns:
- Return value properties (use `__return__` to reference it)
- State changes on self or parameters
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

Write to `.claude/artifacts/crosshair-bugs/contract-plan.md`:

```markdown
# Contract Plan

## Triage Summary

- Total functions in batch: 45
- CONTRACT: 18
- SKIP: 27

## Skipped Functions

| File | Function | Reason |
|------|----------|--------|
| mealie/routes/recipe/crud.py | get_all_recipes | pure-delegation |
| mealie/services/email/email_service.py | EmailService.send | framework-glue |
| ... | ... | ... |

## Class Invariants

### RecipeModel (mealie/db/models/recipe/recipe.py)
- `inv: self.name is not None` — schema: nullable=false
- `inv: self.slug is not None` — schema: nullable=false
- REJECTED: `inv: self.description is not None` — schema: nullable=true

## Function Contracts by File

### mealie/repos/repository_foods.py

#### RepositoryFood.merge(self, from_food, to_food)
**Preconditions:**
- `pre: from_food != to_food` — merging a food into itself loses data
**Postconditions:**
- `post: ...` — ...

### <next file>
...

## Edge Cases and Notes
- [any targets where contracts are unclear or require discussion]
```

Do NOT write code — just the plan in markdown.
