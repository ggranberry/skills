#!/usr/bin/env python3
"""Merge a hand-curated list of CrossHair findings into stub-effectiveness.json
so the report can compute Metric B (stubbed-model vs primitive attribution).

The findings file is a JSON list, schema documented in
references/findings-schema.md. Each entry needs at least:
  - id (int or str)
  - file (path)
  - function (str)
  - category ("real_bug" | "contract_bug" | "precondition_gap" | "stub_gap")
  - input_source ("primitive" | "stubbed_model" | "stub_gap" | "contract_only")

Inline mode: pass `--inline '[{...}]'` instead of `--findings <path>`.

Usage:
    attribute_findings.py --findings findings.json --effectiveness stub-effectiveness.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED = {"id", "file", "function", "category", "input_source"}
ALLOWED_CATEGORIES = {"real_bug", "contract_bug", "precondition_gap", "stub_gap"}
ALLOWED_INPUT_SOURCES = {"primitive", "stubbed_model", "stub_gap", "contract_only"}


def validate_findings(items: list[dict]) -> list[str]:
    errors: list[str] = []
    for i, f in enumerate(items):
        missing = REQUIRED - set(f.keys())
        if missing:
            errors.append(f"item {i}: missing fields {missing}")
        if f.get("category") not in ALLOWED_CATEGORIES:
            errors.append(f"item {i}: category {f.get('category')!r} not in {sorted(ALLOWED_CATEGORIES)}")
        if f.get("input_source") not in ALLOWED_INPUT_SOURCES:
            errors.append(f"item {i}: input_source {f.get('input_source')!r} not in {sorted(ALLOWED_INPUT_SOURCES)}")
    return errors


def compute_metrics(findings: list[dict]) -> dict:
    real_bugs = [f for f in findings if f["category"] == "real_bug"]
    stubbed_real = sum(1 for f in real_bugs if f["input_source"] == "stubbed_model")
    primitive_real = sum(1 for f in real_bugs if f["input_source"] == "primitive")

    attributable = [f for f in findings if f["input_source"] in {"primitive", "stubbed_model"}]
    stubbed_all = sum(1 for f in attributable if f["input_source"] == "stubbed_model")

    return {
        "real_bugs_count": len(real_bugs),
        "real_bugs_from_stubbed_models": stubbed_real,
        "real_bugs_from_primitives": primitive_real,
        "real_bugs_smart_stub_attribution_ratio": round(stubbed_real / len(real_bugs), 3) if real_bugs else 0.0,
        "attributable_findings_count": len(attributable),
        "all_findings_smart_stub_attribution_ratio": round(stubbed_all / len(attributable), 3) if attributable else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--findings", type=Path, help="Path to findings JSON file")
    src.add_argument("--inline", type=str, help="Inline JSON list of findings")
    parser.add_argument("--effectiveness", type=Path, required=True,
                        help="Path to stub-effectiveness.json to update")
    args = parser.parse_args()

    if args.findings:
        findings = json.loads(args.findings.read_text())
    else:
        findings = json.loads(args.inline)

    if not isinstance(findings, list):
        print(f"ERROR: findings must be a JSON list, got {type(findings).__name__}", file=sys.stderr)
        sys.exit(2)

    errors = validate_findings(findings)
    if errors:
        for e in errors:
            print(f"VALIDATION: {e}", file=sys.stderr)
        sys.exit(2)

    eff = json.loads(args.effectiveness.read_text())
    eff["findings_attribution"] = findings
    eff["summary"].update(compute_metrics(findings))

    args.effectiveness.write_text(json.dumps(eff, indent=2))
    print(f"Updated {args.effectiveness}")
    for k, v in compute_metrics(findings).items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
