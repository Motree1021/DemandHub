package com.demandhub.notification.integration.wecom;

/**
 * 企微应用消息客户端（一期 Mock：{@link MockWecomMessageClient}；二期切换真实企微 API）。
 * 推送失败抛 {@link WecomPushException}。
 */
public interface WecomMessageClient {

    /** 文本消息 */
    void sendText(String toUser, String content);

    /** 卡片消息（标题 + 摘要 + 直达链接） */
    void sendCard(String toUser, String title, String description, String url);
}
