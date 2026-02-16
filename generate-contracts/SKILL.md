---
name: generate-contracts
description: Add PEP 316 docstring contracts (preconditions, postconditions, invariants) to business logic functions for CrossHair symbolic analysis. Orchestrates target discovery, contract planning, and application.
---

# Generate Contracts

Adds PEP 316 docstring contracts to business logic classes and functions so CrossHair can verify them symbolically against database stubs.

## Purpose

CrossHair stubs replace DB calls with symbolic values, but without contracts there is nothing to *check*. Contracts define what "correct" means:

- **Preconditions** (`pre:`) declare what must be true for a function to work correctly
- **Postconditions** (`post:`) declare what the function guarantees when it returns
- **Invariants** (`inv:`) declare what must always be true about an object's state

CrossHair searches for inputs that satisfy preconditions but violate postconditions or invariants — those are bugs.

No library dependency is needed. PEP 316 contracts are pure docstrings that CrossHair reads natively.

## Prerequisites

Before running this skill:
- `orm-detection.json` must exist (from detect-orm)
- `schema-constraints.json` must exist (from parse-migrations)
- `_crosshair_stubs.py` should exist (from generate-stubs), though contracts can be planned without it

## PEP 316 Syntax Reference

### Preconditions

Preconditions go in the function's docstring. They have access to all parameter names.

```python
def make_article(title, body, description, tagList=None):
    """Create an article with slug, author, and tags.

    pre: title is not None
    pre: body is not None
    """
```

For methods, `self` is available:

```python
def follow(self, profile):
    """Follow a user profile.

    pre: profile is not None
    pre: profile.id != self.id
    """
```

### Postconditions

Postconditions use `__return__` to reference the return value. All parameter names remain accessible.

```python
def make_article(title, body, description, tagList=None):
    """Create an article with slug, author, and tags.

    pre: title is not None
    post: __return__ is not None
    post: __return__.slug is not None
    """
```

Use `__old__` to reference pre-call state (captured before execution):

```python
def favourite(self, profile):
    """Add profile to favoriters.

    pre: profile is not None
    post: profile in self.favoriters
    """
```

### Class Invariants

Invariants go in the **class** docstring. They are checked after `__init__` and after every public method call. `self` is available.

```python
class Article(Model):
    """Represents a published article.

    inv: self.title is not None
    inv: self.slug is not None
    inv: self.author_id is not None
    """
```

Invariants are the right place for schema constraints that must **always** hold, not just at function boundaries.

### Multi-line conditions

For complex conditions, use `\` continuation:

```python
def register_user(username, password, email):
    """Register a new user.

    pre: username is not None and \
         email is not None and \
         password is not None
    """
```

Prefer separate `pre:`/`post:` lines over multi-line when conditions are independent concerns.

## Best Practices

### What makes a good precondition

A precondition should capture a **real assumption** the function makes — something that, if violated, leads to incorrect behavior rather than a clean error.

**Good preconditions:**
```python
def make_article(title, body, description, tagList=None):
    """
    pre: title is not None    # slugify(title) fails on None
    pre: body is not None     # stored directly, schema requires it
    """

def follow(self, profile):
    """
    pre: profile is not None
    pre: profile.id != self.id    # business rule: cannot follow yourself
    """
```

**Bad preconditions (avoid these):**
```python
# Too obvious — Python already raises TypeError
# pre: isinstance(title, str)

# Duplicates a DB constraint that the stub already enforces via _apply_constraints
# pre: len(email) <= 100

# Tests framework behavior, not business logic
# pre: current_user.is_authenticated
```

**Rules:**
1. Only assert what the function *silently depends on* — not what would naturally raise an exception
2. Don't duplicate constraints already enforced by stubs (`_apply_constraints`)
3. Focus on business rules the schema can't express (e.g., "cannot follow yourself")
4. Keep conditions simple and readable — if it needs a helper function, it's testing too much

### What makes a good postcondition

A postcondition should capture a **guarantee** — something the caller can rely on.

**Good postconditions:**
```python
def make_article(title, body, description, tagList=None):
    """
    post: __return__ is not None        # always creates and returns an article
    post: __return__.slug is not None   # slug is auto-generated in __init__
    """

