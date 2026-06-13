package com.example.order;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * DiscountService - 计算订单折扣并写回 ORDHDR (样例,非真实生产码)
 * 对应 AS400 程序 CALCDISC。
 * 注意:此处故意埋了两个对等性差异,供脚手架演示。
 */
public class DiscountService {

    @Table(name = "ORDHDR")
    private OrderHeaderRepo ordHdr;

    @Table(name = "CUSTMAS")
    private CustomerRepo custMas;

    public void calcDiscount(String custNo, OrderHeader ord) {
        Customer c = custMas.findById(custNo);
        // 差异点 1 (logical-delete): 没有过滤 DEL_STS='D',逻辑已删客户也会算折扣
        if (c != null) {
            BigDecimal pct = c.getCustDisc();
            // 差异点 2 (packed-zoned-precision): 用 HALF_EVEN(银行家舍入),
            // 与 AS400 half-adjust(HALF_UP) 不一致
            BigDecimal discAmt = ord.getOrdAmt()
                    .multiply(pct)
                    .divide(new BigDecimal("100"), 2, RoundingMode.HALF_EVEN);
            ord.setDiscAmt(discAmt);
            ordHdr.update(ord);
        }
    }
}
