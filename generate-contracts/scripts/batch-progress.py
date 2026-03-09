#!/usr/bin/env python3
"""Report batched progress for contract planning and return the next batch.

Reads planner-assignments.json, checks which contract-plan-*.md files
already exist in the artifacts directory, and outputs the next N
unplanned assignments as JSON to stdout.  Progress summary goes to
stderr so the orchestrator can display it without parsing JSON.

Usage:
    python batch-progress.py [--batch-size N] [--assignments PATH] [--artifacts-dir PATH]

Options:
    --batch-size N       Number of assignments per batch (default: 10)
    --assignments PATH   Path to planner-assignments.json
                         (default: .claude/artifacts/crosshair-bugs/planner-assignments.json)
    --artifacts-dir PATH Directory containing contract-plan-*.md files
                         (default: .claude/artifacts/crosshair-bugs/)
"""

import argparse
import json
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Report batch progress for contract planning")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Assignments per batch (default: 10)")
    parser.add_argument("--assignments",
                        default=".claude/artifacts/crosshair-bugs/planner-assignments.json",
                        help="Path to planner-assignments.json")
    parser.add_argument("--artifacts-dir",
                        default=".claude/artifacts/crosshair-bugs/",
                        help="Directory containing contract-plan-*.md files")
    args = parser.parse_args()

    if not os.path.exists(args.assignments):
        print(f"Error: {args.assignments} not found. Run Phase 1.5 (Chunk) first.", file=sys.stderr)
        sys.exit(1)

    with open(args.assignments) as f:
        data = json.load(f)

    assignments = data.get("assignments", [])
    total = len(assignments)

    # Find which assignments already have plan files on disk.
    remaining = []
    for assignment in assignments:
        plan_path = os.path.join(args.artifacts_dir, assignment["output_file"])
        if not os.path.exists(plan_path):
            remaining.append(assignment)

    planned = total - len(remaining)
    batch = remaining[: args.batch_size]

    print(
        f"Progress: {planned}/{total} planned, {len(remaining)} remaining. "
        f"Next batch: {len(batch)}",
        file=sys.stderr,
    )

    json.dump(batch, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
