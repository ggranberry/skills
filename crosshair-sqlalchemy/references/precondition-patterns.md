# SQLAlchemy Precondition Patterns

Patterns for writing `pre:` conditions in SQLAlchemy code that avoid symbolic noise. Planner agents in Phase 6 must apply these alongside the PEP 316 guide and the cross-cutting type-guard table in `crosshair-django/precondition-patterns.md`.

---

## Type guards — `hasattr` pattern table

CrossHair cannot symbolically construct live `Engine`, `Connection`, or `Session` objects. Use `hasattr` duck-typing guards instead of `isinstance(x, Connection)` which forces CrossHair to import and instantiate the class.

| Argument type | Safe `pre:` guard | Notes |
|---------------|-------------------|-------|
| `sqlalchemy.engine.Engine` | `pre: hasattr(engine, 'connect') and hasattr(engine, 'dispose')` | Both attrs distinguish from `Connection` (which has `connect` only via context) |
| `sqlalchemy.engine.Connection` | `pre: hasattr(conn, 'execute')` | Sufficient for the common case; covers cursors too |
| Cursor / `CursorResult` | `pre: hasattr(result, 'fetchone') and hasattr(result, 'fetchall')` | Distinguishes from `ScalarResult` |
| `ScalarResult` | `pre: hasattr(result, 'all') and hasattr(result, 'one')` | Note: SA 2.x `Result` exposes both — narrow further if needed |
| `sqlalchemy.orm.Session` | `pre: hasattr(session, 'query') and hasattr(session, 'commit')` | Distinguishes from request/transaction objects |
| `sqlalchemy.orm.Query` | `pre: hasattr(q, 'filter') and hasattr(q, 'all')` | Both attrs to distinguish from QuerySet-like objects |
| `Select` / `select(...)` | `pre: hasattr(stmt, 'compile') and hasattr(stmt, 'columns')` | Compiled statement type |
| `Column` | `pre: hasattr(col, 'name') and hasattr(col, 'type')` | Both required to distinguish from string column names |
| `Table` | `pre: hasattr(table, 'columns') and hasattr(table, 'name')` | |
| Mapped instance | `pre: hasattr(obj, '__table__') or hasattr(obj, '__mapper__')` | ORM-mapped class instances |
| `BindParameter` | `pre: hasattr(param, 'key') and hasattr(param, 'value')` | |

**Rule of thumb:** Prefer `hasattr` over `isinstance(x, sqlalchemy.engine.Connection)` because CrossHair cannot reliably import and instantiate SQLAlchemy classes (see `plugin-patterns.md` Pattern 2 — string-forward-ref failures).

---

## Don't generate symbolic SQL constructs

CrossHair will happily produce a symbolic `Select` with arbitrary symbolic clauses. The body of your function then tries to compile or execute it, which calls native SQL compilers and dialects.

**Wrong:** Let CrossHair generate the input statement:
```python
def list_records(stmt):
    """
    pre: hasattr(stmt, 'compile')
    """
    return conn.execute(stmt).fetchall()
```

CrossHair will produce a `Select` with symbolic columns/tables that don't correspond to any real schema, and `stmt.compile()` will fail or produce nonsense.

**Right:** Constrain inputs to plain Python primitives that the function uses to **build** the statement:
```python
def list_records(table_name: str, limit: int):
    """
    pre: isinstance(table_name, str) and table_name.isidentifier()
    pre: 1 <= limit <= 1000
    """
    stmt = select(metadata.tables[table_name]).limit(limit)
    return conn.execute(stmt).fetchall()
```

In general: take strings/ints in, build the SQL inside the function, and let the stub return a symbolic result.

---

## Empty-list pitfalls in `IN` and `OR` clauses

`column.in_([])` produces a `False` predicate that some SQLAlchemy versions warn about; `or_()` with no args raises. CrossHair often generates `[]` as a symbolic list.

**Pre-condition pattern:**
```python
def filter_by_ids(ids):
    """
    pre: isinstance(ids, list)
    pre: len(ids) > 0
    """
    return Model.query.filter(Model.id.in_(ids)).all()
```

If the function legitimately handles empty lists, document the branch and don't add the `len > 0` precondition — but be ready for CrossHair to produce empty-list counterexamples that exercise that branch.

---

## `scalar_one()` vs `scalar_one_or_none()`

`scalar_one()` raises `NoResultFound` or `MultipleResultsFound`. `scalar_one_or_none()` returns `None` for the empty case but still raises on multiple.

**Postcondition for `scalar_one_or_none()`:**
```python
def get_user_id(email):
    """
    pre: isinstance(email, str)
    post: __return__ is None or isinstance(__return__, int)
    raises: MultipleResultsFound
    """
    return session.execute(
        select(User.id).where(User.email == email)
    ).scalar_one_or_none()
```

CrossHair won't symbolically reproduce the database race condition that produces `MultipleResultsFound`, so list it under `raises:` rather than asserting it can't happen.

---

## Numeric / Decimal contracts

`Decimal` arithmetic in symbolic execution is slow and sometimes wrong. Where the function returns `Decimal` from a `Numeric` column:

**Wrong:** `post: __return__ >= 0`  — slow under symbolic Decimal

**Better:** Constrain via `hasattr` only, and verify the actual numeric properties in unit tests instead:
```python
post: hasattr(__return__, 'is_finite')   # works on float and Decimal
```

When the postcondition is critical, use `isinstance(__return__, (int, float, Decimal))` and test the function once with concrete inputs — leave deeper symbolic numeric reasoning to CrossHair's int/float types, not Decimal.

---

## When to update this file

Add entries for any SQLAlchemy idiom where the planner agent in Phase 6 would otherwise generate a contract that produces false-positive symbolic noise. Cite the symptom — e.g. "scalar_one_or_none false positive on empty result" — so future debuggers can pattern-match.
