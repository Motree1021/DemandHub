package com.demandhub.system.service;

import com.demandhub.system.entity.UserSnapshot;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.io.Serializable;
import java.time.Duration;
import java.util.List;
import java.util.Set;

/**
 * Redis 会话存储：access 会话按 JWT jti 存取（网关鉴权时校验存在性，支持登出即失效）；
 * refresh 会话同样按 jti 存取并维护 user→jti 索引，refresh 旋转/登出/按用户全清一并失效。
 */
@Slf4j
@Service
public class SessionService {

    private static final String SESSION_KEY = "auth:session:";
    private static final String REFRESH_KEY = "auth:refresh:";
    private static final String USER_SESSIONS_KEY = "auth:user-sessions:";
    private static final String USER_REFRESH_KEY = "auth:user-refresh:";

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public SessionService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveSession(String jti, SessionUser user, long ttlSeconds) {
        redis.opsForValue().set(SESSION_KEY + jti, toJson(user), Duration.ofSeconds(ttlSeconds));
        // 维护 user -> jti 索引，授权变更时按用户失效会话（FR-M1-03：调整授权后 1 分钟内生效）
        String indexKey = USER_SESSIONS_KEY + user.getUserId();
        redis.opsForSet().add(indexKey, jti);
        redis.expire(indexKey, Duration.ofDays(7));
    }

    public SessionUser getSession(String jti) {
        String json = redis.opsForValue().get(SESSION_KEY + jti);
        if (json == null) {
            return null;
        }
        try {
            return objectMapper.readValue(json, SessionUser.class);
        } catch (JsonProcessingException e) {
            log.warn("会话反序列化失败: {}", e.getMessage());
            return null;
        }
    }

    public void deleteSession(String jti) {
        redis.delete(SESSION_KEY + jti);
    }

    /**
     * 使指定用户 access 会话失效（保留 refresh）。
     * 用于授权变更（FR-M1-03）：access 立即失效，用户凭 refresh 自动续期获取新角色，实现无感生效。
     */
    public void deleteSessionsByUser(String userId) {
        String indexKey = USER_SESSIONS_KEY + userId;
        Set<String> jtis = redis.opsForSet().members(indexKey);
        if (jtis != null) {
            jtis.forEach(jti -> redis.delete(SESSION_KEY + jti));
        }
        redis.delete(indexKey);
    }

    /**
     * 使指定用户全部会话失效（access + refresh 一并清除）。
     * 用于改密/停用/合并等必须强制重新登录的场景。
     */
    public void deleteAllSessionsByUser(String userId) {
        deleteSessionsByUser(userId);

        String refreshIndexKey = USER_REFRESH_KEY + userId;
        Set<String> refreshJtis = redis.opsForSet().members(refreshIndexKey);
        if (refreshJtis != null) {
            refreshJtis.forEach(jti -> redis.delete(REFRESH_KEY + jti));
        }
        redis.delete(refreshIndexKey);
    }

    public void saveRefresh(String jti, String userId, long ttlSeconds) {
        redis.opsForValue().set(REFRESH_KEY + jti, userId, Duration.ofSeconds(ttlSeconds));
        String indexKey = USER_REFRESH_KEY + userId;
        redis.opsForSet().add(indexKey, jti);
        redis.expire(indexKey, Duration.ofDays(7));
    }

    public boolean refreshExists(String jti) {
        return Boolean.TRUE.equals(redis.hasKey(REFRESH_KEY + jti));
    }

    public void deleteRefresh(String jti) {
        redis.delete(REFRESH_KEY + jti);
    }

    private String toJson(SessionUser user) {
        try {
            return objectMapper.writeValueAsString(user);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("会话序列化失败", e);
        }
    }

    /**
     * 会话中的用户快照（登录时写入；角色授权变更后由授权接口刷新，保证 1 分钟内生效）
     */
    @Data
    public static class SessionUser implements Serializable {
        private Long id;
        private String userId;
        private String name;
        private Long primaryOrgId;
        private List<String> roles;
        /** 登录渠道（WEB/CHUANGJIN_LS），网关注入 X-Channel */
        private String channel;

        public static SessionUser of(UserSnapshot u, List<String> roles, String channel) {
            SessionUser su = new SessionUser();
            su.setId(u.getId());
            su.setUserId(u.getUserId());
            su.setName(u.getName());
            su.setPrimaryOrgId(u.getPrimaryOrgId());
            su.setRoles(roles);
            su.setChannel(channel);
            return su;
        }
    }
}
