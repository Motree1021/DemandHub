package com.demandhub.notification.mq;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.core.RocketMQTemplate;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

/**
 * 企微推送任务生产者：通知落库后投递，消费者异步调企微接口，失败延迟重试。
 */
@Slf4j
@Component
public class WecomPushProducer {

    public static final String TOPIC = "demandhub-wecom-push";

    private final RocketMQTemplate rocketMQTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public WecomPushProducer(RocketMQTemplate rocketMQTemplate) {
        this.rocketMQTemplate = rocketMQTemplate;
    }

    /** 立即投递 */
    public void send(Long notificationId) {
        sendWithDelay(notificationId, 0);
    }

    /**
     * 延迟投递（失败重试用）。delayLevel 对应 RocketMQ 预设延迟等级：
     * 1=1s 2=5s 3=10s 4=30s 5=1m（指数退避）。
     */
    public void sendWithDelay(Long notificationId, int delayLevel) {
        try {
            String payload = objectMapper.writeValueAsString(new WecomPushMessage(notificationId));
            if (delayLevel > 0) {
                rocketMQTemplate.syncSend(TOPIC, MessageBuilder.withPayload(payload).build(), 5000, delayLevel);
            } else {
                rocketMQTemplate.syncSend(TOPIC, MessageBuilder.withPayload(payload).build());
            }
        } catch (Exception e) {
            log.error("[WecomPushProducer] 投递失败 notificationId={}: {}", notificationId, e.getMessage());
        }
    }
}
