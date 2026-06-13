package com.example.customer;

import java.util.List;

/**
 * CustomerSearch - 按客户编号范围检索 (样例,非真实生产码)
 * 对应 AS400 程序 CUSTSRCH。
 * 故意埋差异:EBCDIC 排序序 与 空条件处理。
 */
public class CustomerSearch {

    @Table(name = "CUSTMAS")
    private CustomerRepo custMas;

    public List<Customer> search(String fromNo, String toNo) {
        // 差异点 1 (dynamic-query-condition-range): 空 from/to 被当成 "",
        // 而非 AS400 的 *LOVAL/*HIVAL 哨兵,导致空条件语义不同
        String f = (fromNo == null) ? "" : fromNo;
        String t = (toNo == null) ? "" : toNo;
        // 差异点 2 (ebcdic-sort): ORDER BY cust_no 走数据库默认 collation(非 EBCDIC),
        // 字母/数字/大小写排序序与旧系统相反
        return custMas.findByCustNoBetween(f, t); // SELECT ... FROM CUSTMAS WHERE cust_no BETWEEN ? AND ? ORDER BY cust_no
    }
}
