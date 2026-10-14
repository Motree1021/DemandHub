package com.demandhub.demand.dto;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 需求提交请求（M2）。ext 按类型携带扩展字段：
 * TECH: relatedSystem/relatedModule/businessScenario/acceptanceCriteria
 * MATL: materialSubtype/usageScenario/quantity/expectedArrivalAt
 * TRAIN: trainingSubtype/traineeObject/traineeCount/expectedCompleteAt
 * 来源渠道不从前端接收：由网关注入的 X-Channel（会话 claims）落库，伪造无效。
 */
public record SubmitRequest(Long draftId,
                            String title,
                            String demandTypeCode,
                            String subtypeCode,
                            String content,
                            String urgency,
                            LocalDateTime expectDeliveryAt,
                            Long actualDemanderId,
                            Map<String, Object> ext,
                            List<Long> attachmentIds) {
}
