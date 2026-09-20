package com.demandhub.demand.dto;

/**
 * 草稿保存请求（id 为空新建，否则更新；formPayload 为表单 JSON 字符串）
 */
public record DraftSaveRequest(Long id, String channel, String formPayload) {
}
