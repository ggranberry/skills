#!/usr/bin/env python3
"""Render stub-effectiveness.json into a human-readable markdown report.

Usage:
    generate_report.py --effectiveness stub-effectiveness.json --output report.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(eff: dict) -> str:
    s = eff["summary"]
    per_file = eff["per_file"]
    findings = eff.get("findings_attribution", [])

    lines: list[str] = []
    lines.append("# CrossHair Stub Effectiveness Report")
    lines.append("")
    lines.append("Companion to `stub-effectiveness.json`.")
    lines.append("")

    # Headline verdict
    stub_pct = s.get("stub_required_pct", 0)
    has_findings = bool(findings)
    if has_findings:
        ratio = s.get("real_bugs_smart_stub_attribution_ratio", 0)
        bug_pct = int(ratio * 100)
        lines.append("## Verdict")
        lines.append("")
        lines.append(
            f"The smart ORM stubs are the only path to symbolic execution for "
            f"**{s['functions_stub_required']} of {s['functions_with_contracts']} contracted functions "
            f"({stub_pct}%)**, but they receive credit for triggering "
            f"**{s.get('real_bugs_from_stubbed_models', 0)} of {s.get('real_bugs_count', 0)} real bugs "
            f"({bug_pct}%)**. The rest were triggered by primitives "
            f"CrossHair generates natively."
        )
    else:
        lines.append("## Verdict")
        lines.append("")
        lines.append(
            f"The smart ORM stubs gate symbolic execution for "
            f"**{s['functions_stub_required']} of {s['functions_with_contracts']} contracted functions "
            f"({stub_pct}%)**. Bug-attribution metric not computed — run "
            f"`attribute_findings.py` with a findings list to enable Metric B."
        )
    lines.append("")

    # Metric A
    lines.append("## Metric A — stub-reach")
    lines.append("")
    lines.append("| Bucket | Count | % | Meaning |")
    lines.append("|---|---|---|---|")
    total = s["functions_with_contracts"]
    for bucket, label in [
        ("functions_stub_required", "stub_required"),
        ("functions_stub_unreached_but_imported", "stub_unreached_but_imported"),
        ("functions_stub_irrelevant", "stub_irrelevant"),
    ]:
        n = s[bucket]
        pct = round(n / total * 100, 1) if total else 0
        meaning = {
            "stub_required": "Body needs the smart ORM stubs to run (touches manager, takes stubbed-model param, iterates QuerySet param, or reads attrs[<model>]).",
            "stub_unreached_but_imported": "Module imports the framework but the function body uses only primitives. Needs only the import-time scaffold.",
            "stub_irrelevant": "Pure-Python module, no framework imports at all.",
        }[label]
        lines.append(f"| `{label}` | {n} | {pct}% | {meaning} |")
    lines.append("")
    lines.append(
        f"- Files with ≥1 stub_required function: **{s['files_with_any_stub_required_fn']} / {s['files_with_contracts']}**."
    )
    lines.append(
        f"- Files completely framework-free: {s['files_completely_framework_free']}."
    )
    lines.append(
        f"- Stubbed models: {s['stubbed_models_total']} total, {s['stubbed_models_with_factory']} with full SimpleNamespace factories."
    )
    lines.append("")

    # Metric B
    if has_findings:
        lines.append("## Metric B — finding attribution")
        lines.append("")
        lines.append("| ID | File | Function | Category | Input source |")
        lines.append("|---|---|---|---|---|")
        for f in sorted(findings, key=lambda x: (x["category"], x["id"])):
            lines.append(
                f"| {f['id']} | `{f['file']}` | {f.get('function', '?')} | "
                f"{f['category']} | {f['input_source']} |"
            )
        lines.append("")
        ratio = s.get("real_bugs_smart_stub_attribution_ratio", 0)
        lines.append(
            f"- Real bugs from stubbed models: "
            f"**{s.get('real_bugs_from_stubbed_models', 0)} / {s.get('real_bugs_count', 0)}** = {int(ratio*100)}%"
        )
        all_ratio = s.get("all_findings_smart_stub_attribution_ratio", 0)
        lines.append(
            f"- Across all attribution-eligible findings: "
            f"**{int(all_ratio * 100)}%** stubbed-model-attributable"
        )
        lines.append("")

    # Per-file ORM call sites
    orm_files = [f for f in per_file if f["orm_call_site_count"] > 0]
    if orm_files:
        lines.append("## Per-file ORM call-site inventory")
        lines.append("")
        lines.append("| File | Call-site count | Distinct expressions |")
        lines.append("|---|---|---|")
        for f in sorted(orm_files, key=lambda x: -x["orm_call_site_count"]):
            exprs = ", ".join(f["orm_call_sites"][:6])
            if len(f["orm_call_sites"]) > 6:
                exprs += f", … (+{len(f['orm_call_sites']) - 6} more)"
            lines.append(f"| `{f['file']}` | {f['orm_call_site_count']} | {exprs} |")
        lines.append("")

    # Per-bucket file listing
    lines.append("## Per-file bucket distribution")
    lines.append("")
    lines.append("| File | stub_required | stub_unreached | stub_irrelevant |")
    lines.append("|---|---|---|---|")
    for f in per_file:
        buckets = {"stub_required": 0, "stub_unreached_but_imported": 0, "stub_irrelevant": 0}
        for fn in f["functions"]:
            if fn["bucket"] in buckets:
                buckets[fn["bucket"]] += 1
        lines.append(
            f"| `{f['file']}` | {buckets['stub_required']} | "
            f"{buckets['stub_unreached_but_imported']} | {buckets['stub_irrelevant']} |"
        )
    lines.append("")

    # Footer
    lines.append("## Caveats")
    lines.append("")
    lines.append("- The analyzer is static: it does not run CrossHair. A function classified `stub_required` *can* still complete symbolic execution if the stubs are present; one classified `stub_unreached_but_imported` *cannot* run without at least the import-time scaffold.")
    lines.append("- `module_has_framework` only inspects module-level imports. Functions that import lazily inside their body may be miscategorized as `stub_irrelevant`.")
    lines.append("- Metric B is hand-curated. There is no automated way to introspect CrossHair's symbolic value lineage; the attribution file records the user's classification.")
    lines.append("- For ORMs other than Django/SQLAlchemy, augment `ORM_TERMINAL_METHODS` in `analyze_stub_effectiveness.py` or supply additional patterns via the inventory's `extra_orm_patterns` field.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effectiveness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    eff = json.loads(args.effectiveness.read_text())
    md = render(eff)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md)
    print(f"Wrote {args.output} ({len(md.splitlines())} lines)")


if __name__ == "__main__":
    main()
