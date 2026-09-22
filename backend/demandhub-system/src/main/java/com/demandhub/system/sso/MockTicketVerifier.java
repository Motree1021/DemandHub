package com.demandhub.system.sso;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Mock 渠道 SSO 校验器（仅 dev：demandhub.channel-sso.mock=true）。
 * 模拟创金零售 verify 语义：票据由 {@link com.demandhub.system.controller.MockChannelSsoController}
 * 签发（Redis 存 60s、一次性消费 GETDEL），过期/重放/伪造统一返回票据无效。
 * P3 将新增创金零售真实 verify 客户端实现同一接口（HMAC 签名 + 超时熔断）。
 */
@Slf4j
@Component
@ConditionalOnProperty(name = "demandhub.channel-sso.mock", havingValue = "true", matchIfMissing = true)
public class MockTicketVerifier implements TicketVerifier {

    public static final String TICKET_KEY_PREFIX = "mock:sso:ticket:";

    private static final String GETDEL_LUA =
            "local v = redis.call('GET', KEYS[1]); if v then redis.call('DEL', KEYS[1]); end; return v";

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final DefaultRedisScript<String> getdelScript = new DefaultRedisScript<>(GETDEL_LUA, String.class);

    public MockTicketVerifier(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public SsoProfile verify(String channelCode, String ticket) {
        if (ticket == null || ticket.isBlank()) {
            throw new BizException(ErrorCode.CHANNEL_TICKET_INVALID);
        }
        // 一次性消费：取到即删（Lua 原子 GET+DEL，兼容 Redis 3.0，无 GETDEL 依赖）；重复校验/过期/伪造均取不到
        String json = redis.execute(getdelScript, List.of(TICKET_KEY_PREFIX + ticket));
        if (json == null) {
            log.warn("Mock 票据校验失败（无效/过期/重放）: channel={}", channelCode);
            throw new BizException(ErrorCode.CHANNEL_TICKET_INVALID);
        }
        try {
            return objectMapper.readValue(json, SsoProfile.class);
        } catch (Exception e) {
            log.warn("Mock 票据反序列化失败: {}", e.getMessage());
            throw new BizException(ErrorCode.CHANNEL_TICKET_INVALID);
        }
    }
}
