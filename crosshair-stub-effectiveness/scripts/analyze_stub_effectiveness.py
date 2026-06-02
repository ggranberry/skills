#!/usr/bin/env python3
"""Static analyzer that classifies each contracted function by how much it
depends on the project's CrossHair ORM stubs.

Inputs:
- --inventory: JSON from inventory_stubs.py (stubbed_models, factory_models,
  instance_attrs, plural_hints, extra_orm_patterns)
- --contract-files: JSON from crosshair-lite's find_contract_files.py

Output:
- --output: stub-effectiveness.json with per-file and per-function buckets
  plus a summary.

Buckets:
- stub_required: body touches ORM/manager, OR a parameter is a stubbed model,
  OR a parameter is a QuerySet-typed plural hint, OR `attrs['<model>']`
  subscript, OR an attribute access on a stubbed-model-singular variable.
- stub_unreached_but_imported: module imports an ORM/framework but the
  function body uses only primitives.
- stub_irrelevant: pure-Python module, no ORM coupling at all.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


# ORM query/manager methods that hint at a stubbed-resource call
ORM_TERMINAL_METHODS = {
    # Django QuerySet / Manager
    "filter", "get", "all", "exclude", "create", "first", "last", "exists",
    "count", "order_by", "get_or_create", "update_or_create", "values",
    "values_list", "annotate", "select_related", "prefetch_related",
    "distinct", "aggregate", "earliest", "latest", "in_bulk", "iterator",
    "raw", "bulk_create", "bulk_update",
    # SQLAlchemy
    "scalar", "scalars", "execute", "join", "where", "select_from",
}

# Module prefixes treated as "framework" imports (function lives in an ORM/web
# stack module even if its own body uses only primitives).
FRAMEWORK_PREFIXES = (
    "django", "rest_framework", "taggit", "sqlalchemy", "flask",
    "starlette", "fastapi", "pydantic", "tortoise", "peewee",
)


def has_framework_imports(tree: ast.AST, project_packages: set[str]) -> bool:
    """True if the module imports an ORM/framework, OR a known project package."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            head = mod.split(".")[0]
            if head in project_packages:
                return True
            if mod.startswith(FRAMEWORK_PREFIXES):
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                head = alias.name.split(".")[0]
                if head in project_packages:
                    return True
                if alias.name.startswith(FRAMEWORK_PREFIXES):
                    return True
    return False


def find_orm_call_sites(node: ast.AST, stubbed_models: set[str]) -> list[dict]:
    """Collect `<Model>.objects.X` and `<Model>.query.X` patterns inside `node`."""
    sites = []
    for sub in ast.walk(node):
        # <Name>.objects / <Name>.query
        if isinstance(sub, ast.Attribute) and sub.attr in {"objects", "query"}:
            if isinstance(sub.value, ast.Name) and sub.value.id in stubbed_models:
                sites.append({
                    "kind": "manager_access",
                    "expr": f"{sub.value.id}.{sub.attr}",
                    "line": sub.lineno,
                })
        # Method call where the root is <Model>.objects or <Model>.query
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            attr = sub.func.attr
            if attr in ORM_TERMINAL_METHODS:
                # Walk back to find the root Name
                root = sub.func.value
                while isinstance(root, ast.Call) and isinstance(root.func, ast.Attribute):
                    root = root.func.value
                if isinstance(root, ast.Attribute) and root.attr in {"objects", "query"}:
                    if isinstance(root.value, ast.Name) and root.value.id in stubbed_models:
                        sites.append({
                            "kind": "orm_query",
                            "expr": f"{root.value.id}.{root.attr}.{attr}",
                            "line": sub.lineno,
                        })
        # related-manager pattern: <X>.<y>_set.<orm_method>(...)
        if isinstance(sub, ast.Attribute) and sub.attr.endswith("_set"):
            sites.append({
                "kind": "related_manager",
                "expr": ast.unparse(sub) if hasattr(ast, "unparse") else sub.attr,
                "line": sub.lineno,
            })
        # SQLAlchemy: session.query(<Model>) / select(<Model>)
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr == "query" and sub.args:
                arg = sub.args[0]
                if isinstance(arg, ast.Name) and arg.id in stubbed_models:
                    sites.append({
                        "kind": "sa_query",
                        "expr": f"session.query({arg.id})",
                        "line": sub.lineno,
                    })
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "select":
            if sub.args:
                arg = sub.args[0]
                if isinstance(arg, ast.Name) and arg.id in stubbed_models:
                    sites.append({
                        "kind": "sa_select",
                        "expr": f"select({arg.id})",
                        "line": sub.lineno,
                    })
    return sites


def function_params(fn: ast.AST) -> list[str]:
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    args = fn.args
    return [a.arg for a in args.args] + [a.arg for a in (args.kwonlyargs or [])]


