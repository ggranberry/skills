#!/usr/bin/env python3
"""Parse a CrossHair ORM stub file and extract the vocabulary needed by
analyze_stub_effectiveness.py:

- stubbed_models: class names whose `.objects` was replaced with MockManager
  (Django) or whose query path was monkey-patched (SQLAlchemy, etc).
- factory_models: subset whose stub generates a SimpleNamespace mock with
  per-model attribute fields (rather than just `proxy_for_type`).
- instance_attrs: all attribute names that any factory creates on a mock
  instance. Used to detect `<param>.<stub_attr>` patterns in callers.
- plural_hints: lowercased plural -> singular ModelName, used to detect
  parameters that look like QuerySet[<Model>].

Detection heuristics (best-effort, regex + AST):

1. `MockManager(<X>)` constructor calls — X is a stubbed model.
2. `<X>.objects = MockManager(<X>)` assignments — same.
3. `<X>.query = ...` assignments (SQLAlchemy pattern).
4. Class definitions in the stub file named like `Mock<X>` or `Stub<X>`.
5. Branches in factory functions of the form `if <var> == '<X>':` or
   `if <expr>.__name__ == '<X>':`.
6. Keyword args inside `SimpleNamespace(...)` calls — collected as
   instance_attrs.
7. `from <module> import <X>` paired with any of (1)-(5) confirms <X>.

If detection misses or over-detects, the user can supply a JSON config via
`--overrides <path>` whose keys override the auto-detected fields.

Usage:
    inventory_stubs.py <stub_file> [--overrides config.json] --output out.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


# Built-in / stdlib / framework names we never want to treat as stubbed models
NAME_DENYLIST = {
    "Any", "Optional", "List", "Tuple", "Dict", "Set", "Union", "Callable",
    "Generic", "T", "SimpleNamespace", "MockManager", "MockQuerySet",
    "MockRelatedManager", "MagicMock", "Mock", "QuerySet", "Manager",
    "Model", "BaseManager", "Session", "Query", "Engine", "Connection",
    "datetime", "date", "time", "timedelta", "Decimal", "Path", "str",
    "int", "float", "bool", "bytes", "object", "type", "True", "False",
    "None", "self", "cls",
}


def is_modelish_name(name: str) -> bool:
    """A model class name is PascalCase, starts uppercase, not in denylist."""
    if not name or not name[0].isupper():
        return False
    if name in NAME_DENYLIST:
        return False
    if name.startswith("_"):
        return False
    return True


def extract_mockmanager_args(tree: ast.AST) -> set[str]:
    """Find `MockManager(<X>)` and `MockManager[<X>](...)` arg names."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"MockManager", "MockQuerySet"}:
                if node.args and isinstance(node.args[0], ast.Name):
                    if is_modelish_name(node.args[0].id):
                        found.add(node.args[0].id)
    return found


def extract_objects_assignments(tree: ast.AST) -> set[str]:
    """Find `<X>.objects = ...` assignments where <X> is a Name."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Attribute) and tgt.attr in {"objects", "query"}:
                    if isinstance(tgt.value, ast.Name) and is_modelish_name(tgt.value.id):
                        found.add(tgt.value.id)
    return found


def extract_factory_branches(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Find `if <expr> == '<Name>':` branches inside functions. Returns
    (model_names_seen, attribute_names_from_SimpleNamespace_in_branches).
    """
    factory_models: set[str] = set()
    instance_attrs: set[str] = set()

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            # if <expr> == '<Name>':
            if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
                left = node.test.left
                comps = node.test.comparators
                ops = node.test.ops
                for op, right in zip(ops, comps):
                    if isinstance(op, ast.Eq) and isinstance(right, ast.Constant) and isinstance(right.value, str):
                        if is_modelish_name(right.value):
                            factory_models.add(right.value)
                            # Walk this branch for SimpleNamespace kwargs
                            for sub in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "SimpleNamespace":
                                    for kw in sub.keywords:
                                        if kw.arg and not kw.arg.startswith("**"):
                                            instance_attrs.add(kw.arg)
    return factory_models, instance_attrs


