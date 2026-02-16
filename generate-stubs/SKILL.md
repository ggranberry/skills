---
name: generate-stubs
description: Generate CrossHair stubs for ORM database calls. Orchestrates multiple agents to detect ORM, extract schema, generate stubs, and plan constraint application.
---

# Generate Stubs

Generates Python stub files that replace ORM database calls with symbolic values for CrossHair analysis.

## Purpose

CrossHair performs symbolic execution but cannot analyze real database calls. These stubs:

1. **Replace ORM methods** (`.first()`, `.all()`, `.get()`) with symbolic returns via `proxy_for_type()`
2. **Apply database constraints** to the symbolic state space via `context_statespace().add()`

This ensures CrossHair explores code paths with realistic database values that respect schema constraints.

## Workflow

### Phase 1: Explore Agent (Information Gathering)

Spawn an Explore agent to gather ORM and schema information:

```
Task(subagent_type="Explore", prompt="""
Gather database schema information:

1. Run detect-orm: `bash .claude/skills/detect-orm/scripts/detect-orm.sh`
2. For each model file found, extract schema (table names, columns, types, constraints)

Return JSON:
{
  "orm": "sqlalchemy",
  "project_name": "conduit",
  "models": [
    {
      "table": "users",
      "class": "User",
      "module": "conduit.user.models",
      "columns": {
        "id": {"type": "Integer", "primary_key": true},
        "email": {"type": "String(100)", "nullable": false, "unique": true},
        "age": {"type": "Integer", "nullable": true, "check": "age >= 0"},
        "status": {"type": "Enum", "values": ["active", "inactive"]}
      }
    }
  ],
  "session_module": "conduit.extensions",
  "session_name": "db",
  "crud_mixin_module": "conduit.extensions"
}
""")
```

### Phase 2: Generator Agent (Mechanical Stub Creation)

Spawn a Generator agent to create the base stub file:

```
Task(subagent_type="generator", prompt="""
Create base stub file from template.

ORM: {{ orm }}
Schema: {{ JSON from Phase 1 }}

1. Read template: `.claude/skills/generate-stubs/templates/{{ orm }}_stubs.py.jinja`
2. Fill template with:
   - project_name
   - timestamp (current time)
   - models (for import statements and MockQuery setup)
   - session_module, session_name
   - crud_mixin_module (if present)
3. Write to `_crosshair_stubs.py`
4. Validate: `python -m py_compile _crosshair_stubs.py`

Do NOT add constraint logic yet - that comes in Phase 3.
""")
```

### Phase 3: Planner Agent (Constraint Translation)

Spawn a Planner agent to plan constraint application:

```
Task(subagent_type="planner", prompt="""
Plan how to translate database constraints to CrossHair state space constraints.

Schema: {{ JSON from Phase 1 }}

For each model and its columns, plan the constraint code:

| Constraint | Translation |
|------------|-------------|
| nullable=false | `space.add(result.field is not None)` |
| check: "age >= 0" | `space.add(result.age >= 0)` |
| enum: ["a", "b"] | `space.add(z3.Or(result.x == 'a', result.x == 'b'))` |
| String(N) | `space.add(len(result.field) <= N)` |
| foreign_key | Document the relationship (may affect test setup) |

Return a plan with:
1. The `_apply_constraints(result, model_type)` function code
2. Any imports needed (z3, etc.)
3. Notes on edge cases or limitations
""")
```

### Phase 4: Integration

Add the constraint code from Phase 3 to the stub file:

1. Read `_crosshair_stubs.py`
2. Insert the `_apply_constraints` function from Planner
3. Update terminal methods (`.first()`, `.get()`, etc.) to call `_apply_constraints`
4. Add any required imports
5. Re-validate: `python -m py_compile _crosshair_stubs.py`

## Templates

Templates are in `.claude/skills/generate-stubs/templates/`:

- `sqlalchemy_stubs.py.jinja` - SQLAlchemy/Flask-SQLAlchemy
- `django_stubs.py.jinja` - Django ORM

Templates contain:
- MockQuery/MockQuerySet classes with chainable and terminal methods
- MockSession/MockManager classes
- `install_stubs()` function to monkey-patch models
- Placeholder for constraint application (filled in Phase 4)

## Output

Final `_crosshair_stubs.py` contains:
- Symbolic query/session classes
- Constraint application function
- Auto-install on import

Usage:
```python
# In conftest.py or test setup
import _crosshair_stubs  # Auto-installs stubs
```
