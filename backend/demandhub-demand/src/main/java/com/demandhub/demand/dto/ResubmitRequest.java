package com.demandhub.demand.dto;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 退回补充后重新提交请求（字段均为可选，仅更新提供的字段）
 */
public record ResubmitRequest(String title,
                              String content,
                              String urgency,
                              LocalDateTime expectDeliveryAt,
                              Map<String, Object> ext,
                              List<Long> attachmentIds) {
}
