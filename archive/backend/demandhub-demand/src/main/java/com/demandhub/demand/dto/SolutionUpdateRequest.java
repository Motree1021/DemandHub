package com.demandhub.demand.dto;

import java.time.LocalDateTime;

/**
 * 方案草稿更新请求（仅作者、仅 DRAFT 状态）
 */
public record SolutionUpdateRequest(String specContent,
                                    String solutionContent,
                                    LocalDateTime planDeliveryAt,
                                    String remark) {
}
