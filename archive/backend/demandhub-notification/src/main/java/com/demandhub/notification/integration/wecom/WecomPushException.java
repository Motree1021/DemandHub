package com.demandhub.notification.integration.wecom;

/**
 * 企微推送异常：触发 MQ 重试（指数退避，最多 5 次）。
 */
public class WecomPushException extends RuntimeException {

    public WecomPushException(String message) {
        super(message);
    }
}
