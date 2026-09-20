package com.demandhub.demand.dto;

/**
 * 提报人撤销请求（原因必填）
 */
public record WithdrawRequest(String reason) {
}
