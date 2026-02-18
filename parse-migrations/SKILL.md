---
name: parse-migrations
description: Parse migration files and model definitions to extract database schema as JSON. Use when extracting schema constraints for CrossHair stubs. Expects ORM type to be known (run detect-orm first). Not for writing or running migrations.
---

# Parse Migrations

Extracts database schema information from migration files and model definitions, outputting a structured JSON summary.

**Note:** This skill expects the ORM type to already be known. Run detect-orm first or use this skill via generate-stubs which orchestrates both.

## Instructions

1. **Use the ORM context** from a prior detect-orm call to know what patterns to look for:
   - SQLAlchemy/Flask-SQLAlchemy: `__tablename__`, `Column()`, `ForeignKey()`
   - Django: `models.Model`, `models.CharField`, etc.
   - Alembic migrations: `op.create_table()`, `sa.Column()`

2. **Find migration and model files** using Glob/Grep based on ORM:

   **SQLAlchemy/Alembic:**
   ```
   Glob: alembic/versions/*.py, migrations/versions/*.py
   Grep: __tablename__|Column\(|ForeignKey\(
   ```

   **Django:**
   ```
   Glob: */migrations/[0-9]*.py
   Grep: models\.Model|models\.\w+Field
   ```

3. **Read and extract** from each file:
   - Table names (`__tablename__` or `CREATE TABLE`)
   - Column names and types
   - Constraints: nullable, unique, primary_key, foreign_key, check
   - Enum values if present

4. **Return JSON** with this structure:
   ```json
   {
     "source_files": ["conduit/user/models.py"],
     "tables": {
       "users": {
         "model_class": "User",
         "module": "conduit.user.models",
         "columns": {
           "id": {
             "type": "Integer",
             "primary_key": true
           },
           "email": {
             "type": "String(100)",
             "nullable": false,
             "unique": true
           },
           "user_id": {
             "type": "Integer",
             "foreign_key": "users.id"
           }
         }
       }
     }
   }
   ```

5. **Validate the JSON**:
   ```bash
   echo '<json>' | python -m json.tool
   ```

## Extraction Patterns

| Pattern | Extract |
|---------|---------|
| `Column(db.String(N), nullable=False)` | `{"type": "String(N)", "nullable": false}` |
| `Column(db.Integer, unique=True)` | `{"type": "Integer", "unique": true}` |
| `Column(db.Integer, primary_key=True)` | `{"type": "Integer", "primary_key": true}` |
| `ForeignKey('table.col')` | `{"foreign_key": "table.col"}` |
| `Enum('a', 'b', 'c')` | `{"type": "Enum", "values": ["a", "b", "c"]}` |
| `CheckConstraint('expr')` | `{"check": "expr"}` |

## Example Output

```json
{
  "source_files": [
    "conduit/user/models.py",
    "conduit/articles/models.py"
  ],
  "tables": {
    "users": {
      "model_class": "User",
      "module": "conduit.user.models",
      "columns": {
        "id": {"type": "Integer", "primary_key": true},
        "username": {"type": "String(80)", "nullable": false, "unique": true},
        "email": {"type": "String(100)", "nullable": false, "unique": true},
        "password": {"type": "Binary(128)", "nullable": true},
        "created_at": {"type": "DateTime", "nullable": false},
        "bio": {"type": "String(300)", "nullable": true}
      }
    },
    "articles": {
      "model_class": "Article",
      "module": "conduit.articles.models",
      "columns": {
        "id": {"type": "Integer", "primary_key": true},
        "slug": {"type": "String(100)", "nullable": false, "unique": true},
        "title": {"type": "String(100)", "nullable": false},
        "author_id": {"type": "Integer", "foreign_key": "users.id"}
      }
    }
  }
}
```
