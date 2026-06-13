---
mode: agent
description: 对一个已对齐的对做规则级精细对比,逐条过缺陷类(触发 compare-pair skill)
---

# /compare-pair

对**我当前领到的 mapping(bucket=matched)** 做规则级精细对比。请使用 **compare-pair** skill。

铁律:
- 语义一致最多判 `candidate_equivalent`,**绝不直接判 equivalent**。
- 每条规则都对照 `docs/DEFECT-CLASSES.md` 逐项过筛,命中填 `defect_class` 并把 `needs_runtime_test=true`。
- 拿不准就 `uncertain` + `needs_runtime_test=true`。

按以下做:
1. 读该 mapping 两侧 semantics(`as400_units` / `java_units`)。
2. 逐条规则对比,产出 `rule_id, as400_assertion, java_assertion, verdict(same|different|uncertain), defect_class, confidence, evidence, needs_runtime_test`。
3. 给 `pair_verdict`(candidate_equivalent | different | uncertain)。
4. 写到 `analysis/diffs/<mapping_id>.json`,符合 `schemas/rule-diff.schema.json`。
5. 自检 `python tools/validate_outputs.py --file analysis/diffs/<mapping_id>.json --schema rule-diff`。
