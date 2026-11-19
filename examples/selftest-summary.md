# 自测记录（示例，非平台正式案例）

- 日期：2026-11-19
- 输入：arXiv:1706.03762（Attention Is All You Need）PDF，15 页
- 命令：

```bash
python3 scripts/extract_paper.py --paper paper.pdf --out .
python3 scripts/audit.py --case case.json --work .
python3 scripts/report.py --case case.json --work .
```

## 结果摘要

| 指标 | 值 |
|-|-|
| 页面 / 段落 / 文献 | 15 / 1025 / 44 |
| 章节数 | 50+ |
| findings 总数 | 19 |
| 问题 / 待复核 / 通过 | 3 / 13 / 3 |
| audit_status | 待复核 |

## 观察到的真实问题与修复（示例价值）

1. **章节切分未闭合**：最初的 `segment()` 没有维护当前章节的段落列表，导致所有标题都不触发"封章节"，整篇被并成 1 个章节，结构检查全部误报。修复：在切分时同步维护 `current["paragraphs"]`。
2. **标题误判**：`Google Brain` 等作者单位被当成标题。修复：只接受编号标题、已知章节名或全大写标题。
3. **过度报告**：初版把"未检测到某关键词"一律算作问题。修复：改为 `待复核`，并在建议中说明可能不适用于该文体。

> 本文件为**技能自测示例**，不冒充平台正式案例结果。
