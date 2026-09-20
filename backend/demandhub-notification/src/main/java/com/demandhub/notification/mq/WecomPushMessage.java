package com.demandhub.notification.mq;

import lombok.Data;

import java.io.Serializable;

/**
 * 企微推送任务 MQ 报文（topic: demandhub-wecom-push）。
 * 只携带通知记录 ID，消费者回表取最新内容/状态，重试时天然幂等。
 */
@Data
public class WecomPushMessage implements Serializable {

    private Long notificationId;

    public WecomPushMessage() {
    }

    public WecomPushMessage(Long notificationId) {
        this.notificationId = notificationId;
    }
}