def extract_imports(tree: ast.AST) -> dict[str, str]:
    """Map imported class names to their source module (for context)."""
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if is_modelish_name(name):
                    imports[name] = node.module or ""
    return imports


def derive_plural_hints(models: set[str]) -> dict[str, str]:
    """Generate likely plural-form parameter names for each model.
    e.g. 'Sleep' -> {'sleeps': 'Sleep', 'sleep': 'Sleep'}
         'Feeding' -> {'feedings': 'Feeding'}
         'Child' -> {'children': 'Child', 'child': 'Child', 'childs': 'Child'}
         'TummyTime' -> {'tummy_times': 'TummyTime', 'tummytimes': 'TummyTime'}
    """
    irregular = {
        "Child": ["children", "child"],
        "Person": ["people", "person"],
        "Datum": ["data", "datum"],
    }
    out: dict[str, str] = {}
    for m in models:
        lower = m.lower()
        out[lower] = m  # singular
        if m in irregular:
            for p in irregular[m]:
                out[p] = m
            continue
        # snake_case version
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", m).lower()
        out[snake] = m
        out[f"{snake}s"] = m
        out[f"{lower}s"] = m
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stub_file", type=Path, help="Path to the project's CrossHair stub file (e.g. _crosshair_stubs.py)")
    parser.add_argument("--overrides", type=Path, default=None, help="Optional JSON file whose keys override the auto-detected fields")
    parser.add_argument("--output", type=Path, default=Path(".claude/artifacts/crosshair-stub-effectiveness/stub-inventory.json"))
    args = parser.parse_args()

    if not args.stub_file.exists():
        print(f"ERROR: stub file not found: {args.stub_file}", file=sys.stderr)
        sys.exit(2)

    src = args.stub_file.read_text()
    tree = ast.parse(src, filename=str(args.stub_file))

    mm_models = extract_mockmanager_args(tree)
    assign_models = extract_objects_assignments(tree)
    factory_models, instance_attrs = extract_factory_branches(tree)
    imports = extract_imports(tree)

    stubbed_models = mm_models | assign_models | factory_models

    # Common attrs across many model factories (id, created_at, updated_at, etc.)
    common_attrs = {"id", "model_name", "tags", "child", "child_id"}
    instance_attrs |= common_attrs

    plural_hints = derive_plural_hints(stubbed_models)

    inventory = {
        "stub_file": str(args.stub_file),
        "stubbed_models": sorted(stubbed_models),
        "factory_models": sorted(factory_models),
        "instance_attrs": sorted(instance_attrs),
        "plural_hints": plural_hints,
        "detection_signals": {
            "mockmanager_constructor": sorted(mm_models),
            "objects_assignment": sorted(assign_models),
            "factory_branch": sorted(factory_models),
            "imports_seen": imports,
        },
        "extra_orm_patterns": [],  # Hook for user overrides
    }

    if args.overrides and args.overrides.exists():
        overrides = json.loads(args.overrides.read_text())
        for key in ("stubbed_models", "factory_models", "instance_attrs", "plural_hints", "extra_orm_patterns"):
            if key in overrides:
                # Merge for lists, replace for dicts
                if isinstance(inventory[key], list):
                    inventory[key] = sorted(set(inventory[key]) | set(overrides[key]))
                elif isinstance(inventory[key], dict):
                    inventory[key] = {**inventory[key], **overrides[key]}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2))

    print(f"Wrote {args.output}")
    print(f"  Stubbed models:    {len(inventory['stubbed_models'])}")
    print(f"  Factory models:    {len(inventory['factory_models'])}")
    print(f"  Instance attrs:    {len(inventory['instance_attrs'])}")
    print(f"  Plural hints:      {len(inventory['plural_hints'])}")

    if not inventory["stubbed_models"]:
        print("WARNING: no stubbed models detected. Check the stub file format,", file=sys.stderr)
        print("or supply --overrides with at least a stubbed_models list.", file=sys.stderr)


if __name__ == "__main__":
    main()
