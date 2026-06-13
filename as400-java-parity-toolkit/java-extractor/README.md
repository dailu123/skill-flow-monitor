# java-extractor — Java 侧确定性锚点抽取器

用**真正的解析器**(不是正则)抽 Java 锚点,做到接近 100% 准:

- **JavaParser**:出 AST,拿类、方法、方法调用图。
- **JSqlParser**:解析代码里的 SQL 字符串字面量,得到表名(可扩展到列)。
- **JPA 注解**:读 `@Table(name=...)` / `@Entity` / `@Column(name=...)`。
- (可扩展)MyBatis mapper XML、`@RequestMapping` 端点。

产出一份**中间 JSON**,交给 `tools/ingest_java_anchors.py` 归一成本工具链统一的
`analysis/anchors.java.json`,再喂 `build_units.py`。

## 构建
需要 JDK 17+ 和 Maven。
```bash
cd java-extractor
mvn -q clean package
# 产物: target/java-anchor-extractor.jar (fat-jar)
```

## 运行
```bash
# <srcRoot> <outFile>
java -jar target/java-anchor-extractor.jar ../samples/java ./out/java-anchors.raw.json
```

## 归一并接入流水线(回到仓库根目录)
```bat
python tools\ingest_java_anchors.py --in java-extractor\out\java-anchors.raw.json --out analysis\anchors.java.json
python tools\build_units.py --anchors analysis\anchors.as400.json analysis\anchors.java.json --out analysis\units.csv
```

## 中间 JSON 契约
`ingest_java_anchors.py` 顶部注释是唯一权威契约。每个 unit:
| 字段 | 含义 |
| --- | --- |
| `path` | 源文件相对路径(需与语义产物的 path 一致,便于 verify 对账) |
| `class` | 全限定类名 |
| `methods` / `calls` | 方法列表 / 方法调用图 |
| `jpa_tables` / `jpa_columns` | JPA 注解里的表/列 |
| `sql_tables` / `sql_columns` | JSqlParser 解析出的表/列 |
| `endpoints` / `mybatis_tables` | 可选扩展 |

> 没装 Maven/JDK 也能先跑通流水线:`samples/java_extract/java-anchors.raw.json` 是一份
> 手写的中间 JSON 样例(就是本抽取器对 `samples/java` 应产出的结果),可直接喂
> `ingest_java_anchors.py` 验证 Python 侧链路。

## 为什么不在 Python 里解析 Java?
解析 Java 最稳的就是 Java 自己的 AST 库;在 Python 里重写一个 Java 解析器既不准也维护不起。
本工具链因此把"确定性锚点抽取"做成可插拔:任何来源(本抽取器 / Spoon / Eclipse JDT)
只要产出符合契约的 JSON,`ingest_java_anchors.py` 都能接。
