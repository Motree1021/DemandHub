package com.demandhub.demand.dto;

/**
 * 关闭请求（原因必填；重复关闭可关联原需求）
 */
public record CloseRequest(String reason, Long duplicateOfId) {
}
