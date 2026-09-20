package com.demandhub.system.service;

import com.demandhub.system.config.AuthProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.UUID;

/**
 * JWT 签发与解析：HS256；access token 携带用户数值 ID、权限中心 userId、角色列表。
 */
@Service
public class JwtService {

    public static final String CLAIM_UID = "uid";
    public static final String CLAIM_USER_ID = "userId";
    public static final String CLAIM_ROLES = "roles";
    public static final String CLAIM_TYPE = "typ";
    public static final String TYPE_ACCESS = "access";
    public static final String TYPE_REFRESH = "refresh";

    private final AuthProperties properties;
    private final SecretKey key;

    public JwtService(AuthProperties properties) {
        this.properties = properties;
        this.key = Keys.hmacShaKeyFor(properties.getJwtSecret().getBytes(StandardCharsets.UTF_8));
    }

    public String createAccessToken(Long uid, String userId, List<String> roles) {
        Instant now = Instant.now();
        return Jwts.builder()
                .id(UUID.randomUUID().toString())
                .subject(userId)
                .claim(CLAIM_UID, uid)
                .claim(CLAIM_USER_ID, userId)
                .claim(CLAIM_ROLES, roles)
                .claim(CLAIM_TYPE, TYPE_ACCESS)
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(Duration.ofHours(properties.getAccessTtlHours()))))
                .signWith(key)
                .compact();
    }

    public String createRefreshToken(Long uid, String userId) {
        Instant now = Instant.now();
        return Jwts.builder()
                .id(UUID.randomUUID().toString())
                .subject(userId)
                .claim(CLAIM_UID, uid)
                .claim(CLAIM_USER_ID, userId)
                .claim(CLAIM_TYPE, TYPE_REFRESH)
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(Duration.ofDays(properties.getRefreshTtlDays()))))
                .signWith(key)
                .compact();
    }

    /**
     * 解析并校验签名与有效期；失败返回 null
     */
    public Claims parse(String token) {
        try {
            return Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
        } catch (JwtException | IllegalArgumentException e) {
            return null;
        }
    }

    public long getAccessTtlSeconds() {
        return Duration.ofHours(properties.getAccessTtlHours()).getSeconds();
    }

    public long getRefreshTtlSeconds() {
        return Duration.ofDays(properties.getRefreshTtlDays()).getSeconds();
    }
}
