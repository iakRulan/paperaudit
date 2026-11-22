---
name: paperaudit
description: "Audit a scientific paper for quality, structure, fact consistency, citation support, methods/statistics reporting, argumentation and research integrity. Produces a fixed-schema findings list where every item carries a location (page/section/paragraph), a verbatim quote, a severity and a recommendation, plus an explicit unchecked list. Trigger on: '论文审查', '论文质量审查', '审稿', 'paper review', 'audit this paper', 'check this manuscript', 'review for publication'. Not for: language polishing, translation, plagiarism checking or typesetting."
---

# paperaudit — Evidence-bearing Paper Quality Audit

> **脚本路径**：本技能安装于 `/skills/weekly-skill/`，脚本绝对路径为 `/skills/weekly-skill/scripts/`（工作目录是 `/app/work`，不要用相对路径）。

Turn "this paper has problems" into a set of actionable, checkable items: which sentence, which section, what evidence, how severe, what to change. The failure mode this skill exists to prevent: a vague commentary ("结构完整、论证充分"), a flat list of typos, or unsupported claims like "引用不支持观点" with no mapping to the cited work.

**Method in one line:** extract the paper into a citable structure (page / section / paragraph), run deterministic checks that are grounded in verbatim quotes, then let the model add judgment on the facets that cannot be pattern-matched — and record what was **not** checked.

## When to use

- Input: a case file (default `/input/case.json`) naming the paper (PDF or text) and the review facets; the actual paper.
- Output: under `/app/output` — `paper.json`, `full_text.txt`, `audit_report.json`, `result.json`.
- Works on PDF (PyMuPDF) and plain text/Markdown. Scanned PDFs without a text layer are reported as a limitation, not silently skipped.

## Pipeline (run in order)

### Phase 1 — Extract to a citable structure

```bash
python3 /skills/weekly-skill/scripts/extract_paper.py --paper <paper.pdf> --out /app/work
```

Produces `work/paper.json`: title, abstract, per-page stats, sections, paragraphs (each with `page`, `section`, `index`, `text`), references, tables, figures. Also writes `work/full_text.txt` for reading.

Read `paper.json` — do not re-parse the PDF ad hoc. Every later finding must reference a paragraph `index` so a reviewer can jump back to the source.

If the PDF has almost no text (scanned), say so in `result.json.uncertainty` and continue with OCR only if an OCR tool is available; otherwise mark the affected facets `未检查`.

### Phase 2 — Deterministic, evidence-bearing checks

```bash
python3 /skills/weekly-skill/scripts/audit.py --case /input/case.json --work /app/work
```

Checks (each grounded in a quote + location):

| Facet | What it checks |
|-|-|
| `structure` | presence of abstract / introduction / methods / results / discussion / conclusion / references / data availability |
| `consistency` | abstract numbers vs body numbers; citation markers `[n]` vs reference list (cited-but-missing, never-cited); table-caption numbers |
| `methods` | sample size, randomization, control, blinding, replication |
| `methods` (stats) | p-value, CI, effect size, α, multiple-testing correction |
| `argument` | over-claim lexicon (`prove`, `demonstrstrate`, `cure`, `definitive`) relative to data scope |
| `ethics` | ethics approval, consent, conflict of interest, funding, author contributions |

Output `work/audit_report.json`: `findings[]` with `id`, `facet`, `severity` (high/medium/low/info), `status` (问题/证据不足/建议/待复核/通过), `title`, `evidence`, `location` (page/section/quote), `recommendation`, `confidence`, `method`. Plus `checked_facets` and `unchecked_facets`.

### Phase 3 — Model judgment on top (do not skip)

The deterministic checks cannot judge argument quality, novelty, or whether a citation actually supports the claim. Read `full_text.txt` and the structured report, then:

1. For every `待复核` finding, decide: keep it, downgrade it, or explain why it does not apply to this paper type.
2. Add `argument`/`consistency` findings that require understanding (e.g. a claim in the discussion not supported by any result; a reference whose topic does not match the citing sentence). Each added finding **must** carry a paragraph index and a verbatim quote.
3. Fill `unchecked_facets` honestly — if a facet could not be assessed, say so and why.

Merge your additions into `audit_report.json` (keep the same schema) and record them with `method: "model-judgment"` so the provenance is visible.

