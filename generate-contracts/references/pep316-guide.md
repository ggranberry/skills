# PEP 316 Contract Guide

Reference material for writing PEP 316 docstring contracts for CrossHair symbolic analysis.

## Contents

- [Syntax Reference](#syntax-reference)
  - [Preconditions](#preconditions)
  - [Postconditions](#postconditions)
  - [Class Invariants](#class-invariants)
  - [Multi-line conditions](#multi-line-conditions)
- [Assertions in Function Bodies](#assertions-in-function-bodies)
- [Best Practices](#best-practices)
  - [What makes a good precondition](#what-makes-a-good-precondition)
  - [What makes a good postcondition](#what-makes-a-good-postcondition)
  - [What makes a good invariant](#what-makes-a-good-invariant)
  - [Contract strength: finding the sweet spot](#contract-strength-finding-the-sweet-spot)
  - [Docstring integration](#docstring-integration)
  - [Common contract patterns](#common-contract-patterns)

## Syntax Reference

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
    post: __return__.slug is not None
    post: __return__.author_id == self.id
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

## Assertions in Function Bodies

CrossHair also checks `assert` statements inside function bodies — these act as contracts on intermediate values rather than function boundaries. This is especially useful for loop invariants and multi-step mutations. See `.claude/skills/generate-contracts/references/assertions.md` for details.

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

**Why preconditions are valuable even without postconditions:**

Preconditions propagate *upward* through the call graph. When function `bar` has a precondition, CrossHair checks that every caller of `bar` satisfies it. This means a precondition on a low-level function can surface bugs in its callers — even if those callers have no contracts at all.

```python
def foo():
    """
    post: __return__ == 9
    """
    x = bar(10)     # CrossHair flags: foo() violates bar()'s precondition

def bar(x):
    """
    pre: x == 0
    """
    return x + 1
```

CrossHair reports that `foo` calls `bar` with `x=10`, violating `pre: x == 0`. The bug is in `foo` (the caller), but the precondition on `bar` is what makes it detectable. This is why **a function with only preconditions and no postconditions is still a useful contract** — it defines a boundary that callers must respect, and CrossHair enforces it across function boundaries.

### What makes a good postcondition

A postcondition should capture a **guarantee** — something the caller can rely on.
**A bare `post: __return__ is not None` is almost never a useful contract.** It restates the return type annotation and catches nothing interesting. If the only postcondition you can think of is "returns not None", **skip the postcondition entirely** — the function doesn't need one.

Good postconditions assert **semantic properties** of the return value: relationships between inputs and outputs, structural guarantees, state changes, or business invariants.

**Good postconditions:**
```python
def make_article(title, body, description, tagList=None):
    """
    post: __return__.slug is not None       # slug is auto-generated from title
    post: __return__.author_id == self.id   # article belongs to current user
    """

def merge(self, from_food, to_food):
    """
    pre: from_food != to_food
    post: __return__.id == to_food           # the target food survives
    """

def favourite(self, profile):
    """
    pre: profile is not None
    post: profile in self.favoriters        # state change guarantee
    """
```

**Bad postconditions (avoid these):**
```python
# TRIVIAL — just restates the type hint, catches no real bugs
# post: __return__ is not None

# Tests implementation detail, not a guarantee
# post: __return__.created_at <= datetime.utcnow()

# Too vague to catch anything
# post: __return__ is not None or __return__ is None

# Restates the function body
# post: __return__ == User.query.filter_by(email=email).first()

# Just checks the return type — use type annotations for this
# post: isinstance(__return__, bool)
```

**Rules:**
1. Assert properties of the return value, not how it was computed
2. **Never use `post: __return__ is not None` as the sole postcondition** — if you can't find a more meaningful property, omit the postcondition
3. Prefer postconditions that relate the return value to the inputs (e.g., `__return__.id == item_id`)
4. For functions that return None on failure, None *is* valid behavior — don't postcondition against it
5. For mutation functions that return the mutated object, check that the mutation stuck
6. If a function has no meaningful postcondition, **it's fine to have only preconditions** — don't force a postcondition just to have one

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
def create(cls, title, body, **kwargs):
    """
    pre: title is not None
    post: __return__.slug is not None   # slug derived from title
    post: __return__.author_id == self.id
    """
```

**CRUD update:**
```python
def update(self, item_id, data):
    """
    pre: self.id is not None
    pre: item_id is not None
    """
    # No postcondition needed — preconditions alone let CrossHair
    # verify callers pass valid arguments
```

**Merge / destructive operation:**
```python
def merge(self, from_id, to_id):
    """
    pre: from_id != to_id   # self-merge causes data loss
    pre: from_id is not None
    pre: to_id is not None
    post: __return__.id == to_id  # target survives
    """
```

**Query that may return None:**
```python
def get_article(slug):
    """
    pre: slug is not None
    """
    # No postcondition — None is valid (not found)
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
