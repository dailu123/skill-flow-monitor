      *--------------------------------------------------------------
      * CALCDISC - 计算订单折扣并写回 ORDHDR (样例,非真实生产码)
      * 缺陷类演示: packed-zoned-precision / logical-delete
      *--------------------------------------------------------------
     H DFTACTGRP(*NO)

     FORDHDR    UF   E           K DISK
     FCUSTMAS   IF   E           K DISK

      * 字段: ORD_AMT  packed(9,2)  订单金额
      *       DISC_PCT packed(5,2)  折扣率(百分比)
      *       DISC_AMT packed(9,2)  折扣金额
      *       DEL_STS  char(1)      逻辑删除标记 'D'=已删

     D discAmt         S              9P 2
     D pct             S              5P 2

      /free
        // 只处理未被逻辑删除的客户
        chain custNo CUSTMAS;
        if %found(CUSTMAS) and DEL_STS <> 'D';
           pct = CUST_DISC;
           // half-adjust: 四舍五入到 2 位小数
           discAmt = ORD_AMT * pct / 100;
           DISC_AMT = discAmt;          // packed(9,2),half-adjust 截到 2 位
           update ORDHDRR;
        endif;
        return;
      /end-free
