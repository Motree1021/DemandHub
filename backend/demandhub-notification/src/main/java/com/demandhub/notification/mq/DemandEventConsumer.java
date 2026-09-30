package com.demandhub.notification.mq;

import com.demandhub.notification.entity.UserSnapshotView;
import com.demandhub.notification.mapper.NotificationUserSnapshotViewMapper;
import com.demandhub.notification.service.NotificationService;
import com.demandhub.notification.service.NotifyTypes;
import com.demandhub.notification.service.RecipientResolver;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/**
 * 需求领域事件消费者（架构 4.5）：事件 → 查模板 → 渲染变量 → 偏好过滤 → 写站内信 + 投企微推送。
 * 消费失败抛异常由 MQ 重投；业务上幂等（重复消费会产生重复通知，一期接受，二期可加去重表）。
 */
@Slf4j
@Component
@RocketMQMessageListener(topic = "demandhub-demand-event", consumerGroup = "demandhub-notification-demand-event")
public class DemandEventConsumer implements RocketMQListener<String> {

    /** 事件 → 通知类型（模板编码 = 事件名） */
    private static final Map<String, String> EVENT_NOTIFY_TYPE = Map.ofEntries(
            Map.entry("SUBMIT", NotifyTypes.TODO),
            Map.entry("WITHDRAW", NotifyTypes.STATUS_CHANGE),
            Map.entry("ACCEPT", NotifyTypes.STATUS_CHANGE),
            Map.entry("RETURN", NotifyTypes.TODO),
            Map.entry("CLOSE", NotifyTypes.STATUS_CHANGE),
            Map.entry("ASSIGN", NotifyTypes.ASSIGN),
            Map.entry("CLAIM", NotifyTypes.STATUS_CHANGE),
            Map.entry("SUBMIT_REVIEW", NotifyTypes.REVIEW_REQUEST),
            Map.entry("REVIEW_PASS", NotifyTypes.STATUS_CHANGE),
            Map.entry("REVIEW_REJECT", NotifyTypes.TODO),
            Map.entry("START", NotifyTypes.STATUS_CHANGE),
            Map.entry("SUBMIT_ACCEPTANCE", NotifyTypes.ACCEPTANCE_REQUEST),
            Map.entry("ACCEPT_PASS", NotifyTypes.STATUS_CHANGE),
            Map.entry("ACCEPT_REJECT", NotifyTypes.TODO),
            Map.entry("CHANGE_TYPE", NotifyTypes.STATUS_CHANGE),
            Map.entry("HOLD", NotifyTypes.STATUS_CHANGE),
            Map.entry("RESUME", NotifyTypes.STATUS_CHANGE),
            Map.entry("SLA_ALERT", NotifyTypes.SLA_ALERT));

    private final RecipientResolver recipientResolver;
    private final NotificationService notificationService;
    private final NotificationUserSnapshotViewMapper userSnapshotMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DemandEventConsumer(RecipientResolver recipientResolver, NotificationService notificationService,
                               NotificationUserSnapshotViewMapper userSnapshotMapper) {
        this.recipientResolver = recipientResolver;
        this.notificationService = notificationService;
        this.userSnapshotMapper = userSnapshotMapper;
    }

    @Override
    public void onMessage(String payload) {
        DemandEventMessage msg;
        try {
            msg = objectMapper.readValue(payload, DemandEventMessage.class);
        } catch (Exception e) {
            log.error("[DemandEventConsumer] 报文解析失败，丢弃: {}", e.getMessage());
            return;
        }
        String notifyType = EVENT_NOTIFY_TYPE.get(msg.getEvent());
        if (notifyType == null) {
            log.warn("[DemandEventConsumer] 未知事件类型，跳过: {}", msg.getEvent());
            return;
        }
        Set<Long> receivers = recipientResolver.resolve(msg);
        if (receivers.isEmpty()) {
            log.info("[DemandEventConsumer] 无接收人，跳过: {} {}", msg.getEvent(), msg.getDemandNo());
            return;
        }
        int sent = notificationService.sendToReceivers(msg.getDemandId(), msg.getEvent(), notifyType,
                receivers, buildVars(msg));
        log.info("[DemandEventConsumer] 事件 {} {} → 通知 {} 人", msg.getEvent(), msg.getDemandNo(), sent);
    }

    /** 模板变量：编号/标题/操作人/源目标状态/意见/链接 + extra 透传（from_type/to_type/level_text/elapsed_minutes 等） */
    private Map<String, Object> buildVars(DemandEventMessage msg) {
        Map<String, Object> vars = new HashMap<>();
        vars.put("demand_no", nullToEmpty(msg.getDemandNo()));
        vars.put("title", nullToEmpty(msg.getTitle()));
        vars.put("operator_name", operatorName(msg.getOperatorId()));
        vars.put("from_status", nullToEmpty(msg.getFromStatus()));
        vars.put("to_status", nullToEmpty(msg.getToStatus()));
        vars.put("comment", nullToEmpty(msg.getComment()));
        if (msg.getExtra() != null) {
            msg.getExtra().forEach((k, v) -> vars.put(snake(k), v == null ? "" : v));
        }
        return vars;
    }

    /** extra 的 camelCase key 转模板变量的 snake_case（如 levelText → level_text） */
    private String snake(String key) {
        return key.replaceAll("([a-z])([A-Z])", "$1_$2").toLowerCase();
    }

    private String operatorName(Long operatorId) {
        if (operatorId == null || operatorId <= 0) {
            return "系统";
        }
        UserSnapshotView user = userSnapshotMapper.selectById(operatorId);
        return user != null && user.getName() != null ? user.getName() : String.valueOf(operatorId);
    }

    private String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
