package com.demandhub.demand.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 工时填报请求
 */
public record EffortAddRequest(Long demandId,
                               LocalDate workDate,
                               BigDecimal hours,
                               String description) {
}
