package com.demandhub.demand.dto;

/**
 * 经理受理 / 退回补充请求（退回时 comment 必填）
 */
public record TriageActionRequest(String comment) {
}
