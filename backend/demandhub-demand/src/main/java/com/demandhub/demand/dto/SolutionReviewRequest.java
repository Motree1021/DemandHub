package com.demandhub.demand.dto;

/**
 * 方案评审请求（conclusion: PASS/REJECT；打回意见必填）
 */
public record SolutionReviewRequest(String conclusion, String comment) {
}
