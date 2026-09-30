package com.demandhub.server.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.crypto.SecretKey;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 单体版统一鉴权（自 demandhub-gateway AuthFilter 移植，NFR-07/08）：
 * 1. 白名单（登录类/文档/健康检查）放行；
 * 2. 校验 JWT 签名与有效期，并校验 Redis 会话存在（登出/授权变更后即失效）；
 * 3. 注入 X-User-Id / X-User-Uid / X-User-Roles / X-Channel 用户头供 UserContextFilter 解析；
 *    先剥离客户端伪造头（与原网关语义一致，只信任本过滤器注入）。
 * 排序在 UserContextFilter（HIGHEST_PRECEDENCE+10）之前。
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class AuthFilter extends OncePerRequestFilter {

    private static final String SESSION_KEY = "auth:session:";
    private static final String HEADER_USER_ID = "X-User-Id";
    private static final String HEADER_USER_UID = "X-User-Uid";
    private static final String HEADER_USER_ROLES = "X-User-Roles";
    private static final String HEADER_CHANNEL = "X-Channel";
    private static final String DEFAULT_CHANNEL = "WEB";

    /** 登录类白名单（前缀匹配，URI 含 context-path /api，与原网关一致） */
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
    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public AuthFilter(@Value("${demandhub.auth.jwt-secret}") String jwtSecret,
                      StringRedisTemplate redis) {
        this.key = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
        this.redis = redis;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String path = request.getRequestURI();

        if (isWhitelisted(path)) {
            chain.doFilter(stripUserHeaders(request), response);
            return;
        }

        String authorization = request.getHeader("Authorization");
        if (!StringUtils.hasText(authorization) || !authorization.startsWith("Bearer ")) {
            unauthorized(response, "未登录或登录已过期");
            return;
        }
        Claims claims = parse(authorization.substring(7));
        if (claims == null || !"access".equals(claims.get("typ"))) {
            unauthorized(response, "未登录或登录已过期");
            return;
        }

        // 会话必须存在于 Redis（登出/授权变更后立即失效）
        if (!Boolean.TRUE.equals(redis.hasKey(SESSION_KEY + claims.getId()))) {
            unauthorized(response, "会话已失效，请重新登录");
            return;
        }

        List<?> roles = claims.get("roles", List.class);
        Object channel = claims.get("channel");
        Map<String, String> inject = new HashMap<>();
        inject.put(HEADER_USER_ID, String.valueOf(claims.get("uid")));
        inject.put(HEADER_USER_UID, String.valueOf(claims.get("userId")));
        inject.put(HEADER_USER_ROLES, roles == null ? "" : String.join(",", roles.stream().map(String::valueOf).toList()));
        inject.put(HEADER_CHANNEL, channel == null ? DEFAULT_CHANNEL : String.valueOf(channel));
        chain.doFilter(new HeaderMutatingRequest(request, inject), response);
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

    private void unauthorized(HttpServletResponse response, String message) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(objectMapper.writeValueAsString(Map.of("code", 401, "message", message)));
    }

    /** 仅剥离四个用户头（白名单路径） */
    private HttpServletRequest stripUserHeaders(HttpServletRequest request) {
        return new HeaderMutatingRequest(request, Map.of());
    }

    /** 请求头改写包装器：先移除全部用户头，再叠加注入值（防客户端伪造） */
    private static class HeaderMutatingRequest extends HttpServletRequestWrapper {

        private static final Set<String> USER_HEADERS = Set.of(
                HEADER_USER_ID.toLowerCase(), HEADER_USER_UID.toLowerCase(),
                HEADER_USER_ROLES.toLowerCase(), HEADER_CHANNEL.toLowerCase());

        private final Map<String, String> injected;

        HeaderMutatingRequest(HttpServletRequest request, Map<String, String> injected) {
            super(request);
            this.injected = injected;
        }

        @Override
        public String getHeader(String name) {
            String lower = name.toLowerCase();
            for (Map.Entry<String, String> e : injected.entrySet()) {
                if (e.getKey().equalsIgnoreCase(name)) {
                    return e.getValue();
                }
            }
            if (USER_HEADERS.contains(lower)) {
                return null;
            }
            return super.getHeader(name);
        }

        @Override
        public Enumeration<String> getHeaders(String name) {
            String value = getHeader(name);
            return value == null ? Collections.emptyEnumeration() : Collections.enumeration(List.of(value));
        }

        @Override
        public Enumeration<String> getHeaderNames() {
            Set<String> names = new HashSet<>();
            Enumeration<String> original = super.getHeaderNames();
            while (original != null && original.hasMoreElements()) {
                String name = original.nextElement();
                if (!USER_HEADERS.contains(name.toLowerCase())) {
                    names.add(name);
                }
            }
            names.addAll(injected.keySet());
            return Collections.enumeration(names);
        }
    }
}
