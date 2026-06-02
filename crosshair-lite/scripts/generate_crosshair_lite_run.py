#!/usr/bin/env python3
"""Generate .claude/artifacts/crosshair-lite/crosshair/run_crosshair.sh

Reads contract-files.json (from find_contract_files.py) and writes one
shell command per file. No plugin flags — this is the stub-free variant.

Output filenames use the full path slug (e.g. core/views.py ->
crosshair-output-core-views.py.txt) to avoid basename collisions.

Usage (run from the project root):
    python3 /path/to/generate_crosshair_lite_run.py <venv_path>

Where <venv_path> is the Python venv that has both crosshair and the
project's dependencies installed, e.g. /home/user/myproject/venv
"""
import json
import os
import sys

ARTIFACTS = ".claude/artifacts/crosshair-lite"
CROSSHAIR_DIR = f"{ARTIFACTS}/crosshair"


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: generate_crosshair_lite_run.py <venv_path>")

    venv = sys.argv[1].rstrip("/")
    crosshair = f"{venv}/bin/crosshair"
    if not os.path.exists(crosshair):
        sys.exit(f"ERROR: {crosshair} not found. Check the venv path.")

    contract_files_path = f"{ARTIFACTS}/contract-files.json"
    if not os.path.exists(contract_files_path):
        sys.exit(f"ERROR: {contract_files_path} not found. Run find_contract_files.py first.")

    with open(contract_files_path) as f:
        data = json.load(f)

    files_to_run = [entry["path"] for entry in data["files"]]
    if not files_to_run:
        sys.exit("ERROR: No files with contracts found in contract-files.json.")

    os.makedirs(CROSSHAIR_DIR, exist_ok=True)

    skipped = []
    to_run = []

    lines = ["#!/bin/bash", ""]
    for fp in sorted(files_to_run):
        slug = fp.replace("/", "-")
        outfile = f"{CROSSHAIR_DIR}/crosshair-output-{slug}.txt"
        if os.path.exists(outfile):
            skipped.append(fp)
            continue
        parts = [crosshair, "check", fp]
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
