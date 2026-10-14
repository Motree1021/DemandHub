package com.demandhub.gateway.filter;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 网关统一鉴权（NFR-07/08）：
 * 1. 白名单（登录类/文档/健康检查）放行；
 * 2. 校验 JWT 签名与有效期，并校验 Redis 会话存在（登出/授权变更后即失效）；
 * 3. 注入 X-User-Id / X-User-Uid / X-User-Roles / X-Channel 用户头转发下游；先剥离客户端伪造头。
 */
@Slf4j
@Component
public class AuthFilter implements GlobalFilter, Ordered {

    private static final String SESSION_KEY = "auth:session:";
    private static final String HEADER_USER_ID = "X-User-Id";
    private static final String HEADER_USER_UID = "X-User-Uid";
    private static final String HEADER_USER_ROLES = "X-User-Roles";
    private static final String HEADER_CHANNEL = "X-Channel";
    private static final String DEFAULT_CHANNEL = "WEB";

    /** 登录类白名单（前缀匹配）：渠道SSO/账密登录/刷新/登出/Mock入口（仅dev） */
    private static final List<String> WHITELIST_PREFIX = List.of(
            "/api/system/auth/channel-sso",
            "/api/system/auth/login",
            "/api/system/auth/refresh",
            "/api/system/auth/logout",
            "/api/system/mock-sso"
    );
    /** 文档与健康检查（包含匹配） */
    private static final List<String> WHITELIST_CONTAINS = List.of(
            "/ping", "/doc.html", "/v3/api-docs", "/swagger", "/webjars", "/favicon.ico"
    );

    private final SecretKey key;
    private final ReactiveStringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public AuthFilter(@Value("${demandhub.auth.jwt-secret}") String jwtSecret,
                      ReactiveStringRedisTemplate redis) {
        this.key = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
        this.redis = redis;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        ServerHttpRequest request = exchange.getRequest();
        String path = request.getPath().value();

        // 剥离客户端伪造的用户头，只信任本网关注入
        ServerHttpRequest sanitized = request.mutate()
                .headers(h -> {
                    h.remove(HEADER_USER_ID);
                    h.remove(HEADER_USER_UID);
                    h.remove(HEADER_USER_ROLES);
                    h.remove(HEADER_CHANNEL);
                })
                .build();

        if (isWhitelisted(path)) {
            return chain.filter(exchange.mutate().request(sanitized).build());
        }

        String authorization = request.getHeaders().getFirst("Authorization");
        if (!StringUtils.hasText(authorization) || !authorization.startsWith("Bearer ")) {
            return unauthorized(exchange, "未登录或登录已过期");
        }
        Claims claims = parse(authorization.substring(7));
        if (claims == null || !"access".equals(claims.get("typ"))) {
            return unauthorized(exchange, "未登录或登录已过期");
        }

        // 会话必须存在于 Redis（登出/授权变更后立即失效）
        return redis.hasKey(SESSION_KEY + claims.getId()).flatMap(exists -> {
            if (!Boolean.TRUE.equals(exists)) {
                return unauthorized(exchange, "会话已失效，请重新登录");
            }
            List<?> roles = claims.get("roles", List.class);
            Object channel = claims.get("channel");
            ServerHttpRequest authed = sanitized.mutate()
                    .header(HEADER_USER_ID, String.valueOf(claims.get("uid")))
                    .header(HEADER_USER_UID, String.valueOf(claims.get("userId")))
                    .header(HEADER_USER_ROLES, roles == null ? "" : String.join(",", roles.stream().map(String::valueOf).toList()))
                    .header(HEADER_CHANNEL, channel == null ? DEFAULT_CHANNEL : String.valueOf(channel))
                    .build();
            return chain.filter(exchange.mutate().request(authed).build());
        });
    }

    private boolean isWhitelisted(String path) {
        if (WHITELIST_PREFIX.stream().anyMatch(path::startsWith)) {
            return true;
        }
        return WHITELIST_CONTAINS.stream().anyMatch(path::contains);
    }

    private Claims parse(String token) {
        try {
            return Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
        } catch (JwtException | IllegalArgumentException e) {
            return null;
        }
    }

    private Mono<Void> unauthorized(ServerWebExchange exchange, String message) {
        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        byte[] bytes;
        try {
            bytes = objectMapper.writeValueAsBytes(Map.of("code", 401, "message", message));
        } catch (Exception e) {
            bytes = ("{\"code\":401,\"message\":\"" + message + "\"}").getBytes(StandardCharsets.UTF_8);
        }
        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }

    @Override
    public int getOrder() {
        return -100;
    }
}
