---
name: detect-orm
description: Detect which ORM framework(s) a Python project uses. Use when analyzing a new codebase or before making database-related changes.
---

# Detect ORM

Identifies ORM frameworks used in a Python project by analyzing dependencies, imports, and configuration files.

## Instructions

1. **Run the detection script** to get structured results:
   ```bash
   bash .claude/skills/detect-orm/scripts/detect-orm.sh [target-directory]
   ```
   If no directory is specified, it scans the current directory.

2. **Parse the JSON output** which includes:
   - `orms_detected`: Array of detected ORMs with confidence levels
   - `evidence`: What triggered each detection (dependency, import, or config)
   - `model_files`: Python files containing model definitions

3. **Present findings to the user** including:
   - Primary ORM detected (highest confidence)
   - Key model files they should know about
   - Any secondary ORMs (some projects use multiple)

4. **If no ORM is detected**, inform the user and suggest:
   - The project may use raw SQL
   - Dependencies might be in an unusual location
   - It could be a new project without database setup yet

## Supported ORMs

| ORM | Detection Signals |
|-----|-------------------|
| SQLAlchemy | `sqlalchemy` dependency, `declarative_base`, `alembic.ini` |
| Django ORM | `django` dependency, `models.Model`, `manage.py`, `DATABASES` config |
| Peewee | `peewee` dependency/imports |
| SQLModel | `sqlmodel` dependency, `SQLModel` base class |
| Tortoise | `tortoise-orm` dependency/imports |

## Examples

### Basic usage
```
User: /detect-orm
Assistant: [Runs detect-orm.sh, parses JSON, presents findings]

Detected: SQLAlchemy (high confidence)

Evidence:
- Dependency: sqlalchemy==2.0.0 in requirements.txt
- Config: alembic.ini present (migrations configured)

Model files:
- src/models/user.py
- src/models/product.py
```

### Scanning a specific directory
```
User: /detect-orm ./backend
Assistant: [Runs detect-orm.sh ./backend]

Detected: Django ORM (high confidence)

Evidence:
- Dependency: Django==4.2 in requirements.txt
- Config: manage.py with Django setup
- Config: settings.py with DATABASES configuration

Model files:
- backend/users/models.py
- backend/orders/models.py
```

### Multiple ORMs detected
```
User: /detect-orm
Assistant: [Presents both findings]

Detected multiple ORMs:

1. SQLAlchemy (high confidence)
   - Primary application ORM
   - Models in src/models/

2. Django (low confidence)
   - May be a test dependency
   - No model files found

The project primarily uses SQLAlchemy.
```

### No ORM found
```
User: /detect-orm
Assistant:
No ORM framework detected in this project.

This could mean:
- The project uses raw SQL queries
- Database dependencies are in a non-standard location
- This is a new project without database setup

Would you like me to search for raw SQL patterns instead?
```
