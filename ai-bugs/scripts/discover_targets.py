#!/usr/bin/env python3
"""Discover Python source files for AI bug analysis.

Run from the project root:
    python3 /path/to/discover_targets.py [--include-dirs src app] [--exclude-dirs vendor]

Outputs file-targets.json to .claude/artifacts/ai-bugs/.
"""

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_EXCLUDE_DIRS = {
    "test", "tests", "testing",
    "migrations", "migrate",
    "venv", ".venv", "env", ".env",
    "node_modules",
    "__pycache__",
    "site-packages",
    ".claude",
    ".git",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist", "build", "egg-info",
}

DEFAULT_EXCLUDE_FILES = {
    "setup.py",
    "conftest.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
}

ARTIFACTS_DIR = Path(".claude/artifacts/ai-bugs")
FINDINGS_DIR = ARTIFACTS_DIR / "findings"


def make_slug(filepath: str) -> str:
    """Convert a file path to a slug for artifact filenames.

    core/views.py -> core-views.py
    """
    return filepath.replace(os.sep, "-").replace("/", "-")


def count_lines(filepath: str) -> int:
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def should_exclude_dir(dirname: str, exclude_dirs: set) -> bool:
    lower = dirname.lower()
    for pattern in exclude_dirs:
        if lower == pattern.lower() or lower.startswith(pattern.lower() + "."):
            return True
    return False


def discover_files(
    root: str = ".",
    include_dirs: list[str] | None = None,
    exclude_dirs: set[str] | None = None,
    skip_existing: bool = False,
) -> list[dict]:
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS

    root_path = Path(root).resolve()
    files = []

    if include_dirs:
        walk_roots = []
        for d in include_dirs:
            p = root_path / d
            if p.is_dir():
                walk_roots.append(p)
            else:
                print(f"Warning: --include-dir '{d}' not found, skipping", file=sys.stderr)
        if not walk_roots:
            print("Error: none of the --include-dirs exist", file=sys.stderr)
            sys.exit(1)
    else:
        walk_roots = [root_path]

    for walk_root in walk_roots:
        for dirpath, dirnames, filenames in os.walk(walk_root):
            # Prune excluded directories in-place
            dirnames[:] = [
                d for d in dirnames
                if not should_exclude_dir(d, exclude_dirs)
            ]

            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                if fname in DEFAULT_EXCLUDE_FILES:
                    continue
                if fname.startswith("test_") or fname.endswith("_test.py"):
                    continue

                full_path = Path(dirpath) / fname
                rel_path = str(full_path.relative_to(root_path))
                slug = make_slug(rel_path)

                if skip_existing:
                    raw_file = FINDINGS_DIR / f"raw-{slug}.json"
                    if raw_file.exists():
                        continue

                line_count = count_lines(str(full_path))
                if line_count == 0:
                    continue

                files.append({
                    "file": rel_path,
                    "slug": slug,
                    "lines": line_count,
                })

    # Sort by line count descending (meatiest files first)
    files.sort(key=lambda f: f["lines"], reverse=True)
    return files


def main():
    parser = argparse.ArgumentParser(description="Discover Python files for AI bug analysis")
    parser.add_argument("--root", default=".", help="Project root directory (default: .)")
    parser.add_argument("--include-dirs", nargs="+", help="Only scan these directories")
    parser.add_argument("--exclude-dirs", nargs="+", help="Additional directories to exclude")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip files with existing raw findings")
    parser.add_argument("--output", default=str(ARTIFACTS_DIR / "file-targets.json"),
                        help="Output file path")
    args = parser.parse_args()

    exclude = set(DEFAULT_EXCLUDE_DIRS)
    if args.exclude_dirs:
        exclude.update(args.exclude_dirs)

    files = discover_files(
        root=args.root,
        include_dirs=args.include_dirs,
        exclude_dirs=exclude,
        skip_existing=args.skip_existing,
    )

    result = {
        "total_files": len(files),
        "total_lines": sum(f["lines"] for f in files),
        "files": files,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Discovered {len(files)} Python files ({result['total_lines']} lines total)", file=sys.stderr)
    if files:
        print(f"Largest: {files[0]['file']} ({files[0]['lines']} lines)", file=sys.stderr)
        print(f"Smallest: {files[-1]['file']} ({files[-1]['lines']} lines)", file=sys.stderr)
    print(f"Written to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
