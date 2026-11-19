# 输出字段字典

## `paper.json`（提取产物）

| 字段 | 类型 | 说明 |
|-|-|-|
| `source` | string | 输入文件路径 |
| `title` | string | 首个段落文本（或文件名） |
| `abstract` | string | Abstract 章节拼接文本（≤2000 字符） |
| `pages[]` | array | `page` / `chars` / `images` |
| `sections[]` | array | `title` / `level` / `start_index` / `end_index` / `paragraphs[]` |
| `paragraphs[]` | array | `index` / `page` / `section` / `text` — **定位锚点** |
| `references[]` | array | `index` / `page` / `text` |
| `tables[]` / `figures[]` | array | `page` / `caption` |
| `stats` | object | 计数 |
| `extraction_notes[]` | array | 提取方式与限制 |

## `audit_report.json`

| 字段 | 说明 |
|-|-|
| `case_id` | 输入标识 |
| `paper` | `{source, title, stats}` |
| `declared_facets` | 案例声明的检查面 |
| `checked_facets` | 本次覆盖到的 facet |
| `unchecked_facets` | **未检查的 facet**（不得省略） |
| `status` | 通过 / 问题 / 待复核 / 未检查 |
| `counts` | `by_status` / `by_severity` / `total` |
| `findings[]` | 问题条目（见下） |
| `model_additions` | `{added, dropped[]}` |

## `findings[]`

| 字段 | 类型 | 说明 |
|-|-|-|
| `id` | string | `<facet>-<序号>` 或 `model-<序号>` |
| `facet` | string | `structure` / `consistency` / `methods` / `argument` / `ethics` |
| `facet_zh` | string | 中文名 |
| `severity` | `high`/`medium`/`low`/`info` | |
| `status` | `问题`/`证据不足`/`建议`/`待复核`/`通过` | |
| `title` | string | 一句话问题描述 |
| `evidence` | string | 判定依据（模式、集合差、匹配文本） |
| `location` | object/null | `{index, page, section, quote}` |
| `recommendation` | string | 修改建议 |
| `confidence` | `high`/`medium`/`low` | |
| `method` | string | `deterministic-*` 或 `model-judgment` |

## `result.json`

`case_id` / `task` / `status` / `audit_status` / `deliverables` / `counts` / `checked_facets` / `unchecked_facets` / `model_additions` / `findings` / `uncertainty` / `sources` / `changes`。
