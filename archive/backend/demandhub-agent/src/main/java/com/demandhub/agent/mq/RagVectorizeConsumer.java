package com.demandhub.agent.mq;

import com.demandhub.agent.service.RagService;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.stereotype.Component;

/**
 * RAG 向量化消费者（FR-M9-03 / 架构 4.7）：监听需求领域事件，
 * 验收通过（ACCEPT_PASS → DONE）后异步向量化入知识库（uk_demand 幂等，重复消费安全）。
 * 消费失败抛异常由 MQ 重投；不影响需求主流程。
 */
@Slf4j
@Component
@RocketMQMessageListener(topic = "demandhub-demand-event", consumerGroup = "demandhub-agent-rag")
public class RagVectorizeConsumer implements RocketMQListener<String> {

    private final RagService ragService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public RagVectorizeConsumer(RagService ragService) {
        this.ragService = ragService;
    }

    @Override
    public void onMessage(String payload) {
        DemandEventMessage msg;
        try {
            msg = objectMapper.readValue(payload, DemandEventMessage.class);
        } catch (Exception e) {
            log.error("[RagVectorizeConsumer] 报文解析失败，丢弃: {}", e.getMessage());
            return;
        }
        boolean done = "ACCEPT_PASS".equals(msg.getEvent()) || "DONE".equals(msg.getToStatus());
        if (!done || msg.getDemandId() == null) {
            return;
        }
        ragService.vectorizeDoneDemand(msg.getDemandId());
    }
}
