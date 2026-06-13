# GLOSSARY — 术语表

## 平台 / 旧系统
- **AS400 / IBM i**:IBM 中端主机平台(原 AS/400)。
- **RPG III / RPG IV / RPGLE / SQLRPGLE**:RPG 各代;RPGLE 为自由式 RPG IV;SQLRPGLE 为含嵌入式 SQL 的 RPGLE。定宽列(III)对解析/LLM 最不友好。
- **CL / CLP / CLLE**:Control Language,作业控制脚本。
- **COBOL**:旧业务程序语言之一。
- **DDS**:Data Description Specifications,定义物理文件(PF)、逻辑文件(LF)、显示文件(DSPF)。
- **PF / LF**:物理文件 / 逻辑文件(≈表 / 视图+索引)。
- **DSPF / 显示文件**:屏幕定义;记录格式(R 规)≈ 一屏。
- **OPNQRYF**:Open Query File,运行时动态构造查询(类似动态 SQL)。
- **DB2 for i**:平台自带数据库。
- **CALL / CALLP / CALLB**:程序调用。

## 数据类型 / 常量
- **packed decimal**:压缩十进制(每字节两位数字),定点。
- **zoned decimal**:区位十进制(每字节一位数字)。
- **half-adjust**:RPG 的四舍五入。
- **figurative constant**:`*HIVAL`(最大值哨兵)、`*LOVAL`、`*BLANKS`、`*ZEROS`、`*ALL'x'` 等内建常量。
- **EBCDIC**:AS400 字符编码,排序序与 ASCII/Unicode 不同。

## 本工具术语
- **锚点 (anchor)**:确定性抽出的可对齐标识(表/字段/程序/事务码/屏幕/CALL 目标/SQL 表)。对齐的最强依据。
- **单元 (unit)**:一个分析粒度对象(一个 AS400 程序 / 一个 Java 类)。`unit_id` 稳定唯一。
- **对齐 (mapping)**:两侧单元的对应关系,落 `matched / as400_only / java_only` 三桶,允许 N:M。
- **桶 (bucket)**:matched=双侧匹配;as400_only=Java 缺失;java_only=Java 新增。
- **candidate_equivalent**:候选等价。语义看一致能到的最高结论,**待运行时验证**,不是 equivalent。
- **rule-diff**:规则级对比产物,逐条规则给 verdict + defect_class。
- **defect_class**:已知缺陷类(见 DEFECT-CLASSES.md)。
- **difftest**:运行时差异测试规格,同输入双跑、比对输出+数据扫描,以 AS400 为 oracle。
- **oracle**:判定对错的权威来源(本项目通常是 AS400 旧系统的实际运行结果)。
- **分类风险点 N / 已验 M**:某缺陷类命中的规则数 N,其中已有运行时结论的数 M。
- **协调人 (coordinator)**:跑离线 Python(建题、分配、汇总、合并)的人。
- **成员 (member)**:在 Copilot agent 里逐单元跑 skill 的 10 人之一。
