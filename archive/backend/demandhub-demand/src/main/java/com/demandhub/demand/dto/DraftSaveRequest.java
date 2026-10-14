package com.demandhub.demand.dto;

/**
 * 草稿保存请求（id 为空新建，否则更新；formPayload 为表单 JSON 字符串）。
 * 来源渠道不从前端接收：由网关注入的 X-Channel（会话 claims）落库，伪造无效。
 */
public record DraftSaveRequest(Long id, String formPayload) {
}
