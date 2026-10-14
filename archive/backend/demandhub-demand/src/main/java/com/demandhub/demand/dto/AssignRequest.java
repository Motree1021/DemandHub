package com.demandhub.demand.dto;

/**
 * 经理分派请求
 */
public record AssignRequest(Long assigneeId, String comment) {
}
