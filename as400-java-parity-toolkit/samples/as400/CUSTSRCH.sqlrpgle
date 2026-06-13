      *--------------------------------------------------------------
      * CUSTSRCH - 按客户编号范围检索客户 (样例,非真实生产码)
      * 缺陷类演示: ebcdic-sort / dynamic-query-condition-range
      *--------------------------------------------------------------
     H DFTACTGRP(*NO)

     FCUSTMAS   IF   E           K DISK

      * 字段: CUST_NO  char(8)   客户编号(可含字母+数字)
      *       CUST_NM  char(30)  客户名

     D fromNo          S              8A
     D toNo            S              8A

      /free
        // 范围检索: from..to 闭区间; 空 from 表示从最小键开始
        if fromNo = *BLANKS;
           fromNo = *LOVAL;            // figurative constant 作下界哨兵
        endif;
        if toNo = *BLANKS;
           toNo = *HIVAL;              // figurative constant 作上界哨兵
        endif;
        // SETLL/READE 按 EBCDIC 排序序扫描,闭区间含端点
        exec sql
          declare c1 cursor for
            select CUST_NO, CUST_NM from CUSTMAS
             where CUST_NO between :fromNo and :toNo
             order by CUST_NO;
        // ... fetch loop omitted ...
        return;
      /end-free
