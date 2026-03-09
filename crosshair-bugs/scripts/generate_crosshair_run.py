#!/usr/bin/env python3
"""
Generate .claude/artifacts/crosshair-bugs/crosshair/run_crosshair.sh

Reads planner-assignments.json, finds files whose plan has been applied,
and writes one shell command per file. Output filenames use the full path
slug (e.g. core/views.py -> crosshair-output-core-views.py.txt) to avoid
basename collisions.

Usage (run from the project root):
    python3 /path/to/generate_crosshair_run.py <venv_path>

Where <venv_path> is the Python venv that has both crosshair and the
project's dependencies installed, e.g. /home/user/myproject/venv
"""
import json
import os
import sys

ARTIFACTS = ".claude/artifacts/crosshair-bugs"
PLANS_DIR = f"{ARTIFACTS}/plans"
CROSSHAIR_DIR = f"{ARTIFACTS}/crosshair"


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: generate_crosshair_run.py <venv_path>")

    venv = sys.argv[1].rstrip("/")
    crosshair = f"{venv}/bin/crosshair"
    if not os.path.exists(crosshair):
        sys.exit(f"ERROR: {crosshair} not found. Check the venv path.")

    # Load assignments
    with open(f"{ARTIFACTS}/planner-assignments.json") as f:
        data = json.load(f)

    # Collect unique files whose plan has ## Applied
    file_to_output = {}
    for a in data["assignments"]:
        fp = a["file"]
        if fp not in file_to_output:
            file_to_output[fp] = a["output_file"]

    applied = []
    for fp, output_file in file_to_output.items():
        plan_path = f"{PLANS_DIR}/{output_file}"
        if os.path.exists(plan_path):
            with open(plan_path) as f:
                if "## Applied" in f.read():
                    applied.append(fp)

    if not applied:
        sys.exit("ERROR: No plan files with '## Applied' found. Run phases 6-7 first.")

    # Detect Django
    with open(f"{ARTIFACTS}/orm-detection.json") as f:
        orm = json.load(f).get("orm", "")
    django_flag = "--extra_plugin crosshair_django_setup.py" if orm == "django" else ""

    # Ensure output directory exists
    os.makedirs(CROSSHAIR_DIR, exist_ok=True)

    # Write script — one command per file, skipping existing outputs
    skipped = []
    to_run = []

    lines = ["#!/bin/bash", ""]
    for fp in sorted(applied):
        slug = fp.replace("/", "-")
        outfile = f"{CROSSHAIR_DIR}/crosshair-output-{slug}.txt"
        if os.path.exists(outfile):
            skipped.append(fp)
            continue
        parts = [crosshair, "check", fp]
        if django_flag:
            parts.append(django_flag)
        parts += ["--per_condition_timeout", "30", "--analysis_kind", "PEP316"]
        cmd = " ".join(parts) + f" > {outfile} 2>&1"
        lines.append(cmd)
        to_run.append((fp, outfile))

    script_path = f"{CROSSHAIR_DIR}/run_crosshair.sh"
    with open(script_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(script_path, 0o755)

    print(f"Wrote {script_path}")
    print(f"  {len(to_run)} files to run, {len(skipped)} skipped (output already exists)")
    if skipped:
        print()
        print("Skipped (delete output file to re-run):")
        for fp in skipped:
            print(f"  {fp}")
    if to_run:
        print()
        print("To run (spawn one run_in_background=true Bash call per line):")
        for fp, outfile in to_run:
            print(f"  {fp}")


if __name__ == "__main__":
    main()
