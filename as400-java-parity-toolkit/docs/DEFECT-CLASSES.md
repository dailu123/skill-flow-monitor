# DEFECT-CLASSES — 迁移对等性已知缺陷类清单

这是 `compare-pair` 的核对清单,也是 `rule-diff.schema.json` 里 `defect_class` 的取值来源。
每条规则对比时**逐类过筛**:命中就填对应 `defect_class`,并把 `needs_runtime_test` 置 true。
拿不准 → `uncertain` + `needs_runtime_test=true`,不要赌成 same。

每类给出:**AS400 行为 / Java 易错点 / 判别问句 / 建议运行时边界用例**。

---

## ebcdic-sort — EBCDIC 排序序差异
- **AS400**:字符比较/排序按 EBCDIC 码序。常见后果:小写字母 < 大写字母、数字排在字母**之后**、特殊符号位置不同。SETLL/READE 范围、ORDER BY、`IF A > B` 都受影响。
- **Java 易错点**:默认按 Unicode/UTF-16 码序(数字 < 大写 < 小写),与 EBCDIC 几乎相反;`String.compareTo`、`ORDER BY`(取决于 DB collation)未还原 EBCDIC。
- **判别问句**:这条规则涉及排序、范围扫描、键比较吗?键里混有数字+字母+符号吗?
- **边界用例**:键集合含 `"A1"`、`"1A"`、`"a"`、`" "`(空格)、特殊符号,看两侧排序结果与范围命中。

## packed-zoned-precision — packed/zoned 十进制精度与舍入
- **AS400**:packed/zoned decimal 是定点十进制;RPG 默认 half-adjust(四舍五入到指定 scale)或直接截断,中间结果有固定字段长度。
- **Java 易错点**:用 `double`/`float`(二进制浮点)导致精度漂移;`BigDecimal` 没设对 scale 或 RoundingMode(HALF_UP vs HALF_EVEN vs DOWN);除法默认舍入与 AS400 不一致。
- **判别问句**:涉及金额/数量的乘除、累加、舍入吗?scale 是多少?用的什么舍入?
- **边界用例**:`0.005` 舍入、连续累加误差、除不尽(如 `10/3`)、大数(逼近字段位宽)。容差应为 **0**。

## null-blank-empty — null / 空白 / 空串语义混淆
- **AS400**:`*BLANKS`(全空格)、`*ZEROS`(全零)、SQL NULL 三者不同;很多字段用空格/零表示"无值",不用 NULL。
- **Java 易错点**:把空白 trim 成 `""`、把 NULL 当 `""`、把零当 null;`Optional`/包装类型 null 与数据库 NULL 映射错位。
- **判别问句**:这条规则里"空值"指的是 *BLANKS、*ZEROS 还是 SQL NULL?两侧对"空"的判定一致吗?
- **边界用例**:输入空格串 vs 空串 vs NULL vs 全零,看分支走向、写库结果、比较结果。

## date-century-window — 日期世纪窗口与格式
- **AS400**:大量两位年份 + 世纪窗口规则(如 <50 → 20xx,>=50 → 19xx);6 位(YYMMDD)与 8 位日期并存;非法日期处理各异。
- **Java 易错点**:`LocalDate` 解析窗口不同、用了系统默认 pivot、对非法日期抛异常而非旧系统的兜底值;时区介入。
- **判别问句**:有两位年份吗?世纪 pivot 是多少?非法/全零日期怎么处理?
- **边界用例**:年份 `49` / `50` / `00` / `99`,`000000`,`20240230`(非法),闰年 `0229`。

## logical-delete — 逻辑删除语义
- **AS400**:常用删除标记字段(如 `DEL_STATUS`/`DLT_FLG`='D'/'1')做逻辑删除;读取逻辑常带隐式过滤,或用逻辑文件排除。
- **Java 易错点**:物理删除替代逻辑删除;查询忘了加 `WHERE del_flag <> 'D'`;或反过来旧系统物理删而 Java 软删,历史口径变。
- **判别问句**:有删除标记字段吗?读路径是否过滤它?统计/报表是否包含被标删行?
- **边界用例**:存在被标删记录时的查询、计数、唯一键冲突(标删后重建同键)。

## numeric-overflow-truncation — 数值溢出与字段截断
- **AS400**:字段定长,溢出常**截高位**(silent wrap)或触发半告警;中间结果字段长度固定导致截断。
- **Java 易错点**:`int`/`long` 溢出语义不同、`BigDecimal` 不溢出(行为反而"更对"但与旧系统不一致)、字符串字段未按旧长度截断。
- **判别问句**:运算结果可能超字段位宽吗?旧系统溢出行为是什么?中间字段会截断吗?
- **边界用例**:逼近并超过字段最大值、负数边界、累加溢出、超长字符串入定长字段。

## transaction-commit-boundary — 事务/提交边界
- **AS400**:COMMIT/ROLLBACK 边界、提交粒度、commitment control 作用域;一个工作单元的原子性。
- **Java 易错点**:`@Transactional` 边界与旧系统不一致(粒度更粗/更细)、隔离级别不同、部分提交导致中间态可见、异常回滚范围错。
- **判别问句**:这个业务操作的原子边界在哪?哪些写在一个事务内?失败回滚什么?
- **边界用例**:中途失败注入,检查两侧落库的部分结果是否一致;并发下的可见性。

## figurative-constant — figurative constant 语义
- **AS400**:`*HIVAL`/`*LOVAL`/`*BLANKS`/`*ZEROS`/`*ALL'x'` 等;`*HIVAL` 常用作排序/查找的哨兵高值键。
- **Java 易错点**:没有等价哨兵,用 `null`/`Integer.MAX_VALUE`/`"zzz"` 近似导致比较/边界错;`*HIVAL` 的"最大可能值"语义未按字段类型还原。
- **判别问句**:用到 figurative constant 了吗?它在比较/赋值里代表什么?Java 用什么还原?
- **边界用例**:以 *HIVAL/*LOVAL 作为范围端点的扫描;空白/零常量参与的比较。

## dynamic-query-condition-range — 动态查询条件与范围边界
- **AS400**:OPNQRYF / 嵌入式 SQL 动态构造查询;可选过滤条件、范围端点(含/不含)、空条件(无过滤=全表)语义明确。
- **Java 易错点**:动态 SQL/Criteria 拼接时,空条件被当成"无结果"或反之;`BETWEEN` 端点含否不一致;可选过滤为空时行为变化;`LIKE`/通配符语义差异。
- **判别问句**:查询条件是动态拼的吗?某过滤为空时该全过还是不过?范围端点含不含?
- **边界用例**:所有可选过滤为空、单端点为空、范围端点恰好等于边界值、通配符为空串。

---

## 用法提示
- 一条规则可能命中**多类**;schema 当前每条 rule 记一个主 `defect_class`,其余在 `evidence`/`notes` 注明,或拆成多条 rule。
- 命中任一精度/排序/边界/事务类,几乎都应 `needs_runtime_test=true`——这些是语义层看不准、必须运行时兜的。
- `propagate-pattern` 时,按 `defect_class` 横扫,产"分类风险点 N / 已验 M"。
