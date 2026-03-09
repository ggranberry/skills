#!/usr/bin/env python3
"""Phase 1: Discover all contract candidates in a Python codebase.

Performs a broad mechanical sweep to find functions/methods that could
receive PEP 316 contracts. Applies only objective exclusion rules —
subjective triage happens in Phase 2 (planners).

Works with any Python project. Determines source packages automatically
from orm-detection.json or by scanning for top-level Python packages.

Usage:
    python explore-contracts.py [options]

Options:
    --base-path PATH        Project root directory (default: cwd)
    --packages PKG [PKG...] Source packages to scan (auto-detected if omitted)
    --exclude-dirs DIR ...  Additional directories to exclude
    --orm-detection PATH    Path to orm-detection.json for auto-detecting packages
    --output PATH           Output path (default: .claude/artifacts/crosshair-bugs/contract-targets.json)
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path


# --- Default Exclusion Rules ---
# These are universal — they apply to any Python project.

DEFAULT_EXCLUDED_DIRS = {
    # Test directories
    "tests", "test",
    # Migration/schema directories
    "migrations", "alembic", "versions",
    # Static/template assets
    "static", "templates", "assets",
    # Build/cache artifacts
    "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    # Dependency directories
    "node_modules", ".venv", "venv", "env",
    # Tooling directories
    ".git", ".claude", ".github",
    # Locale/i18n
    "locale",
    # Test fixtures
    "fixtures",
}

DEFAULT_EXCLUDED_FILES = {
    "__init__.py", "conftest.py", "setup.py", "manage.py", "tests.py",
}

EXCLUDED_FILE_PATTERNS = [
    re.compile(r".*_test\.py$"),
    re.compile(r"test_.*\.py$"),
    re.compile(r".*tests\.py$"),
]

EXCLUDED_DUNDERS = {
    "__repr__", "__str__", "__hash__", "__eq__", "__lt__", "__le__",
    "__gt__", "__ge__", "__bool__", "__len__", "__contains__",
}


def is_excluded_dir(dirname: str, extra_excluded: set[str]) -> bool:
    return dirname in DEFAULT_EXCLUDED_DIRS or dirname in extra_excluded


def is_excluded_file(filename: str) -> bool:
    if filename in DEFAULT_EXCLUDED_FILES:
        return True
    for pat in EXCLUDED_FILE_PATTERNS:
        if pat.match(filename):
            return True
    return False


def is_trivial_body(node: ast.FunctionDef) -> bool:
    """Check if function body is trivial (single meaningful statement)."""
    body = node.body
    # Strip docstrings
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]

    meaningful = [s for s in body if not isinstance(s, ast.Pass)]
    if len(meaningful) == 0:
        return True
    if len(meaningful) == 1:
        stmt = meaningful[0]
        if isinstance(stmt, ast.Return):
            return True
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            if isinstance(stmt.exc, ast.Call):
                func = stmt.exc.func
                if isinstance(func, ast.Name) and func.id == "NotImplementedError":
                    return True
            elif isinstance(stmt.exc, ast.Name) and stmt.exc.id == "NotImplementedError":
                return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            if stmt.value.value is ...:
                return True
    return False


def is_pure_field_init(node: ast.FunctionDef) -> bool:
    """Check if __init__ only does self.x = param assignments."""
    body = node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]

    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if not (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"):
                    return False
            if isinstance(stmt.value, (ast.Name, ast.Constant)):
                continue
            return False
        elif isinstance(stmt, ast.AnnAssign):
            if (stmt.target and isinstance(stmt.target, ast.Attribute)
                    and isinstance(stmt.target.value, ast.Name)
                    and stmt.target.value.id == "self"):
                if stmt.value is None or isinstance(stmt.value, (ast.Name, ast.Constant)):
                    continue
            return False
        else:
            return False
    return True


def has_trivial_property_getter(node: ast.FunctionDef) -> bool:
    """Check if this is a @property with a trivial getter."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "property":
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            if len(body) == 1 and isinstance(body[0], ast.Return):
                return True
    return False


def is_pydantic_validator(node: ast.FunctionDef) -> bool:
    """Check if decorated with @validator/@field_validator/@model_validator."""
    for dec in node.decorator_list:
        name = None
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
            name = dec.func.id
        if name in ("validator", "field_validator", "model_validator"):
            return True
    return False


