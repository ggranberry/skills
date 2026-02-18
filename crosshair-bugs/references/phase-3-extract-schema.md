# Phase 3: Extract Schema Constraints

Spawn as: `Task(subagent_type="Explore")`

Extract database constraints from model files.

## Instructions

1. Read `.claude/artifacts/crosshair-bugs/orm-detection.json` for model file list
2. For each model file, extract columns and constraints:
   - nullable (true/false, default true)
   - unique (true/false)
   - primary_key (true/false)
   - foreign_key (reference string)
   - check (constraint expression)
   - enum (list of values)
   - type with length (e.g., String(100))

3. Write to `.claude/artifacts/crosshair-bugs/schema-constraints.json`:
```json
{
  "models": [
    {
      "class": "User",
      "module": "conduit.user.models",
      "table": "users",
      "columns": {
        "id": {"type": "Integer", "primary_key": true},
        "email": {"type": "String(100)", "nullable": false, "unique": true},
        "age": {"type": "Integer", "nullable": true, "check": "age >= 0"},
        "status": {"type": "Enum", "values": ["active", "inactive"]}
      }
    }
  ]
}
```
