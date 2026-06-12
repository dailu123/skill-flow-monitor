# 中间产物（evidence/）—— 用来印证最终报告

最终报告（reports/）里的每个结论都必须能回溯到这里的某一行。人工抽查方法见各节。

## 文件清单

| 文件 | 谁生成 | 内容 | 怎么印证 |
|------|--------|------|----------|
| `mca/inventory.csv` | 阶段A 每单元追加 | MCA 的接口/类/表/作业清单 | 随机抽 5 行，打开 location 列的 文件:行号 看是否真有此物 |
| `hub/inventory.csv` | 阶段A 每单元追加 | HUB 的程序/PF/LF/DSPF/CL 清单 | 同上 |
| `mca/business-functions.md` | 阶段A | 从代码推断的业务功能 + 证据 | 抽查证据行号 |
| `hub/business-functions.md` | 阶段A | 同上 | 同上 |
| `mca/relations.csv` `hub/relations.csv` | 阶段A | AI 验证的跨模块依赖（共享表/MQ/文件接口），会画到代码地图上 | 抽查 evidence 列的 文件:行号 |
| `capabilities.csv` | 阶段C | 业务能力对齐矩阵（对比报告的唯一数据源） | 见下 |

## capabilities.csv 印证方法
1. 报告 COMPARE.md / BUSINESS.md 里的统计数字（如“重叠能力 31 项”）必须等于本表对应行数。
2. 每行的 mca_modules / hub_modules 必须出现在对应 work/*/PROGRESS.md 的队列里
   （render_status.py 会自动检查并打印 ⚠ 警告——看到警告就是模型在编造）。
3. parity=mca-only / hub-only 的行最值得人工复核：去对面仓库搜关键词确认真的没有。

## inventory.csv 计数印证（一条命令复核报告数字）
    python -c "import csv;print(sum(1 for r in csv.DictReader(open('code-analysis-kit/evidence/hub/inventory.csv',encoding='utf-8-sig')) if r['kind']=='table'))"
