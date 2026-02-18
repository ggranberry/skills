# Phase 1: Explore — Gather ORM and Schema Information

Spawn as: `Task(subagent_type="Explore")`

Gather ORM type, model locations, and schema details needed to generate stubs.

## Instructions

1. Run detect-orm: `bash .claude/skills/detect-orm/scripts/detect-orm.sh`
2. For each model file found, extract schema:
   - Table names
   - Column names, types, and constraints (nullable, unique, primary_key, foreign_key, check)
   - Enum values if present
3. Identify the session/database object:
   - Module path (e.g., `conduit.extensions`)
   - Variable name (e.g., `db`)
   - CRUD mixin module if present

## Output

Return JSON to `.claude/artifacts/crosshair-bugs/orm-detection.json`:

```json
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
```
