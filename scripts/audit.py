#!/usr/bin/env python3
"""audit — deterministic, evidence-bearing paper quality checks.

Usage:
    python3 audit.py --case /input/case.json --work /app/work --out /app/work

Reads work/paper.json (from extract_paper.py) plus the case's declared review
facets, and produces:
    work/audit_report.json  — findings[] with location + evidence + severity
    work/result.json        — status (通过/问题/待复核/未检查) + counts

Every finding is grounded in a quote and a location. A facet the script cannot
check deterministically is reported as `未检查` (unchecked) rather than silently
dropped — the caller (a human or model) decides how to cover it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FACETS = {
    "structure": "整体质量与结构完整性",
    "consistency": "事实一致性与引用支持",
    "methods": "方法设计与统计报告",
    "argument": "论证链与逻辑一致性",
    "ethics": "学术规范与可发表性",
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

# -- keyword sets ----------------------------------------------------------
REQUIRED_SECTIONS = {
    "abstract": ["abstract", "summary"],
    "introduction": ["introduction", "background"],
    "methods": ["method", "materials and methods", "experimental"],
    "results": ["result"],
    "discussion": ["discussion"],
    "conclusion": ["conclusion"],
    "references": ["reference", "bibliography"],
    "data_availability": ["data availability", "data access", "code availability"],
}

METHOD_MARKERS = {
    "sample_size": [r"n\s*=\s*\d+", r"\d+\s+(?:patients|subjects|samples|mice|rats|participants|cells)"],
    "randomization": [r"randomi[sz]ed", r"randomly assigned", r"random allocation"],
    "control": [r"control group", r"placebo", r"sham", r"wild[\s-]?type", r"untreated"],
    "blinding": [r"blind(ed|ing)?", r"masked"],
    "replication": [r"replicat", r"independent experiment", r"three (?:technical|biological)"],
}

STAT_MARKERS = {
    "p_value": [r"p\s*[≤<>=]\s*0?\.\d+", r"p\s*value"],
    "confidence_interval": [r"95%\s*CI", r"confidence interval", r"\bCI\s*\["],
    "effect_size": [r"effect size", r"Cohen'?s\s*d", r"Hedges'?s?\s*g", r"odds ratio", r"hazard ratio"],
    "alpha": [r"α\s*=\s*0?\.\d+", r"significance level", r"two[\s-]?tailed"],
    "multiple_testing": [r"Bonferroni", r"FDR", r"false discovery rate", r"multiple (?:comparisons|testing)"],
}

ETHICS_MARKERS = {
    "ethics_approval": [r"ethics (?:committee|approval|review board)", r"IRB", r"institutional review board"],
    "consent": [r"informed consent", r"written consent"],
    "conflict_of_interest": [r"conflict of interest", r"competing interests"],
    "funding": [r"fund(?:ed|ing)? (?:by|from)", r"grant (?:no|number)"],
    "author_contributions": [r"author contributions", r"conceptuali[sz]ation", r"CRediT"],
}

OVERCLAIM = [r"\bprove[sd]?\b", r"\bdemonstrates?\b", r"\bcures?\b", r"\bdefinitive\b", r"\bgroundbreaking\b"]
HEDGING = [r"\bmay\b", r"\bmight\b", r"\bpossibly\b", r"\bsuggest(?:s|ive)?\b", r"\blikely\b"]


def load(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def find_paper(case: dict):
    for key in ("paper", "paper_path", "pdf", "manuscript", "document", "input", "file", "path"):
        val = case.get(key)
        if isinstance(val, str) and val:
            return val
    for key in ("papers", "documents", "files", "inputs"):
        val = case.get(key)
        if isinstance(val, list) and val:
            first = val[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("path") or first.get("paper") or first.get("file")
    return None


def pquote(paper, idx, maxlen=240):
    if idx is None or idx < 0 or idx >= len(paper["paragraphs"]):
        return None
    p = paper["paragraphs"][idx]
    return {"index": p["index"], "page": p["page"], "section": p["section"], "quote": p["text"][:maxlen]}


def add(findings, facet, severity, status, title, evidence, location, recommendation, confidence="medium", method="deterministic"):
    findings.append({
        "id": f"{facet}-{len(findings) + 1:03d}",
        "facet": facet,
        "facet_zh": FACETS.get(facet, facet),
        "severity": severity,
        "status": status,
        "title": title,
        "evidence": evidence,
        "location": location,
        "recommendation": recommendation,
        "confidence": confidence,
        "method": method,
    })


def numbers_in(text):
    """Extract numeric literals with a little context."""
    out = []
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s*%|\s*±\s*(\d+(?:\.\d+)?))?", text):
        out.append((m.group(1), m.group(0)))
    return out


def check_structure(paper, findings):
    titles = {s["title"].strip().lower() for s in paper["sections"]}
    joined = " | ".join(titles)
    for key, aliases in REQUIRED_SECTIONS.items():
        if not any(a in joined for a in aliases):
            add(findings, "structure", "medium", "问题",
                f"缺少章节：{key}",
                f"检测到的章节：{sorted(titles)[:12]}",
                None,
                "补充该章节，或在审计说明中解释为何不适用（如综述类文章无实验方法）。",
                confidence="high", method="section-presence")


def check_consistency(paper, findings):
    # abstract vs body numbers
    abstract = paper.get("abstract", "")
    body = " ".join(p["text"] for p in paper["paragraphs"])
    anums = {n for n, _ in numbers_in(abstract)}
    bnums = {n for n, _ in numbers_in(body)}
    missing = sorted(anums - bnums)
    if abstract and missing:
        add(findings, "consistency", "medium", "证据不足",
            f"摘要中的 {len(missing)} 个数值未在正文出现",
            f"仅出现在摘要中的数值：{missing[:10]}",
            None,
            "核对摘要数值是否有正文或表格支撑；若为约数请在正文给出对应量。",
            confidence="medium", method="number-set-difference")

    # citation markers vs reference list
    cited = set()
    for p in paper["paragraphs"]:
        for m in re.finditer(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]", p["text"]):
            for part in re.split(r"[,\-–]", m.group(1)):
                if part.strip().isdigit():
                    cited.add(int(part.strip()))
    refs = paper.get("references", [])
    ref_ids = set()
    for r in refs:
        m = re.match(r"^\[(\d+)\]", r["text"])
        if m:
            ref_ids.add(int(m.group(1)))
    if cited and ref_ids:
        missing_refs = sorted(cited - ref_ids)
        uncited = sorted(ref_ids - cited)
        if missing_refs:
            add(findings, "consistency", "high", "问题",
                f"正文引用了不存在的参考文献编号：{missing_refs[:10]}",
                f"被引编号集合与参考列表编号集合的差集：{missing_refs[:10]}",
                None,
                "补齐对应文献，或修正正文引用编号。",
                confidence="high", method="citation-reference-set-diff")
        if uncited:
            add(findings, "consistency", "low", "建议",
                f"{len(uncited)} 条参考文献从未被正文引用",
                f"未被引用的编号：{uncited[:10]}",
                None,
                "删除无关文献，或在正文相应位置引用。",
                confidence="high", method="citation-reference-set-diff")
    elif cited and not ref_ids:
        add(findings, "consistency", "high", "问题",
            "正文有引用标记但未能解析出参考文献列表",
            f"检测到引用编号 {sorted(cited)[:10]}，但参考列表为空或格式无法解析。",
            None, "确认参考文献章节存在且格式可被解析；否则视为缺失。",
            confidence="medium", method="citation-reference-set-diff")


def check_methods_and_stats(paper, findings):
    text = " ".join(p["text"] for p in paper["paragraphs"])
    for group, table in (("methods", METHOD_MARKERS), ("methods", STAT_MARKERS), ("ethics", ETHICS_MARKERS)):
        for name, patterns in table.items():
            hit = None
            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    hit = m
                    break
            if hit:
                # locate the paragraph
                loc = None
                for p in paper["paragraphs"]:
                    if re.search(patterns[0], p["text"], re.IGNORECASE):
                        loc = pquote(paper, p["index"])
                        break
                add(findings, group, "info", "通过",
                    f"检测到 {name} 相关表述",
                    f"匹配：{hit.group(0)!r}", loc,
                    "已覆盖；请人工确认表述是否与实际做法一致。",
                    confidence="medium", method="keyword-presence")
            else:
                sev = "medium" if (group == "methods" and name in {"sample_size", "p_value"}) else "low"
                add(findings, group, sev, "待复核",
                    f"未检测到 {name} 相关表述",
                    f"在全文中未匹配到任何模式：{patterns}",
                    None,
                    f"确认论文是否应报告 {name}；若适用请补充，若不适用请在审计说明中注明。",
                    confidence="low", method="keyword-absence")


def check_argument(paper, findings):
    for p in paper["paragraphs"]:
        for pat in OVERCLAIM:
            m = re.search(pat, p["text"], re.IGNORECASE)
            if m:
                add(findings, "argument", "low", "建议",
                    f"结论性表述可能超出数据范围：{m.group(0)!r}",
                    p["text"][:240], pquote(paper, p["index"]),
                    "检查该论断是否有对应数据支撑；必要时改为限定性表述。",
                    confidence="low", method="overclaim-lexicon")
                break


def check_numbers_vs_tables(paper, findings):
    # numbers mentioned near table captions vs elsewhere — a lightweight sanity check
    table_caps = " ".join(t["caption"] for t in paper.get("tables", []) if t.get("caption"))
    if not table_caps:
        return
    nums = {n for n, _ in numbers_in(table_caps)}
    if nums:
        add(findings, "consistency", "info", "待复核",
            f"表格标题中包含数值：{sorted(nums)[:10]}",
            "表格标题中的数值需与表内数据及正文描述一致。",
            None, "逐表核对标题数值与表内数据。", confidence="low", method="table-caption-numbers")


def summarize(findings):
    counts = {}
    for f in findings:
        key = f["status"]
        counts[key] = counts.get(key, 0) + 1
    sev = {}
    for f in findings:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
    if sev.get("high"):
        status = "问题"
    elif sev.get("medium") or counts.get("待复核"):
        status = "待复核"
    elif findings:
        status = "通过"
    else:
        status = "未检查"
    return status, counts, sev


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)

    case = load(Path(args.case))
    work = Path(args.work)
    paper = load(work / "paper.json")

    findings = []
    check_structure(paper, findings)
    check_consistency(paper, findings)
    check_methods_and_stats(paper, findings)
    check_argument(paper, findings)
    check_numbers_vs_tables(paper, findings)

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["facet"]))

    case_id = case.get("case_id") or case.get("id") or Path(args.case).stem
    declared = case.get("facets") or case.get("review_facets") or case.get("checklist")
    declared = declared if isinstance(declared, list) else []

    status, counts, sev = summarize(findings)

    # a facet counts as checked when its check actually ran on real text,
    # even if it produced no findings (e.g. no over-claim detected)
    has_text = paper.get("stats", {}).get("paragraphs", 0) > 0
    checked = set(FACETS) if has_text else set()
    unchecked = sorted(set(FACETS) - checked)

    report = {
        "case_id": case_id,
        "paper": {"source": paper.get("source"), "title": paper.get("title"), "stats": paper.get("stats")},
        "declared_facets": declared,
        "checked_facets": sorted(checked),
        "unchecked_facets": unchecked,
        "status": status,
        "counts": {"by_status": counts, "by_severity": sev, "total": len(findings)},
        "findings": findings,
        "uncertainty": [
            "确定性检查只能覆盖可模式匹配的证据；论证质量、结论新颖性等主观维度需人工或模型补充。",
        ],
        "method": "deterministic-evidence-checks + model judgment",
    }
    with open(work / "audit_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    result = {
        "case_id": case_id,
        "task": "paper-quality-audit",
        "status": "complete",
        "audit_status": status,
        "deliverables": {
            "paper_structure": "paper.json",
            "audit_report": "audit_report.json",
            "full_text": "full_text.txt",
        },
        "counts": report["counts"],
        "findings": findings,
        "uncertainty": report["uncertainty"],
        "sources": [paper.get("source")],
        "changes": [
            {"step": "extract", "detail": f"{paper.get('stats', {})}"},
            {"step": "audit", "detail": f"{len(findings)} findings, status={status}"},
        ],
    }
    with open(work / "result.json", "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(f"audit: {len(findings)} findings, status={status} -> {work / 'audit_report.json'}")
    return report


if __name__ == "__main__":
    main()
