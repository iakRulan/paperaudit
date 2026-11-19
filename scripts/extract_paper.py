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