def function_param_annotations(fn: ast.AST) -> list[str]:
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    out = []
    for a in (fn.args.args or []) + (fn.args.kwonlyargs or []):
        if a.annotation:
            try:
                out.append(ast.unparse(a.annotation))
            except Exception:
                pass
    return out


def find_function_node(
    tree: ast.AST,
    target_name: str,
    target_class: str | None,
    target_line: int,
) -> ast.AST | None:
    """Locate the FunctionDef matching name + (optional) class + line."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and (target_class == node.name or target_class is None):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == target_name:
                    if abs(child.lineno - target_line) <= 5:
                        return child
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_name and target_class is None:
            if abs(node.lineno - target_line) <= 5:
                return node
    return None


def classify_function(
    fn_node: ast.AST,
    module_has_framework: bool,
    stubbed_models: set[str],
    instance_attrs: set[str],
    plural_hints: dict[str, str],
) -> dict:
    """Bucket a function. Returns dict with bucket + evidence + raw hit lists."""
    orm_sites = find_orm_call_sites(fn_node, stubbed_models)

    params = function_params(fn_node)
    annotations = function_param_annotations(fn_node)
    stubbed_param_hits: list[str] = []
    qs_param_hits: list[str] = []
    loopvar_hits: list[str] = []
    subscript_hits: list[str] = []
    stub_attr_hits: list[str] = []

    stubbed_singulars = {m.lower() for m in stubbed_models}

    # Parameter NAME checks
    for p in params:
        if p.lower() in stubbed_singulars:
            stubbed_param_hits.append(f"param '{p}' matches stubbed model")
        elif p in plural_hints and plural_hints[p]:
            qs_param_hits.append(f"param '{p}' hints at QuerySet[{plural_hints[p]}]")

    # Parameter ANNOTATION checks
    for ann in annotations:
        for m in stubbed_models:
            if re.search(rf"\b{m}\b", ann):
                stubbed_param_hits.append(f"annotation {ann!r} mentions {m}")

    iterated_params: dict[str, str] = {}
    for sub in ast.walk(fn_node):
        # for X in <param-or-plural>:
        if isinstance(sub, ast.For) and isinstance(sub.iter, ast.Name):
            iter_name = sub.iter.id
            if iter_name in params or iter_name in plural_hints:
                if isinstance(sub.target, ast.Name):
                    iterated_params[sub.target.id] = iter_name
                    loopvar_hits.append(f"for {sub.target.id} in {iter_name} (line {sub.lineno})")

        # <param>.<qs_method>(...)
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if isinstance(sub.func.value, ast.Name) and sub.func.value.id in params:
                if sub.func.attr in ORM_TERMINAL_METHODS:
                    qs_param_hits.append(f"{sub.func.value.id}.{sub.func.attr}() (line {sub.lineno})")

        # <var>.<attr> where var is a stubbed-model singular name
        if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
            base = sub.value.id
            if base in stubbed_singulars:
                stub_attr_hits.append(f"{base}.{sub.attr} (line {sub.lineno})")

        # attrs["<stubbed_model_lower>"] (DRF / dict pattern)
        if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name):
            if sub.value.id in params:
                key_node = sub.slice if not isinstance(sub.slice, ast.Index) else sub.slice.value
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    if key_node.value in stubbed_singulars:
                        subscript_hits.append(f"{sub.value.id}[{key_node.value!r}] (line {sub.lineno})")

    is_stub_required = bool(
        orm_sites or stubbed_param_hits or qs_param_hits or stub_attr_hits
        or subscript_hits or loopvar_hits
    )

    if is_stub_required:
        bucket = "stub_required"
        parts = []
        if orm_sites:
            parts.append(f"{len(orm_sites)} ORM call site(s)")
        if stubbed_param_hits:
            parts.append(stubbed_param_hits[0])
        if qs_param_hits:
            parts.append(qs_param_hits[0])
        if subscript_hits:
            parts.append(f"subscript: {subscript_hits[0]}")
        if stub_attr_hits:
            parts.append(f"stub-attr: {stub_attr_hits[0]}")
        if loopvar_hits and not parts:
            parts.append(f"loopvar: {loopvar_hits[0]}")
        evidence = "; ".join(parts)
    elif module_has_framework:
        bucket = "stub_unreached_but_imported"
        evidence = "module imports framework but function body uses only primitives"
    else:
        bucket = "stub_irrelevant"
        evidence = "no framework imports in module"

    return {
        "bucket": bucket,
        "evidence": evidence,
        "orm_sites": orm_sites,
        "stubbed_param_hits": stubbed_param_hits,
        "qs_param_hits": qs_param_hits,
        "stub_attr_hits": stub_attr_hits,
        "subscript_hits": subscript_hits,
        "loopvar_hits": loopvar_hits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--contract-files", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd(),
                        help="Source root for resolving file paths (default: cwd)")
    parser.add_argument("--output", type=Path,
                        default=Path(".claude/artifacts/crosshair-stub-effectiveness/stub-effectiveness.json"))
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text())
    contracts = json.loads(args.contract_files.read_text())

    stubbed_models = set(inventory["stubbed_models"])
    factory_models = set(inventory.get("factory_models", []))
    instance_attrs = set(inventory.get("instance_attrs", []))
    plural_hints = {k: v for k, v in inventory.get("plural_hints", {}).items()}

    # Derive project_packages from the contract-files.json (e.g. "api/...", "core/...", "babybuddy/...")
    project_packages = set()
    for entry in contracts["files"]:
        head = Path(entry["path"]).parts[0]
        project_packages.add(head)

    per_file: list[dict] = []
    bucket_counts = {"stub_required": 0, "stub_unreached_but_imported": 0, "stub_irrelevant": 0}
    total_functions = 0
    files_with_orm_calls = 0

    for entry in contracts["files"]:
        path = entry["path"]
        full = args.project_root / path
        try:
            src = full.read_text()
        except OSError as e:
            print(f"WARN: cannot read {full}: {e}", file=sys.stderr)
            continue
        try:
            tree = ast.parse(src, filename=str(full))
        except SyntaxError as e:
            print(f"WARN: syntax error in {full}: {e}", file=sys.stderr)
            continue

        module_has_framework = has_framework_imports(tree, project_packages)
        file_orm_sites: list[dict] = []
        functions_out: list[dict] = []

        for fn in entry.get("functions", []):
            name = fn["name"]
            klass = fn.get("class_name")
            line = fn.get("line", 0)
            fn_type = fn.get("type", "function")

            if fn_type == "class":
                continue

            node = find_function_node(tree, name, klass, line)
            if node is None:
                functions_out.append({
                    "name": name, "class_name": klass, "line": line,
                    "bucket": "unknown", "evidence": "could not locate AST node",
                    "orm_sites": [],
                })
                continue

            cls = classify_function(node, module_has_framework, stubbed_models, instance_attrs, plural_hints)
            bucket_counts[cls["bucket"]] += 1
            total_functions += 1
            file_orm_sites.extend(cls["orm_sites"])

            functions_out.append({
                "name": name,
                "class_name": klass,
                "line": line,
                "bucket": cls["bucket"],
                "evidence": cls["evidence"],
                "orm_sites": cls["orm_sites"],
                "stubbed_param_hits": cls["stubbed_param_hits"],
                "qs_param_hits": cls["qs_param_hits"],
                "stub_attr_hits": cls["stub_attr_hits"],
                "subscript_hits": cls["subscript_hits"],
                "loopvar_hits": cls["loopvar_hits"],
            })

        if file_orm_sites:
            files_with_orm_calls += 1

        per_file.append({
            "file": path,
            "module_has_framework": module_has_framework,
            "orm_call_sites": sorted({
                s["expr"] for s in file_orm_sites
                if s["kind"] in {"orm_query", "manager_access", "sa_query", "sa_select"}
            }),
            "orm_call_site_count": len(file_orm_sites),
            "functions": functions_out,
        })

    files_with_any_stub_required = sum(
        1 for f in per_file if any(fn["bucket"] == "stub_required" for fn in f["functions"])
    )
    files_completely_django_free = sum(
        1 for f in per_file if f["functions"] and all(fn["bucket"] == "stub_irrelevant" for fn in f["functions"])
    )

    summary = {
        "files_with_contracts": len(per_file),
        "files_with_orm_calls": files_with_orm_calls,
        "files_with_any_stub_required_fn": files_with_any_stub_required,
        "files_completely_framework_free": files_completely_django_free,
        "functions_with_contracts": total_functions,
        "functions_stub_required": bucket_counts["stub_required"],
        "functions_stub_unreached_but_imported": bucket_counts["stub_unreached_but_imported"],
        "functions_stub_irrelevant": bucket_counts["stub_irrelevant"],
        "stub_required_pct": round(bucket_counts["stub_required"] / total_functions * 100, 1) if total_functions else 0,
        "stubbed_models_total": len(stubbed_models),
        "stubbed_models_with_factory": len(factory_models),
    }

    # Stub for Metric B — attribute_findings.py fills this in
    findings_attribution: list[dict] = []
    if args.output.exists():
        try:
            prior = json.loads(args.output.read_text())
            findings_attribution = prior.get("findings_attribution", [])
        except Exception:
            pass

    out_json = {
        "summary": summary,
        "stubbed_models": sorted(stubbed_models),
        "factory_models": sorted(factory_models),
        "instance_attrs": sorted(instance_attrs),
        "per_file": per_file,
        "findings_attribution": findings_attribution,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out_json, indent=2))
    print(f"Wrote {args.output}")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