def get_function_signature(node: ast.FunctionDef) -> str:
    """Extract the parameter list as a string."""
    try:
        args = node.args
        parts: list[str] = []

        for arg in args.posonlyargs:
            parts.append(_format_arg(arg))
        if args.posonlyargs:
            parts.append("/")

        num_defaults = len(args.defaults)
        num_args = len(args.args)
        for i, arg in enumerate(args.args):
            default_idx = i - (num_args - num_defaults)
            if default_idx >= 0:
                parts.append(f"{_format_arg(arg)}=...")
            else:
                parts.append(_format_arg(arg))

        if args.vararg:
            parts.append(f"*{_format_arg(args.vararg)}")
        elif args.kwonlyargs:
            parts.append("*")

        for i, arg in enumerate(args.kwonlyargs):
            if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
                parts.append(f"{_format_arg(arg)}=...")
            else:
                parts.append(_format_arg(arg))

        if args.kwarg:
            parts.append(f"**{_format_arg(args.kwarg)}")

        return f"({', '.join(parts)})"
    except Exception:
        return "(...)"


def _format_arg(arg: ast.arg) -> str:
    if arg.annotation:
        try:
            return f"{arg.arg}: {ast.unparse(arg.annotation)}"
        except Exception:
            return arg.arg
    return arg.arg


def count_body_lines(node: ast.FunctionDef) -> int:
    """Count the number of lines in the function body."""
    if not node.body:
        return 0
    start = node.body[0].lineno
    end = node.end_lineno or node.body[-1].end_lineno or start
    return end - start + 1


def has_existing_docstring(node: ast.FunctionDef) -> bool:
    if node.body and isinstance(node.body[0], ast.Expr):
        val = node.body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            return True
    return False


def extract_functions_from_file(filepath: Path, source_lines: list[str]) -> list[dict]:
    """Parse a Python file and extract all non-excluded function metadata."""
    try:
        tree = ast.parse("".join(source_lines), filename=str(filepath))
    except SyntaxError:
        return []

    functions: list[dict] = []

    def visit_node(node: ast.AST, class_name: str | None = None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit_node(child, class_name=child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
                qualified_name = f"{class_name}.{name}" if class_name else name

                if name in EXCLUDED_DUNDERS:
                    continue
                if name == "__init__" and is_pure_field_init(child):
                    continue
                if is_trivial_body(child):
                    continue
                if has_trivial_property_getter(child):
                    continue
                if is_pydantic_validator(child):
                    continue

                line_count = count_body_lines(child)
                if line_count <= 1:
                    body = child.body
                    if (body and isinstance(body[0], ast.Expr)
                            and isinstance(body[0].value, ast.Constant)):
                        body = body[1:]
                    meaningful = [s for s in body if not isinstance(s, ast.Pass)]
                    if len(meaningful) <= 1:
                        continue

                functions.append({
                    "name": qualified_name,
                    "signature": get_function_signature(child),
                    "line_number": child.lineno,
                    "line_count": line_count,
                    "has_existing_docstring": has_existing_docstring(child),
                })

    visit_node(tree)
    return functions


def scan_directory(
    base_path: Path,
    package_name: str,
    extra_excluded_dirs: set[str],
) -> tuple[list[dict], int, int, int]:
    """Scan a package directory for contract candidates."""
    package_dir = base_path / package_name
    if not package_dir.is_dir():
        return [], 0, 0, 0

    files_result: list[dict] = []
    total_files = 0
    total_found = 0
    total_excluded = 0

    for root, dirs, filenames in os.walk(package_dir):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d, extra_excluded_dirs)]

        rel_root = Path(root).relative_to(base_path)

        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            if is_excluded_file(filename):
                continue

            total_files += 1
            filepath = Path(root) / filename
            rel_path = str(rel_root / filename)

            try:
                source_lines = filepath.read_text().splitlines(keepends=True)
            except (UnicodeDecodeError, OSError):
                continue

            if not any("def " in line for line in source_lines):
                continue

            functions = extract_functions_from_file(filepath, source_lines)

            all_defs = sum(1 for line in source_lines if re.match(r"\s*(async\s+)?def\s+", line))
            included = len(functions)
            excluded = all_defs - included
            total_found += all_defs
            total_excluded += excluded

            if functions:
                files_result.append({
                    "path": rel_path,
                    "functions": functions,
                })

    return files_result, total_files, total_found, total_excluded


