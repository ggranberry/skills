
#!/usr/bin/env bash
# detect-orm.sh - Detect ORM frameworks in a Python project
# Outputs JSON with detected ORMs, confidence levels, and evidence

set -euo pipefail

TARGET_DIR="${1:-.}"

# Initialize results
declare -A ORM_FOUND
declare -a EVIDENCE
declare -a MODEL_FILES

# Helper to add evidence
add_evidence() {
    local type="$1" file="$2" match="$3"
    EVIDENCE+=("{\"type\":\"$type\",\"file\":\"$file\",\"match\":\"$match\"}")
}

# Check dependency files for ORM packages
check_dependencies() {
    local dep_files=("requirements.txt" "requirements-dev.txt" "pyproject.toml" "setup.py" "setup.cfg" "Pipfile")
    for dep_file in "${dep_files[@]}"; do
        local filepath="$TARGET_DIR/$dep_file"
        [[ -f "$filepath" ]] || continue

        # SQLAlchemy
        if grep -qiE '(^|\s|"|'"'"')sqlalchemy' "$filepath" 2>/dev/null; then
            ORM_FOUND[sqlalchemy]="dependency"
            local match=$(grep -iE '(^|\s|"|'"'"')sqlalchemy' "$filepath" | head -1 | tr -d '\n' | sed 's/"/\\"/g')
            add_evidence "dependency" "$dep_file" "$match"
        fi

        # Flask-SQLAlchemy
        if grep -qiE 'flask-sqlalchemy' "$filepath" 2>/dev/null; then
            ORM_FOUND[sqlalchemy]="dependency"
            add_evidence "dependency" "$dep_file" "flask-sqlalchemy"
        fi

        # Django
        if grep -qiE '(^|\s|"|'"'"')django[^-]' "$filepath" 2>/dev/null; then
            ORM_FOUND[django]="dependency"
            local match=$(grep -iE '(^|\s|"|'"'"')django[^-]' "$filepath" | head -1 | tr -d '\n' | sed 's/"/\\"/g')
            add_evidence "dependency" "$dep_file" "$match"
        fi

        # Peewee
        if grep -qiE '(^|\s|"|'"'"')peewee' "$filepath" 2>/dev/null; then
            ORM_FOUND[peewee]="dependency"
            add_evidence "dependency" "$dep_file" "peewee"
        fi

        # SQLModel
        if grep -qiE '(^|\s|"|'"'"')sqlmodel' "$filepath" 2>/dev/null; then
            ORM_FOUND[sqlmodel]="dependency"
            add_evidence "dependency" "$dep_file" "sqlmodel"
        fi

        # Tortoise ORM
        if grep -qiE 'tortoise-orm' "$filepath" 2>/dev/null; then
            ORM_FOUND[tortoise]="dependency"
            add_evidence "dependency" "$dep_file" "tortoise-orm"
        fi

        # Alembic (indicates SQLAlchemy)
        if grep -qiE '(^|\s|"|'"'"')alembic' "$filepath" 2>/dev/null; then
            ORM_FOUND[sqlalchemy]="${ORM_FOUND[sqlalchemy]:-alembic}"
            add_evidence "dependency" "$dep_file" "alembic (SQLAlchemy migrations)"
        fi
    done
}

# Check for ORM imports in Python files
check_imports() {
    # SQLAlchemy imports
    local sa_files=$(grep -rlE 'from sqlalchemy|import sqlalchemy' "$TARGET_DIR" --include="*.py" 2>/dev/null | head -5 || true)
    if [[ -n "$sa_files" ]]; then
        ORM_FOUND[sqlalchemy]="${ORM_FOUND[sqlalchemy]:-import}"
        while IFS= read -r f; do
            if [[ -n "$f" ]]; then
              add_evidence "import" "${f#$TARGET_DIR/}" "from sqlalchemy..."
            fi
        done <<< "$sa_files"
    fi

    # Django imports
    local django_files=$(grep -rlE 'from django\.db|import django\.db' "$TARGET_DIR" --include="*.py" 2>/dev/null | head -5 || true)
    if [[ -n "$django_files" ]]; then
        ORM_FOUND[django]="${ORM_FOUND[django]:-import}"
        while IFS= read -r f; do
            if [[ -n "$f" ]]; then
              add_evidence "import" "${f#$TARGET_DIR/}" "from django.db..."
            fi
        done <<< "$django_files"
    fi

    # Peewee imports
    local peewee_files=$(grep -rlE 'from peewee|import peewee' "$TARGET_DIR" --include="*.py" 2>/dev/null | head -5 || true)
    if [[ -n "$peewee_files" ]]; then
        ORM_FOUND[peewee]="${ORM_FOUND[peewee]:-import}"
        while IFS= read -r f; do
            if [[ -n "$f" ]]; then
              add_evidence "import" "${f#$TARGET_DIR/}" "from peewee..."
            fi
        done <<< "$peewee_files"
    fi

    # SQLModel imports
    local sqlmodel_files=$(grep -rlE 'from sqlmodel|import sqlmodel' "$TARGET_DIR" --include="*.py" 2>/dev/null | head -5 || true)
    if [[ -n "$sqlmodel_files" ]]; then
        ORM_FOUND[sqlmodel]="${ORM_FOUND[sqlmodel]:-import}"
        while IFS= read -r f; do
            if [[ -n "$f" ]]; then
              add_evidence "import" "${f#$TARGET_DIR/}" "from sqlmodel..."
            fi
        done <<< "$sqlmodel_files"
    fi

    # Tortoise imports
    local tortoise_files=$(grep -rlE 'from tortoise|import tortoise' "$TARGET_DIR" --include="*.py" 2>/dev/null | head -5 || true)
    if [[ -n "$tortoise_files" ]]; then
        ORM_FOUND[tortoise]="${ORM_FOUND[tortoise]:-import}"
        while IFS= read -r f; do
            if [[ -n "$f" ]]; then
              add_evidence "import" "${f#$TARGET_DIR/}" "from tortoise..."
            fi
        done <<< "$tortoise_files"
    fi
}

