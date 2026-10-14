package com.demandhub.demand.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 工时修改请求（已完成需求的历史工时不可修改）
 */
public record EffortUpdateRequest(LocalDate workDate, BigDecimal hours, String description) {
}