def detect_packages_from_orm(base_path: Path, orm_detection_path: Path) -> list[str]:
    """Derive source packages from orm-detection.json model file paths."""
    try:
        with open(orm_detection_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    packages: set[str] = set()
    model_files = data.get("model_files", [])
    for mf in model_files:
        # Extract top-level package from path like "zerver/models/users.py"
        parts = Path(mf).parts
        if parts:
            candidate = parts[0]
            pkg_dir = base_path / candidate
            if pkg_dir.is_dir() and (pkg_dir / "__init__.py").exists():
                packages.add(candidate)

    return sorted(packages)


def detect_packages_by_scanning(base_path: Path) -> list[str]:
    """Find top-level Python packages by scanning for directories with __init__.py.

    Skips common infrastructure directories that have __init__.py but
    aren't application source code (scripts, tools, docs, etc.).
    """
    # Directories that often have __init__.py but aren't business logic
    non_source_dirs = {
        "scripts", "tools", "docs", "deploy", "provision", "contrib",
        "examples", "benchmarks", "bin", "devtools", "puppet", "stubs",
    }

    packages: list[str] = []
    try:
        entries = sorted(os.listdir(base_path))
    except OSError:
        return []

    for entry in entries:
        if entry.startswith(".") or entry.startswith("_"):
            continue
        if entry in DEFAULT_EXCLUDED_DIRS or entry in non_source_dirs:
            continue
        candidate = base_path / entry
        if candidate.is_dir() and (candidate / "__init__.py").exists():
            packages.append(entry)

    return packages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover contract candidates in a Python codebase"
    )
    parser.add_argument(
        "--base-path", type=Path, default=Path.cwd(),
        help="Project root directory (default: current directory)"
    )
    parser.add_argument(
        "--packages", nargs="+",
        help="Source packages to scan (auto-detected if omitted)"
    )
    parser.add_argument(
        "--exclude-dirs", nargs="*", default=[],
        help="Additional directories to exclude beyond the defaults"
    )
    parser.add_argument(
        "--orm-detection", type=Path,
        default=Path(".claude/artifacts/crosshair-bugs/orm-detection.json"),
        help="Path to orm-detection.json for auto-detecting packages"
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(".claude/artifacts/crosshair-bugs/contract-targets.json"),
        help="Output path for the manifest"
    )
    args = parser.parse_args()

    base_path = args.base_path.resolve()
    extra_excluded = set(args.exclude_dirs)

    # Resolve orm-detection path relative to base_path if not absolute
    orm_path = args.orm_detection
    if not orm_path.is_absolute():
        orm_path = base_path / orm_path

    # Determine packages to scan
    if args.packages:
        packages = args.packages
    else:
        # Scan for all top-level Python packages, supplemented by orm-detection
        scanned = detect_packages_by_scanning(base_path)
        from_orm = detect_packages_from_orm(base_path, orm_path)
        # Merge: scanning finds all packages, orm-detection catches any it missed
        packages = sorted(set(scanned) | set(from_orm))
        if not packages:
            print("Error: No source packages found. Use --packages to specify them.", file=sys.stderr)
            sys.exit(1)

    print(f"Scanning packages: {', '.join(packages)}")
    if extra_excluded:
        print(f"Additional excluded dirs: {', '.join(sorted(extra_excluded))}")

    all_files: list[dict] = []
    total_files_scanned = 0
    total_functions_found = 0
    total_functions_excluded = 0

    for package in packages:
        files, f_scanned, f_found, f_excluded = scan_directory(base_path, package, extra_excluded)
        all_files.extend(files)
        total_files_scanned += f_scanned
        total_functions_found += f_found
        total_functions_excluded += f_excluded

    all_files.sort(key=lambda f: f["path"])
    total_included = total_functions_found - total_functions_excluded

    result = {
        "source_packages": packages,
        "total_files_scanned": total_files_scanned,
        "total_functions_found": total_functions_found,
        "total_functions_excluded": total_functions_excluded,
        "total_functions_included": total_included,
        "files": all_files,
    }

    # Resolve output path relative to base_path if not absolute
    output_path = args.output
    if not output_path.is_absolute():
        output_path = base_path / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Scanned {total_files_scanned} files across {len(packages)} packages")
    print(f"Found {total_functions_found} function definitions")
    print(f"Excluded {total_functions_excluded} (trivial/dunder/etc)")
    print(f"Included {total_included} candidates across {len(all_files)} files")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
