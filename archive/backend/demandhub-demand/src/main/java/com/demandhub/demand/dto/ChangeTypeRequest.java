package com.demandhub.demand.dto;

/**
 * 类型修正请求（仅 EXECUTIVE；修正后重新路由）
 */
public record ChangeTypeRequest(String newTypeCode, String comment) {
}
