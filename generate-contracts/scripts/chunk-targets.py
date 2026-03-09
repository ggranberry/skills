#!/usr/bin/env python3
"""Split contract-targets.json into per-file planner assignments.

Reads the Phase 1 manifest and produces planner-assignments.json,
where each assignment scopes a single planner agent to one file
(or one chunk of a large file).

Usage:
    python chunk-targets.py [--max-functions N] [--targets PATH] [--output PATH]

Options:
    --max-functions N   Maximum functions per planner assignment (default: 30)
    --targets PATH      Path to contract-targets.json
                        (default: .claude/artifacts/crosshair-bugs/contract-targets.json)
    --output PATH       Path to write planner-assignments.json
                        (default: .claude/artifacts/crosshair-bugs/planner-assignments.json)
"""

import argparse
import json
import math
import os
import sys


def chunk_list(items: list, max_size: int) -> list[list]:
    """Split a list into chunks of at most max_size."""
    if len(items) <= max_size:
        return [items]
    n_chunks = math.ceil(len(items) / max_size)
    chunk_size = math.ceil(len(items) / n_chunks)
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Split contract targets into planner assignments")
    parser.add_argument("--max-functions", type=int, default=30,
                        help="Max functions per planner (default: 30)")
    parser.add_argument("--targets", default=".claude/artifacts/crosshair-bugs/contract-targets.json",
                        help="Path to contract-targets.json")
    parser.add_argument("--output", default=".claude/artifacts/crosshair-bugs/planner-assignments.json",
                        help="Path to write planner-assignments.json")
    args = parser.parse_args()

    if not os.path.exists(args.targets):
        print(f"Error: {args.targets} not found. Run Phase 1 (Explore) first.", file=sys.stderr)
        sys.exit(1)

    with open(args.targets) as f:
        targets = json.load(f)

    assignments = []
    for file_entry in targets.get("files", []):
        file_path = file_entry["path"]
        functions = file_entry.get("functions", [])
        func_names = [fn["name"] for fn in functions]
        basename = os.path.basename(file_path)

        if len(func_names) == 0:
            continue

        chunks = chunk_list(func_names, args.max_functions)
        for i, chunk in enumerate(chunks):
            assignment_id = basename if len(chunks) == 1 else f"{basename}-chunk{i + 1}"
            assignments.append({
                "id": assignment_id,
                "file": file_path,
                "functions": chunk,
                "function_count": len(chunk),
                "output_file": f"contract-plan-{assignment_id}.md",
            })

    result = {
        "max_functions_per_assignment": args.max_functions,
        "total_assignments": len(assignments),
        "total_functions": sum(a["function_count"] for a in assignments),
        "assignments": assignments,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Created {len(assignments)} planner assignments "
          f"({sum(a['function_count'] for a in assignments)} functions total)")
    for a in assignments:
        print(f"  {a['id']}: {a['file']} ({a['function_count']} functions)")


if __name__ == "__main__":
    main()
