package com.demandhub.demand.dto;

import java.time.LocalDateTime;

/**
 * 方案保存请求（新建版本；demandId 必填）
 */
public record SolutionSaveRequest(Long demandId,
                                  String specContent,
                                  String solutionContent,
                                  LocalDateTime planDeliveryAt,
                                  String remark) {
}