# Check for config files
check_config_files() {
    # Alembic config (SQLAlchemy)

    if [[ -f "$TARGET_DIR/alembic.ini" ]]; then
        ORM_FOUND[sqlalchemy]="${ORM_FOUND[sqlalchemy]:-config}"
        add_evidence "config" "alembic.ini" "Alembic migrations configured"
    fi

    # Django manage.py
    if [[ -f "$TARGET_DIR/manage.py" ]]; then
        if grep -q 'django' "$TARGET_DIR/manage.py"; then
          ORM_FOUND[django]="${ORM_FOUND[django]:-config}"
          add_evidence "config" "manage.py" "Django management script"
        fi
    fi


    # Django settings
    local settings_files=$(find "$TARGET_DIR" -name "settings.py" -type f 2>/dev/null | head -3 || true)
    while IFS= read -r sf; do
      if [[ -n "$sf" ]] && grep -q 'DATABASES' "$sf" 2>/dev/null; then
          ORM_FOUND[django]="${ORM_FOUND[django]:-config}"
          add_evidence "config" "${sf#$TARGET_DIR/}" "Django DATABASES config"
      fi
    done <<< "$settings_files"
}

# Find model files
find_model_files() {
    # SQLAlchemy models (declarative_base or Base inheritance)
    local sa_models=$(grep -rlE 'declarative_base|class \w+\([^)]*\b(Base|Model|db\.Model)\b[^)]*\)' "$TARGET_DIR" --include="*.py" 2>/dev/null | head -10 || true)
    while IFS= read -r f; do
        if [[ -n "$f" ]]; then
          MODEL_FILES+=("${f#$TARGET_DIR/}")
        fi
    done <<< "$sa_models"

    # Django models
    local django_models=$(grep -rlE 'class \w+\(models\.Model\)' "$TARGET_DIR" --include="*.py" 2>/dev/null | head -10 || true)
    while IFS= read -r f; do
        if [[ -n "$f" ]]; then 
          MODEL_FILES+=("${f#$TARGET_DIR/}")
        fi
    done <<< "$django_models"

    # SQLModel models
    local sqlmodel_models=$(grep -rlE 'class \w+\(SQLModel' "$TARGET_DIR" --include="*.py" 2>/dev/null | head -10 || true)
    while IFS= read -r f; do
        if [[ -n "$f" ]]; then 
          MODEL_FILES+=("${f#$TARGET_DIR/}")
        fi
    done <<< "$sqlmodel_models"
}

# Determine confidence level
get_confidence() {
    local orm="$1"
    local source="${ORM_FOUND[$orm]:-}"

    case "$source" in
        dependency) echo "high" ;;
        import)     echo "high" ;;
        config)     echo "medium" ;;
        alembic)    echo "medium" ;;
        *)          echo "low" ;;
    esac
}

# Build JSON output
build_json() {
    local orms_json=""
    local first=true

    for orm in "${!ORM_FOUND[@]}"; do
        local confidence=$(get_confidence "$orm")
        [[ "$first" == "true" ]] || orms_json+=","
        orms_json+="{\"orm\":\"$orm\",\"confidence\":\"$confidence\"}"
        first=false
    done

    local evidence_json=$(IFS=,; echo "${EVIDENCE[*]:-}")

    # Remove duplicates from model files
    local unique_models=()
    if [[ ${MODEL_FILES+x} ]]; then
      mapfile -t unique_models < <(printf '%s\n' "${MODEL_FILES[@]}" | sort -u)
    fi

    local models_json=""
    local first_model=true
    for mf in "${unique_models[@]}"; do
        [[ -n "$mf" ]] || continue
        [[ "$first_model" == "true" ]] || models_json+=","
        models_json+="\"$mf\""
        first_model=false
    done

    cat <<EOF
{
  "target_directory": "$TARGET_DIR",
  "orms_detected": [${orms_json}],
  "evidence": [${evidence_json}],
  "model_files": [${models_json}]
}
EOF
}

# Main
main() {
    if [[ ! -d "$TARGET_DIR" ]]; then
        echo "{\"error\": \"Directory not found: $TARGET_DIR\"}" >&2
        exit 1
    fi

    check_dependencies
    check_imports
    check_config_files
    find_model_files


    build_json
}

main