def is_favourite(self, profile):
    """
    post: isinstance(__return__, bool)
    """
```

**Bad postconditions (avoid these):**
```python
# Tests implementation detail, not a guarantee
# post: __return__.created_at <= datetime.utcnow()

# Too vague to catch anything
# post: __return__ is not None or __return__ is None

# Restates the function body
# post: __return__ == User.query.filter_by(email=email).first()
```

**Rules:**
1. Assert properties of the return value, not how it was computed
2. Use schema constraints to inform postconditions (non-nullable fields should be non-None)
3. For functions that return None on failure, don't add `__return__ is not None` — the None *is* valid behavior
4. For mutation functions that return the mutated object, check that the mutation stuck

### What makes a good invariant

Invariants are checked after construction and after every public method. They express **always-true properties** of an object.

**Good invariants:**
```python
class User(Model):
    """
    inv: self.username is not None    # schema: nullable=false
    inv: self.email is not None       # schema: nullable=false
    """

class Article(Model):
    """
    inv: self.title is not None
    inv: self.slug is not None
    inv: self.author_id is not None   # every article has an author
    """
```

**Bad invariants (avoid these):**
```python
# Nullable field — None IS valid state
# inv: self.bio is not None

# Implementation detail of timestamps
# inv: self.created_at <= self.updated_at

# Depends on external state (other objects)
# inv: self.author in User.query.all()
```

**Rules:**
1. Derive invariants from schema constraints: non-nullable columns become invariants
2. Only include fields that are truly always non-None after construction — not fields set lazily
3. Don't reference external state or other objects (invariants should be self-contained)
4. Don't invariant-check nullable fields or optional relationships
5. Invariants are the natural home for schema constraints — prefer them over repeating the same postcondition on every method

### Contract strength: finding the sweet spot

Contracts that are too strict produce false positives (CrossHair finds "bugs" that aren't real). Contracts that are too loose miss real bugs.

**Calibration heuristic:** If you can imagine a reasonable caller passing an input that violates the precondition, it's too strict. If you can imagine the function returning a value that violates the postcondition in normal operation, the postcondition is too strict.

| Too strict | Right level | Too loose |
|------------|-------------|-----------|
| `pre: len(title) > 0` | `pre: title is not None` | (no precondition) |
| `post: len(__return__.slug) > 0` | `post: __return__.slug is not None` | (no postcondition) |
| `pre: email matches regex` | `pre: email is not None` | (no precondition) |
| `inv: len(self.username) > 0` | `inv: self.username is not None` | (no invariant) |

### Docstring integration

When a function already has a docstring, append contracts after the description with a blank line separator:

```python
def make_article(title, body, description, tagList=None):
    """Create an article with slug, author, and tags.

    Generates a URL-friendly slug from the title and associates
    the article with the current user's profile.

    pre: title is not None
    pre: body is not None
    post: __return__ is not None
    post: __return__.slug is not None
    """
```

When a function has no docstring, add one with just the contracts:

```python
def favourite(self, profile):
    """
    pre: profile is not None
    post: profile in self.favoriters
    """
```

### Common contract patterns

**CRUD create:**
```python
def create(cls, **kwargs):
    """
    post: __return__ is not None
    post: __return__.id is not None
    """
```

**CRUD update:**
```python
def update(self, commit=True, **kwargs):
    """
    pre: self.id is not None
    post: __return__ is not None
    """
```

**Query that may return None:**
```python
def get_article(slug):
    """
    pre: slug is not None
    """
    # No postcondition on nullability — None is valid (not found)
```

**Toggle / idempotent operation:**
```python
def favourite(self, profile):
    """
    pre: profile is not None
    post: profile in self.favoriters
    """
```

**Boolean check:**
```python
def is_favourite(self, profile):
    """
    pre: profile is not None
    post: isinstance(__return__, bool)
    """
```

**Class with schema-derived invariants:**
```python
class User(Model):
    """
    inv: self.username is not None
    inv: self.email is not None
    inv: self.password is not None
    """
