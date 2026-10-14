package com.demandhub.common.context;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Arrays;

/**
 * 解析网关注入的用户头（X-User-Id / X-User-Uid / X-User-Roles / X-Channel）构建 UserContext。
 * 网关在转发前已剥离客户端伪造头，业务服务只信任本网关内网调用。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class UserContextFilter extends OncePerRequestFilter {

    public static final String HEADER_USER_ID = "X-User-Id";
    public static final String HEADER_USER_UID = "X-User-Uid";
    public static final String HEADER_USER_ROLES = "X-User-Roles";
    public static final String HEADER_CHANNEL = "X-Channel";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        try {
            String userId = request.getHeader(HEADER_USER_ID);
            if (StringUtils.hasText(userId)) {
                CurrentUser user = new CurrentUser();
                user.setId(Long.parseLong(userId));
                user.setUserId(request.getHeader(HEADER_USER_UID));
                String roles = request.getHeader(HEADER_USER_ROLES);
                if (StringUtils.hasText(roles)) {
                    user.setRoles(Arrays.asList(roles.split(",")));
                }
                user.setChannel(request.getHeader(HEADER_CHANNEL));
                UserContext.set(user);
            }
            chain.doFilter(request, response);
        } finally {
            UserContext.clear();
        }
    }
}
