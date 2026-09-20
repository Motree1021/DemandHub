package com.demandhub.notification.integration.wecom;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicReference;

/**
 * Mock 企微消息发送（一期）：
 * - 模式 OK 正常返回；FAIL 模拟企微接口 500（验证失败重试链路）；
 * - 模式可热切换（管理端接口 /notification/admin/wecom/mock-mode），无需重启。
 */
@Slf4j
@Component
public class MockWecomMessageClient implements WecomMessageClient {

    private final WecomTokenManager tokenManager;

    /** OK / FAIL */
    private final AtomicReference<String> mode;

    public MockWecomMessageClient(WecomTokenManager tokenManager,
                                  @Value("${demandhub.wecom.mock-mode:OK}") String initialMode) {
        this.tokenManager = tokenManager;
        this.mode = new AtomicReference<>(initialMode);
    }

    @Override
    public void sendText(String toUser, String content) {
        doSend(toUser, "文本", content, null);
    }

    @Override
    public void sendCard(String toUser, String title, String description, String url) {
        doSend(toUser, "卡片", title + " | " + description, url);
    }

    public String getMode() {
        return mode.get();
    }

    public void setMode(String newMode) {
        if (!"OK".equals(newMode) && !"FAIL".equals(newMode)) {
            throw new IllegalArgumentException("mode 仅支持 OK / FAIL");
        }
        mode.set(newMode);
        log.warn("[MockWecom] 企微 Mock 模式切换为 {}", newMode);
    }

    private void doSend(String toUser, String kind, String body, String url) {
        String token = tokenManager.getAccessToken();
        if ("FAIL".equals(mode.get())) {
            log.warn("[MockWecom] 模拟企微接口 500: toUser={}, kind={}", toUser, kind);
            throw new WecomPushException("Mock 企微接口返回 500（内部错误）");
        }
        log.info("[MockWecom] 企微{}消息发送成功: token={}..., toUser={}, body={}, url={}",
                kind, token.substring(0, Math.min(16, token.length())), toUser, body, url);
    }
}