```

## Context Isolation

Each phase runs as a separate agent with its own context. To prevent any single agent from
overloading, the artifact pipeline is designed so each phase reads only what it needs:

| Phase | Reads | Does NOT read |
|-------|-------|---------------|
| Phase 1 (Explore) | orm-detection.json, source files | schema-constraints.json, SKILL.md best practices |
| Phase 2 (Plan) | contract-targets.json (includes source excerpts), schema-constraints.json, SKILL.md | source files (already embedded in targets artifact) |
| Phase 3 (Apply) | contract-plan.md, source files (to edit) | contract-targets.json, schema-constraints.json, SKILL.md |
| Phase 4 (Validate) | Modified source files (via CrossHair CLI) | Everything else — this is just a bash command |

The key design decision: **Phase 1 embeds source code into contract-targets.json** so
Phase 2 (the heaviest thinking phase) never needs to re-read source files. This keeps the
planner focused on contract design rather than code exploration.

Phase 3 must read source files again (to edit them), but its task is mechanical — it just
applies the plan — so the extra context is not a problem.

## Workflow

### Phase 1: Explore (Find Contract Targets)

Spawn Explore agent to fan out from model files. This phase produces a **self-contained**
artifact that includes source excerpts, so downstream phases don't re-read source files.

```
Task(subagent_type="Explore", prompt="""
Identify classes and functions that should receive PEP 316 contracts.

Strategy: start from model files and fan out to callers.

1. Read .claude/artifacts/crosshair-bugs/orm-detection.json for model file list
2. For each model file:
   a. Identify model classes (these are candidates for class invariants)
   b. Identify business methods on model classes
      (e.g., Article.favourite, UserProfile.follow — NOT __init__, __repr__)
   c. Identify CRUDMixin or base class methods if they contain logic
3. From model files, trace imports outward to find:
   a. View/route functions that call model methods or query the DB
   b. Service-layer functions between routes and models (if any)
4. Exclude:
   - Serializers / schema classes (data formatting only)
   - Config, app factory, blueprint registration
   - Extension setup (unless it contains business logic like CRUDMixin)
   - Test files
   - Functions that are pure boilerplate wrappers with no logic

IMPORTANT: For each target, include the actual source code. This artifact must be
self-contained so the planner agent does not need to re-read source files.

For each class, record:
- file: relative path
- class_name: name of the class
- non_nullable_fields: list of fields from schema that are nullable=false
- has_docstring: whether the class already has a docstring
- source: the full class definition (column declarations, methods, everything between
  `class Name(...):` and the next top-level definition)

For each function, record:
- file: relative path
- function: name (with class prefix for methods, e.g., "Article.favourite")
- signature: parameter list as written in source
- intent: one-line description of what the function does
- db_ops: list from [query, create, update, delete, relationship_mutation]
- returns: what the function returns (type or description)
- raises: exceptions the function may raise (if apparent from code)
- has_docstring: whether the function already has a docstring
- source: the complete function body as it appears in the file (including decorators)

Write to .claude/artifacts/crosshair-bugs/contract-targets.json:
{
  "classes": [
    {
      "file": "conduit/user/models.py",
      "class_name": "User",
      "non_nullable_fields": ["username", "email", "password"],
      "has_docstring": false,
      "source": "class User(Model):\n    __tablename__ = 'users'\n    id = db.Column(...)  \n    ..."
    }
  ],
  "functions": [
    {
      "file": "conduit/articles/views.py",
      "function": "make_article",
      "signature": "(body, title, description, tagList=None)",
      "intent": "Create article with slug, author, and tags",
      "db_ops": ["create", "query"],
      "returns": "Article instance",
      "raises": ["IntegrityError"],
      "has_docstring": false,
      "source": "@blueprint.route('/articles', methods=('POST',))\n@jwt_required\ndef make_article(...):\n    ..."
    }
  ]
}
""")
```

### Phase 2: Plan Contracts

Spawn Planner agent to design contracts. The planner reads contract-targets.json (which
already contains source code) and schema-constraints.json, so it does NOT need to read
any source files directly.

```
Task(subagent_type="planner", prompt="""
Plan PEP 316 contracts for business logic classes and functions.

Inputs:
1. Read .claude/artifacts/crosshair-bugs/contract-targets.json
   (contains source code for all targets — do NOT re-read source files)
2. Read .claude/artifacts/crosshair-bugs/schema-constraints.json
3. Read .claude/skills/generate-contracts/SKILL.md for best practices and syntax reference

For each target CLASS, determine invariants:
- Derive from non-nullable schema columns → inv: self.field is not None
- Only include fields that are truly always non-None after __init__
- Don't invariant-check nullable fields or optional relationships

For each target FUNCTION, determine pre/post conditions:

**Preconditions (pre:)** — what must be true for the function to behave correctly:
- Parameter validity (not None when required)
- Business rules the schema can't express (e.g., cannot follow yourself)
- NOT type checks, NOT framework state, NOT constraints already in stubs

**Postconditions (post:)** — what the function guarantees when it returns:
- Return value properties (use __return__ to reference it)
- State changes on self or parameters
- NOT implementation details, NOT timing, NOT restating the body

For each contract, provide:
- The exact PEP 316 line(s) to add
- Brief rationale (one line explaining why)
- Any contracts you considered but rejected, with reason

Write to .claude/artifacts/crosshair-bugs/contract-plan.md:

# Contract Plan

## Class Invariants

### User (conduit/user/models.py)
- `inv: self.username is not None` — schema: nullable=false
- `inv: self.email is not None` — schema: nullable=false
- REJECTED: `inv: self.bio is not None` — schema: nullable=true, bio is optional

## Function Contracts by File

### conduit/articles/views.py

#### make_article(body, title, description, tagList=None)
**Preconditions:**
- `pre: title is not None` — function calls slugify(title) which fails on None
- REJECTED: `pre: len(title) > 0` — empty title is valid, produces empty slug

**Postconditions:**
- `post: __return__ is not None` — function always creates and returns an article
- `post: __return__.slug is not None` — slug is auto-generated in __init__

### <next file>
...

## Edge Cases and Notes
- [any targets where contracts are unclear or require discussion]

Do NOT write code — just the plan in markdown.
""")
```

### Phase 3: Apply Contracts

Spawn Generator agent to add docstring contracts:

```
Task(subagent_type="generator", prompt="""
Add PEP 316 docstring contracts to source files based on plan.

1. Read .claude/artifacts/crosshair-bugs/contract-plan.md
2. For each file in the plan:
   a. Read the source file
   b. For each CLASS with invariants:
      - If the class has an existing docstring, append inv: lines after the description
        (separated by a blank line)
      - If the class has no docstring, add a docstring with just the inv: lines
   c. For each FUNCTION with pre/post conditions:
      - If the function has an existing docstring, append pre:/post: lines after the
        description (separated by a blank line)
      - If the function has no docstring, add a docstring with just the pre:/post: lines
   d. Write the updated file
   e. Validate: python -m py_compile <file>

Docstring rules:
- Use triple double quotes
- Place contracts after any existing description text, separated by a blank line
- Put pre: lines before post: lines
- One condition per line
- Preserve existing indentation
- Do NOT modify function/method bodies — only add/update docstrings

If py_compile fails:
- Check for syntax errors in condition expressions
- Check docstring quoting and indentation
- Fix and re-validate before moving to next file
""")
```

### Phase 4: Validate Contract Syntax

Quick smoke test to confirm CrossHair can find and parse the contracts. This is NOT
a bug-finding run — just a syntax check.

```bash
# Run CrossHair with a 1-second timeout per condition.
# We only care that it parses contracts without errors, not that it finds bugs.
crosshair check <file> \
  --per_condition_timeout 1 \
  --analysis_kind PEP316 \
  2>&1
```

Run this on each file modified in Phase 3. If CrossHair reports parse errors or
expression errors (NameError, SyntaxError), fix the contract docstring and re-run.
Timeouts and "no violation found" are both fine — they mean the contract was parsed
successfully.

## Output

- `.claude/artifacts/crosshair-bugs/contract-targets.json` — discovered targets
- `.claude/artifacts/crosshair-bugs/contract-plan.md` — planned contracts with rationale
- Modified source files with PEP 316 docstring contracts

## Resuming

- Phase 2+ can read `contract-targets.json`
- Phase 3 can read `contract-plan.md`
