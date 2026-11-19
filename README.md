# paperaudit — 论文质量审查 Skill

把"这篇稿子哪里有问题"变成一组**可执行、可核对、可交办**的条目：哪一页、哪一段、什么证据、多严重、怎么改。

## 解决什么问题

普通 Agent 审查论文的常见失败：交回一段"结构完整、论证充分"的评语；同一份稿子两次输出字段不同；说"引用不支持观点"却不列出被引文献与本文论断的对应；把学科写作惯例误判为缺陷；解析失败后静默跳过却报告"已完整审查"。

`paperaudit` 把可模式匹配的检查做成确定性脚本（每条都带原文定位与引用），把需要理解力的判断留给模型，并强制记录**未检查项**。

## 安装与依赖

- Python 3.9+
- PyMuPDF（PDF 输入时需要；`pip install pymupdf`）
- 其余仅标准库

```
paperaudit/
├── SKILL.md
├── README.md
├── GITHUB_URL.txt
├── references/
│   ├── facets-and-severity.md   # 检查项与严重度判据
│   └── output-schema.md         # 输出字段字典
├── examples/
│   ├── case.example.json
│   └── selftest-summary.md
└── scripts/
    ├── extract_paper.py         # PDF/文本 → 可定位结构
    ├── audit.py                 # 确定性检查
    └── report.py                # 合并模型判断 + result.json
```

## 用法（最小示例）

```bash
# 1) 提取：页 / 章节 / 段落（带索引）
python3 scripts/extract_paper.py --paper paper.pdf --out /app/work

# 2) 确定性检查
python3 scripts/audit.py --case /input/case.json --work /app/work

# 3) （可选）把模型判断写入 /app/work/findings_model.json，再合并
python3 scripts/report.py --case /input/case.json --work /app/work
```

输入 `case.json` 示例：

```json
{
  "case_id": "demo",
  "paper": "paper.pdf",
  "facets": ["structure", "consistency", "methods", "argument", "ethics"]
}
```

> 以上为**示意示例**，不是正式案例结果。

## 输出

| 文件 | 内容 |
|-|-|
| `paper.json` | 标题、摘要、章节、段落（含 page/section/index）、文献、表、图 |
| `full_text.txt` | 纯文本全文，供阅读与模型判断 |
| `audit_report.json` | `findings[]` + `checked_facets` + `unchecked_facets` + 计数 |
| `result.json` | `case_id` / `audit_status` / counts / findings / uncertainty / sources |

每条 finding：`facet` / `severity` / `status` / `title` / `evidence` / `location`（page+section+quote）/ `recommendation` / `confidence` / `method`。

## 严重度与状态判据

- **severity**：`high`（事实错误、引用缺失、数据与结论冲突）/ `medium`（报告不全、结构缺位）/ `low`（规范、建议）/ `info`（已覆盖，供人工确认）
- **status**：`问题`（确定存在）/ `证据不足`（无法确认，需补材料）/ `建议`（可改进）/ `待复核`（需人工或模型判断）/ `通过`（已覆盖）
- `audit_status`：有 high → `问题`；有 medium 或待复核 → `待复核`；只有 low/info → `通过`；无条目 → `未检查`

## 关键设计

- **可定位**：每条 finding 带页码、章节、段落索引与原文引用。
- **可复核**：所有判定可回到 `paper.json` 的段落索引核对。
- **不编造**：无法确认的写 `待复核`；没查写的进 `unchecked_facets`。
- **出处可见**：`method` 区分 `deterministic-*` 与 `model-judgment`。

## 局限

- 确定性检查只能覆盖可模式匹配的证据；
- 论证质量、新颖性、引用是否真正支持观点，需要模型或人工判断；
- 扫描版 PDF 无文本层时相应检查项标记为未检查。

## 许可与版本

- 版本：paperaudit 1.0.0
- 依赖：Python 3.9+，PyMuPDF（PDF 输入）。
