#!/usr/bin/env python3
"""report — finalize a paper audit into result.json.

Usage:
    python3 report.py --case /input/case.json --work /app/work [--findings FILE]

If `--findings` (or work/findings_model.json) exists, its entries are merged into
audit_report.json with `method: model-judgment` and the counts are recomputed.
The model-supplied file is expected to follow the same schema as the
deterministic findings; entries without a location/evidence are dropped and
reported, never silently accepted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def load(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save(path: Path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def normalize_findings(raw):
    out = []
    dropped = []
    for i, f in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(f, dict):
            dropped.append({"index": i, "reason": "not an object"})
            continue
        evidence = f.get("evidence")
        location = f.get("location")
        if not evidence or not location:
            dropped.append({"index": i, "reason": "missing evidence or location", "title": f.get("title")})
            continue
        item = {
            "id": f.get("id") or f"model-{i + 1:03d}",
            "facet": f.get("facet") or "argument",
            "severity": f.get("severity") or "low",
            "status": f.get("status") or "待复核",
            "title": f.get("title") or "",
            "evidence": evidence,
            "location": location,
            "recommendation": f.get("recommendation") or "",
            "confidence": f.get("confidence") or "medium",
            "method": "model-judgment",
        }
        out.append(item)
    return out, dropped


def counts(findings):
    by_status = {}
    by_severity = {}
    for f in findings:
        by_status[f["status"]] = by_status.get(f["status"], 0) + 1
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    if by_severity.get("high"):
        status = "问题"
    elif by_severity.get("medium") or by_status.get("待复核"):
        status = "待复核"
    elif findings:
        status = "通过"
    else:
        status = "未检查"
    return {"by_status": by_status, "by_severity": by_severity, "total": len(findings)}, status


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--findings", default=None)
    args = ap.parse_args(argv)

    case = load(Path(args.case))
    work = Path(args.work)
    report = load(work / "audit_report.json")

    findings_path = Path(args.findings) if args.findings else (work / "findings_model.json")
    dropped = []
    added = 0
    if findings_path.exists():
        raw = load(findings_path)
        raw = raw.get("findings", raw) if isinstance(raw, dict) else raw
        merged, dropped = normalize_findings(raw)
        existing = {f["id"] for f in report.get("findings", [])}
        for f in merged:
            if f["id"] in existing:
                f["id"] = f["id"] + "-m"
            report.setdefault("findings", []).append(f)
            added += 1

    report["findings"].sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["facet"]))
    counts_, status = counts(report["findings"])
    report["counts"] = counts_
    report["status"] = status
    report["model_additions"] = {"added": added, "dropped": dropped}
    save(work / "audit_report.json", report)

    case_id = case.get("case_id") or case.get("id") or Path(args.case).stem
    result = {
        "case_id": case_id,
        "task": "paper-quality-audit",
        "status": "complete",
        "audit_status": status,
        "deliverables": {
            "paper_structure": "paper.json",
            "full_text": "full_text.txt",
            "audit_report": "audit_report.json",
        },
        "counts": counts_,
        "checked_facets": report.get("checked_facets"),
        "unchecked_facets": report.get("unchecked_facets"),
        "model_additions": report["model_additions"],
        "findings": report["findings"],
        "uncertainty": report.get("uncertainty", []),
        "sources": [report.get("paper", {}).get("source")],
        "changes": [
            {"step": "extract", "detail": json.dumps(report.get("paper", {}).get("stats", {}), ensure_ascii=False)},
            {"step": "audit", "detail": f"{counts_['total']} findings, status={status}"},
        ],
    }
    save(work / "result.json", result)
    print(f"report: {counts_['total']} findings, audit_status={status}, model_added={added}, dropped={len(dropped)}")
    return result


if __name__ == "__main__":
    main()
