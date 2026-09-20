package com.demandhub.notification.mq;

import com.demandhub.notification.entity.NotificationEntity;
import com.demandhub.notification.entity.UserSnapshotView;
import com.demandhub.notification.integration.wecom.WecomMessageClient;
import com.demandhub.notification.integration.wecom.WecomPushException;
import com.demandhub.notification.mapper.NotificationMapper;
import com.demandhub.notification.mapper.UserSnapshotViewMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

/**
 * 企微推送消费者（架构 4.5：失败进重试队列，指数退避，最多 5 次，最终失败告警运维）。
 * 重试通过延迟消息实现：第 n 次失败以延迟等级 n 重投（1s/5s/10s/30s/1m），retry_count 落库。
 */
@Slf4j
@Component
@RocketMQMessageListener(topic = WecomPushProducer.TOPIC, consumerGroup = "demandhub-notification-wecom-push")
public class WecomPushConsumer implements RocketMQListener<String> {

    /** 最大发送次数（首次 + 4 次重试 = 5），达到后标记 FAILED 并告警 */
    private static final int MAX_ATTEMPTS = 5;

    private final NotificationMapper notificationMapper;
    private final UserSnapshotViewMapper userSnapshotMapper;
    private final WecomMessageClient wecomMessageClient;
    private final WecomPushProducer wecomPushProducer;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public WecomPushConsumer(NotificationMapper notificationMapper, UserSnapshotViewMapper userSnapshotMapper,
                             WecomMessageClient wecomMessageClient, WecomPushProducer wecomPushProducer) {
        this.notificationMapper = notificationMapper;
        this.userSnapshotMapper = userSnapshotMapper;
        this.wecomMessageClient = wecomMessageClient;
        this.wecomPushProducer = wecomPushProducer;
    }

    @Override
    public void onMessage(String payload) {
        WecomPushMessage msg;
        try {
            msg = objectMapper.readValue(payload, WecomPushMessage.class);
        } catch (Exception e) {
            log.error("[WecomPushConsumer] 报文解析失败，丢弃: {}", e.getMessage());
            return;
        }
        NotificationEntity notification = notificationMapper.selectById(msg.getNotificationId());
        // 已终态（SENT/FAILED）直接跳过：重复投递/重试消息乱序到达时幂等
        if (notification == null || !"PENDING".equals(notification.getSendStatus())) {
            return;
        }
        try {
            push(notification);
            notification.setSendStatus("SENT");
            notification.setSentAt(LocalDateTime.now());
            notificationMapper.updateById(notification);
            log.info("[WecomPushConsumer] 企微推送成功: notificationId={}", notification.getId());
        } catch (WecomPushException e) {
            onPushFailed(notification, e);
        } catch (Exception e) {
            // 非预期异常同样走重试链路
            onPushFailed(notification, e);
        }
    }

    private void push(NotificationEntity notification) {
        UserSnapshotView receiver = userSnapshotMapper.selectById(notification.getReceiverId());
        String toUser = receiver != null && receiver.getWecomId() != null
                ? receiver.getWecomId() : String.valueOf(notification.getReceiverId());
        wecomMessageClient.sendCard(toUser, notification.getTitle(), notification.getContent(), notification.getLink());
    }

    private void onPushFailed(NotificationEntity notification, Exception e) {
        int attempts = (notification.getRetryCount() == null ? 0 : notification.getRetryCount()) + 1;
        notification.setRetryCount(attempts);
        if (attempts >= MAX_ATTEMPTS) {
            notification.setSendStatus("FAILED");
            notificationMapper.updateById(notification);
            // 最终失败告警运维（一期日志告警，二期可接告警平台）
            log.error("[WecomPushConsumer] 企微推送最终失败（已重试 {} 次）: notificationId={}, receiver={}, err={}",
                    attempts, notification.getId(), notification.getReceiverId(), e.getMessage());
            return;
        }
        notificationMapper.updateById(notification);
        // 指数退避重投：第 attempts 次失败后按延迟等级 attempts 重投（1s→5s→10s→30s→1m）
        wecomPushProducer.sendWithDelay(notification.getId(), attempts);
        log.warn("[WecomPushConsumer] 企微推送失败，第 {} 次重试已排队: notificationId={}, err={}",
                attempts, notification.getId(), e.getMessage());
    }
}
