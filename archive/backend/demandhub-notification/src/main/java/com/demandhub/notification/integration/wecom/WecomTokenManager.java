package com.demandhub.notification.integration.wecom;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 企微 access_token 集中管理（一期 Mock）：
 * 缓存 + 过期自动刷新（Mock 有效期 7000s，与真实企微一致）；二期替换为真实 gettoken 接口。
 */
@Slf4j
@Component
public class WecomTokenManager {

    /** Mock token 有效期（秒），与真实企微 7200s 对齐并留提前量 */
    private static final long TOKEN_TTL_SECONDS = 7000;

    private final AtomicReference<String> cachedToken = new AtomicReference<>();
    private final AtomicReference<Instant> expiresAt = new AtomicReference<>(Instant.EPOCH);

    public synchronized String getAccessToken() {
        if (cachedToken.get() != null && Instant.now().isBefore(expiresAt.get())) {
            return cachedToken.get();
        }
        String token = "mock-wecom-token-" + UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        cachedToken.set(token);
        expiresAt.set(Instant.now().plusSeconds(TOKEN_TTL_SECONDS));
        log.info("[WecomToken] access_token 已刷新（Mock），有效期 {}s", TOKEN_TTL_SECONDS);
        return token;
    }
}