### Phase 4 — Report

```bash
python3 /skills/weekly-skill/scripts/report.py --case /input/case.json --work /app/work
```

Writes `work/result.json` with `case_id`, `audit_status` (通过 / 问题 / 待复核 / 未检查), counts by severity and status, the full findings list, `uncertainty`, `sources` and `changes`.

Copy to `/app/output`:

```bash
mkdir -p /app/output
cp /app/work/paper.json /app/work/full_text.txt /app/work/audit_report.json /app/work/result.json /app/output/
```

## Rules that must hold

1. **Every finding has a location and a quote.** "引用不支持观点" without the two sides of the mapping is not a finding.
2. **Separate 错误 / 证据不足 / 建议.** A missing data-availability statement is not the same as a fabricated result.
3. **No fabricated verdicts.** If the paper is fine on a facet, say `通过`; if you cannot tell, say `待复核`; if you did not look, it goes in `unchecked_facets`. Never invent a defect.
4. **Distinguish "method is flawed" from "method is acceptable but under-reported".**
5. **Discipline conventions are not defects.** Do not flag a CS paper for lacking a medical ethics statement — mark it `待复核`/`不适用` instead.

## Exception handling

| Situation | Behaviour |
|-|-|
| Scanned PDF, no text layer | recorded in `uncertainty`; facets that need text are `未检查` |
| Reference list format unusual | citation check reports `待复核` with the raw sample, not a false mismatch |
| No methods section (e.g. review article) | `structure` finding kept, with recommendation to confirm inapplicability |
| Paper shorter than expected | extraction stats recorded; checks run on what exists |
| Missing/unparseable case file | stop and report honestly; do not guess the paper path |

## Self-check

```bash
python3 -c "import json;r=json.load(open('/app/work/audit_report.json'));print(r['status'], r['counts']);print('unchecked:', r['unchecked_facets'])"
python3 -c "import json;r=json.load(open('/app/work/result.json'));print(r['case_id'], r['audit_status'])"
```

Every finding must have a non-empty `evidence`; `unchecked_facets` must be explicit.


## 附录：脚本源码（自包含回退）

如果 `/skills/weekly-skill/scripts/` 下的脚本不存在（技能安装时未带上脚本），把下面每一段源码写到 `/app/work/` 下的对应文件（保持相对路径），再按上方命令运行。所有脚本均为纯文本，可直接落盘。

### scripts/audit.py

```python
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
```

### scripts/extract_paper.py

