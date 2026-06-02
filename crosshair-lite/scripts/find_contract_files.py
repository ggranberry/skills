#!/usr/bin/env python3
"""Find Python files that already contain PEP 316 contracts.

Scans source packages using AST parsing to find functions/methods with
pre:/post: directives and classes with inv: directives in their docstrings.

Usage:
    python find_contract_files.py [options]

Options:
    --base-path PATH        Project root directory (default: cwd)
    --packages PKG [PKG...] Source packages to scan (auto-detected if omitted)
    --exclude-dirs DIR ...  Additional directories to exclude
    --output PATH           Output path (default: .claude/artifacts/crosshair-lite/contract-files.json)
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path


DEFAULT_EXCLUDED_DIRS = {
    "tests", "test",
    "migrations", "alembic", "versions",
    "static", "templates", "assets",
    "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "node_modules", ".venv", "venv", "env",
    ".git", ".claude", ".github",
    "locale", "fixtures",
}

CONTRACT_RE = re.compile(r"^\s*(pre|post):\s*\S", re.MULTILINE)
INVARIANT_RE = re.compile(r"^\s*inv:\s*\S", re.MULTILINE)


def extract_contract_lines(docstring: str, pattern: re.Pattern) -> list[str]:
    """Extract contract directive lines from a docstring."""
    contracts = []
    for line in docstring.splitlines():
        stripped = line.strip()
        if pattern.match(line):
            contracts.append(stripped)
    return contracts


def scan_file(filepath: Path, rel_path: str) -> dict | None:
    """Parse a Python file and find all PEP 316 contracts in docstrings."""
    try:
        source = filepath.read_text()
    except (UnicodeDecodeError, OSError):
        return None

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return None

    functions_with_contracts = []
    pre_count = 0
    post_count = 0
    inv_count = 0

    def visit(node: ast.AST, class_name: str | None = None) -> None:
        nonlocal pre_count, post_count, inv_count

        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                # Check class docstring for inv:
                docstring = ast.get_docstring(child)
                if docstring:
                    inv_lines = extract_contract_lines(docstring, INVARIANT_RE)
                    if inv_lines:
                        inv_count += len(inv_lines)
                        functions_with_contracts.append({
                            "name": child.name,
                            "class_name": None,
                            "line": child.lineno,
                            "type": "class",
                            "contracts": inv_lines,
                        })
                visit(child, class_name=child.name)

            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                docstring = ast.get_docstring(child)
                if docstring:
                    contract_lines = extract_contract_lines(docstring, CONTRACT_RE)
                    if contract_lines:
                        local_pre = sum(1 for c in contract_lines if c.startswith("pre:"))
                        local_post = sum(1 for c in contract_lines if c.startswith("post:"))
                        pre_count += local_pre
                        post_count += local_post
                        functions_with_contracts.append({
                            "name": child.name,
                            "class_name": class_name,
                            "line": child.lineno,
                            "type": "function",
                            "contracts": contract_lines,
                        })

    visit(tree)

    if not functions_with_contracts:
        return None

    return {
        "path": rel_path,
        "contracts": {"pre": pre_count, "post": post_count, "inv": inv_count},
        "functions": functions_with_contracts,
    }


def detect_packages(base_path: Path) -> list[str]:
    """Find top-level Python packages by scanning for directories with __init__.py."""
    non_source_dirs = {
        "scripts", "tools", "docs", "deploy", "provision", "contrib",
        "examples", "benchmarks", "bin", "devtools", "puppet", "stubs",
    }
    packages = []
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


def scan_package(base_path: Path, package: str, extra_excluded: set[str]) -> tuple[list[dict], int]:
    """Scan a package for files with PEP 316 contracts."""
    package_dir = base_path / package
    if not package_dir.is_dir():
        return [], 0

    results = []
    files_scanned = 0

    for root, dirs, filenames in os.walk(package_dir):
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDED_DIRS and d not in extra_excluded]
        rel_root = Path(root).relative_to(base_path)

        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            files_scanned += 1
            filepath = Path(root) / filename
            rel_path = str(rel_root / filename)
            result = scan_file(filepath, rel_path)
            if result:
                results.append(result)

    return results, files_scanned


def main() -> None:
    parser = argparse.ArgumentParser(description="Find Python files with PEP 316 contracts")
    parser.add_argument("--base-path", type=Path, default=Path.cwd(),
                        help="Project root directory (default: cwd)")
    parser.add_argument("--packages", nargs="+",
                        help="Source packages to scan (auto-detected if omitted)")
    parser.add_argument("--exclude-dirs", nargs="*", default=[],
                        help="Additional directories to exclude")
    parser.add_argument("--output", type=Path,
                        default=Path(".claude/artifacts/crosshair-lite/contract-files.json"),
                        help="Output path")
    args = parser.parse_args()

    base_path = args.base_path.resolve()
    extra_excluded = set(args.exclude_dirs)

    if args.packages:
        packages = args.packages
    else:
        packages = detect_packages(base_path)
        if not packages:
            print("Error: No source packages found. Use --packages to specify them.", file=sys.stderr)
            sys.exit(1)

    print(f"Scanning packages: {', '.join(packages)}")

    all_files = []
    total_scanned = 0
    for package in packages:
        files, scanned = scan_package(base_path, package, extra_excluded)
        all_files.extend(files)
        total_scanned += scanned

    all_files.sort(key=lambda f: f["path"])
    total_contracts = sum(
        f["contracts"]["pre"] + f["contracts"]["post"] + f["contracts"]["inv"]
        for f in all_files
    )

    result = {
        "scan_root": str(base_path),
        "packages_scanned": packages,
        "files_scanned": total_scanned,
        "files_with_contracts": len(all_files),
        "total_contracts": total_contracts,
        "files": all_files,
    }

    output_path = args.output
    if not output_path.is_absolute():
        output_path = base_path / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Scanned {total_scanned} files across {len(packages)} packages")
    print(f"Found {len(all_files)} files with PEP 316 contracts ({total_contracts} total contracts)")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
