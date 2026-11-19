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