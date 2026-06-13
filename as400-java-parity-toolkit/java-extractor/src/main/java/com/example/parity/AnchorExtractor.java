package com.example.parity;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.statement.Statement;
import net.sf.jsqlparser.util.TablesNamesFinder;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Java 侧确定性锚点抽取器。
 *
 * 用 JavaParser(真正的 AST,而非正则)拿到:类、方法、方法调用图;
 * 读 @Table/@Entity/@Column 注解拿 JPA 表/列;
 * 把疑似 SQL 的字符串字面量交给 JSqlParser 解析出表名。
 *
 * 输出中间 JSON(契约见 tools/ingest_java_anchors.py 顶部注释),
 * 由 ingest_java_anchors.py 归一成 anchors.java.json。
 *
 * 用法:
 *   java -jar target/java-anchor-extractor.jar <srcRoot> <outFile>
 *   例: java -jar target/java-anchor-extractor.jar ../samples/java ./out/java-anchors.raw.json
 */
public class AnchorExtractor {

    static final ObjectMapper MAPPER = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("用法: java -jar java-anchor-extractor.jar <srcRoot> <outFile>");
            System.exit(2);
        }
        Path srcRoot = Paths.get(args[0]);
        Path outFile = Paths.get(args[1]);

        List<Map<String, Object>> units = new ArrayList<>();
        try (var stream = Files.walk(srcRoot)) {
            List<Path> javaFiles = stream
                    .filter(p -> p.toString().endsWith(".java"))
                    .sorted()
                    .collect(Collectors.toList());
            for (Path f : javaFiles) {
                try {
                    units.add(parseFile(srcRoot, f));
                } catch (Exception e) {
                    System.err.println("[WARN] 解析失败,跳过 " + f + ": " + e.getMessage());
                }
            }
        }

        Map<String, Object> root = new LinkedHashMap<>();
        root.put("tool", "java-extractor");
        root.put("version", "1.0");
        root.put("source_root", srcRoot.toString().replace('\\', '/'));
        root.put("units", units);

        Files.createDirectories(outFile.getParent());
        MAPPER.writeValue(outFile.toFile(), root);
        System.err.println("[INFO] Java 锚点抽取完成: " + units.size() + " 个单元 -> " + outFile);
    }

    static Map<String, Object> parseFile(Path srcRoot, Path file) throws IOException {
        CompilationUnit cu = StaticJavaParser.parse(file);
        String pkg = cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse("");

        ClassOrInterfaceDeclaration cls = cu.findFirst(ClassOrInterfaceDeclaration.class).orElse(null);
        String simpleName = cls != null ? cls.getNameAsString() : file.getFileName().toString().replace(".java", "");
        String fqcn = pkg.isEmpty() ? simpleName : pkg + "." + simpleName;

        Set<String> methods = new TreeSet<>();
        Set<String> calls = new TreeSet<>();
        Set<String> jpaTables = new TreeSet<>();
        Set<String> jpaColumns = new TreeSet<>();
        Set<String> sqlTables = new TreeSet<>();

        // 方法
        cu.findAll(com.github.javaparser.ast.body.MethodDeclaration.class)
                .forEach(m -> methods.add(m.getNameAsString()));

        // 方法调用图: scope.method 形式(scope 取不到时只记方法名)
        for (MethodCallExpr mc : cu.findAll(MethodCallExpr.class)) {
            String scope = mc.getScope().map(Object::toString).orElse("");
            calls.add(scope.isEmpty() ? mc.getNameAsString() : scope + "." + mc.getNameAsString());
        }

        // JPA 注解: @Table(name="...") / @Column(name="...")
        for (AnnotationExpr ann : cu.findAll(AnnotationExpr.class)) {
            String an = ann.getNameAsString();
            String nameVal = annotationStringMember(ann, "name");
            if (("Table".equals(an) || "Entity".equals(an)) && nameVal != null) {
                jpaTables.add(nameVal.toUpperCase());
            }
            if ("Column".equals(an) && nameVal != null) {
                jpaColumns.add(nameVal.toUpperCase());
            }
        }

        // SQL 字符串字面量 -> JSqlParser 解析表名
        for (StringLiteralExpr lit : cu.findAll(StringLiteralExpr.class)) {
            String s = lit.getValue();
            if (looksLikeSql(s)) {
                try {
                    Statement st = CCJSqlParserUtil.parse(s);
                    TablesNamesFinder finder = new TablesNamesFinder();
                    for (String t : finder.getTableList(st)) {
                        sqlTables.add(t.toUpperCase());
                    }
                } catch (Exception ignore) {
                    // 不是合法 SQL 或方言不支持,忽略
                }
            }
        }

        Map<String, Object> u = new LinkedHashMap<>();
        u.put("path", srcRoot.getParent() == null
                ? file.toString().replace('\\', '/')
                : relPathFromCwd(file));
        u.put("class", fqcn);
        u.put("methods", new ArrayList<>(methods));
        u.put("calls", new ArrayList<>(calls));
        u.put("jpa_tables", new ArrayList<>(jpaTables));
        u.put("jpa_columns", new ArrayList<>(jpaColumns));
        u.put("sql_tables", new ArrayList<>(sqlTables));
        u.put("sql_columns", new ArrayList<>()); // 列级抽取可按需扩展
        u.put("endpoints", new ArrayList<>());    // @RequestMapping 等可按需扩展
        u.put("mybatis_tables", new ArrayList<>());
        return u;
    }

    /** 取注解里 name 成员的字符串值(支持 @X("v") 单值与 @X(name="v"))。 */
    static String annotationStringMember(AnnotationExpr ann, String member) {
        if (ann.isSingleMemberAnnotationExpr()) {
            var v = ann.asSingleMemberAnnotationExpr().getMemberValue();
            return v.isStringLiteralExpr() ? v.asStringLiteralExpr().getValue() : null;
        }
        if (ann.isNormalAnnotationExpr()) {
            return ann.asNormalAnnotationExpr().getPairs().stream()
                    .filter(p -> p.getNameAsString().equals(member) && p.getValue().isStringLiteralExpr())
                    .map(p -> p.getValue().asStringLiteralExpr().getValue())
                    .findFirst().orElse(null);
        }
        return null;
    }

    static boolean looksLikeSql(String s) {
        String u = s.trim().toUpperCase();
        return u.startsWith("SELECT ") || u.startsWith("INSERT ") || u.startsWith("UPDATE ")
                || u.startsWith("DELETE ") || u.contains(" FROM ") || u.contains(" JOIN ");
    }

    static String relPathFromCwd(Path file) {
        Path cwd = Paths.get("").toAbsolutePath();
        Path abs = file.toAbsolutePath();
        try {
            return cwd.relativize(abs).toString().replace('\\', '/');
        } catch (Exception e) {
            return abs.toString().replace('\\', '/');
        }
    }
}