```python
#!/usr/bin/env python3
"""extract_paper — turn a paper (PDF or text) into a structured, citable JSON.

Usage:
    python3 extract_paper.py --paper PATH --out DIR [--fulltext full_text.txt]

Output `paper.json`:
    title, abstract, pages[], sections[], paragraphs[], tables[], figures[],
    references[], stats (counts), extraction_notes[]

Every paragraph carries `page`, `section`, `index` and `text` so an audit
finding can point at an exact location. Nothing is interpreted or corrected —
this script only extracts, so a reviewer can always go back to the source.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?[A-Z][A-Za-z0-9 ,\-:()&/]{3,80}$"
)
NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
KNOWN_SECTIONS = {
    "abstract", "introduction", "background", "related work", "methods",
    "method", "materials and methods", "results", "discussion", "conclusion",
    "conclusions", "references", "acknowledgements", "acknowledgments",
    "appendix", "supplementary", "data availability", "author contributions",
}


def extract_pdf(path: Path):
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for PDF input")
    doc = fitz.open(str(path))
    pages = []
    for pno in range(doc.page_count):
        page = doc[pno]
        text = page.get_text("text")
        images = []
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                images.append({"xref": xref, "w": pix.width, "h": pix.height})
            except Exception:
                pass
        pages.append({"page": pno + 1, "text": text, "images": images})
    return pages


def extract_text(path: Path):
    raw = path.read_text(encoding="utf-8", errors="ignore")
    # split on form feeds, else treat the whole file as one page
    chunks = raw.split("\f")
    if len(chunks) == 1:
        chunks = [raw]
    return [{"page": i + 1, "text": c, "images": []} for i, c in enumerate(chunks)]


def is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 90:
        return False
    if NUMBERED_RE.match(s):
        return True
    if s.lower().rstrip(". ") in KNOWN_SECTIONS:
        return True
    # ALL-CAPS headings only (avoids affiliations such as "Google Brain")
    if s.isupper() and len(s) >= 4 and " " in s:
        return True
    return False


def segment(pages):
    """Split page text into sections of paragraphs."""
    sections = []
    paragraphs = []
    current = {"title": "Front matter", "level": 0, "start_index": 0, "paragraphs": []}
    idx = 0
    for page in pages:
        for raw_line in page["text"].splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if is_heading(line):
                if current["paragraphs"]:
                    current["end_index"] = idx
                    sections.append(current)
                title = NUMBERED_RE.sub(r"\1 \2", line) if NUMBERED_RE.match(line) else line
                level = len(re.findall(r"\d+\.", line.split()[0])) if line[:1].isdigit() else 1
                current = {"title": title, "level": level, "start_index": idx, "paragraphs": []}
                continue
            paragraphs.append({
                "index": idx,
                "page": page["page"],
                "section": current["title"],
                "text": line,
            })
            current["paragraphs"].append(idx)
            idx += 1
    if current["paragraphs"]:
        current["end_index"] = idx
        sections.append(current)
    return sections, paragraphs


def extract_references(paragraphs):
    refs = []
    for p in paragraphs:
        t = p["text"]
        if re.match(r"^\[\d+\]", t) or re.match(r"^\d+\.\s+[A-Z]", t):
            refs.append({"index": p["index"], "page": p["page"], "text": t[:400]})
    return refs


def extract_tables(pages):
    tables = []
    for page in pages:
        lines = [l.strip() for l in page["text"].splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if re.search(r"\bTable\s+\d+", line, re.IGNORECASE):
                tables.append({"page": page["page"], "caption": line[:200], "line_index": i})
    return tables


def extract_figures(pages):
    figs = []
    for page in pages:
        lines = [l.strip() for l in page["text"].splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if re.search(r"\bFig(?:ure)?\.?\s*\d+", line, re.IGNORECASE):
                figs.append({"page": page["page"], "caption": line[:200], "line_index": i})
        for img in page.get("images", []):
            if img["w"] >= 200 and img["h"] >= 150:
                figs.append({"page": page["page"], "caption": None, "image": img})
    return figs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fulltext", default=None)
    args = ap.parse_args(argv)

    paper = Path(args.paper)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    notes = []

    if paper.suffix.lower() == ".pdf":
        pages = extract_pdf(paper)
        notes.append(f"extracted {len(pages)} PDF pages with PyMuPDF")
    else:
        pages = extract_text(paper)
        notes.append(f"read {len(pages)} text chunk(s) from {paper.suffix or 'text'}")

    sections, paragraphs = segment(pages)
    references = extract_references(paragraphs)
    tables = extract_tables(pages)
    figures = extract_figures(pages)

    title = paragraphs[0]["text"][:200] if paragraphs else paper.stem
    abstract = ""
    for s in sections:
        if s["title"].strip().lower().startswith("abstract"):
            abstract = " ".join(paragraphs[i]["text"] for i in s.get("paragraphs", []))[:2000]
            break

    fulltext = "\n".join(p["text"] for p in paragraphs)
    fulltext_path = Path(args.fulltext) if args.fulltext else out / "full_text.txt"
    fulltext_path.write_text(fulltext, encoding="utf-8")

    data = {
        "source": str(paper),
        "title": title,
        "abstract": abstract,
        "pages": [{"page": pg["page"], "chars": len(pg["text"]), "images": len(pg.get("images", []))} for pg in pages],
        "sections": sections,
        "paragraphs": paragraphs,
        "references": references,
        "tables": tables,
        "figures": figures,
        "stats": {
            "pages": len(pages),
            "sections": len(sections),
            "paragraphs": len(paragraphs),
            "references": len(references),
            "tables": len(tables),
            "figures": len(figures),
        },
        "extraction_notes": notes,
    }
    with open(out / "paper.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"extract_paper: {len(pages)} pages, {len(paragraphs)} paragraphs, "
          f"{len(references)} references -> {out / 'paper.json'}")
    return data


if __name__ == "__main__":
    main()
```

### scripts/report.py

```python
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
```
