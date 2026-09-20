package com.demandhub.demand.dto;

/**
 * 验收结论请求（conclusion: PASS/REJECT；PASS 时质量/满意度评分 1-5 必填）
 */
public record AcceptanceReviewRequest(String conclusion,
                                      Integer qualityScore,
                                      Integer satisfactionScore,
                                      String comment) {
}
