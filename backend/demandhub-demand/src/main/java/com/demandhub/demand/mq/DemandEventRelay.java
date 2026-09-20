package com.demandhub.demand.mq;

import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.statemachine.DemandTransitionEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.core.RocketMQTemplate;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 领域事件转发器（架构 4.5）：状态机流转 Spring 事件 → RocketMQ → 通知服务消费。
 * 事务提交后才发送，避免"通知先于数据可见"；发送失败只告警不回流，保证主流程不阻塞。
 */
@Slf4j
@Component
public class DemandEventRelay {

    private final RocketMQTemplate rocketMQTemplate;
    private final DemandMapper demandMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DemandEventRelay(RocketMQTemplate rocketMQTemplate, DemandMapper demandMapper) {
        this.rocketMQTemplate = rocketMQTemplate;
        this.demandMapper = demandMapper;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onTransition(DemandTransitionEvent event) {
        try {
            DemandEventMessage message = buildMessage(event);
            rocketMQTemplate.syncSend(MqTopics.DEMAND_EVENT_TOPIC,
                    MessageBuilder.withPayload(objectMapper.writeValueAsString(message)).build());
        } catch (Exception e) {
            // MQ 抖动不阻断主流程；告警后由运维介入（一期可接受，二期可做本地消息表补偿）
            log.error("[DemandEventRelay] 需求事件转发 MQ 失败: demandId={}, event={}, err={}",
                    event.getDemandId(), event.getEvent(), e.getMessage());
        }
    }

    private DemandEventMessage buildMessage(DemandTransitionEvent event) {
        DemandEventMessage message = new DemandEventMessage();
        message.setDemandId(event.getDemandId());
        message.setDemandNo(event.getDemandNo());
        message.setEvent(event.getEvent());
        message.setFromStatus(event.getFromStatus());
        message.setToStatus(event.getToStatus());
        message.setOperatorId(event.getOperatorId());
        message.setComment(event.getComment());
        message.setExtra(event.getExtra());
        DemandEntity demand = demandMapper.selectById(event.getDemandId());
        if (demand != null) {
            message.setTitle(demand.getTitle());
            message.setDemandTypeCode(demand.getDemandTypeCode());
            message.setSubmitterId(demand.getSubmitterId());
            message.setActualDemanderId(demand.getActualDemanderId());
            message.setAssigneeOrgId(demand.getAssigneeOrgId());
            message.setAssigneeUserId(demand.getAssigneeUserId());
        }
        return message;
    }
}
