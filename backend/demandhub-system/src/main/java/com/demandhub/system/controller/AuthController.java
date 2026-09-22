package com.demandhub.system.controller;

import com.demandhub.common.core.Result;
import com.demandhub.system.dto.ChangePasswordRequest;
import com.demandhub.system.dto.LoginRequest;
import com.demandhub.system.dto.LoginResponse;
import com.demandhub.system.dto.RefreshRequest;
import com.demandhub.system.dto.UserInfoVO;
import com.demandhub.system.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 认证接口（FR-M1-01，渠道接入版 P2）：
 * 渠道 SSO 票据登录、PC 账密登录、改密、刷新、登出、当前用户。
 */
@Tag(name = "认证")
@Validated
@RestController
@RequestMapping("/system/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @Operation(summary = "渠道 SSO 票据登录（一次性票据回源校验后发 JWT）")
    @GetMapping("/channel-sso")
    public Result<LoginResponse> channelSso(@RequestParam String channel,
                                            @RequestParam String ticket,
                                            @RequestParam(required = false) String state) {
        // state：入口跳转方带入的随机串，原样记录用于链路追踪（对接标准 §3.1；防重放由票据一次性+verify nonce 保证）
        return Result.ok(authService.channelSso(channel, ticket, state));
    }

    @Operation(summary = "PC 账密登录（BCrypt；连续失败 5 次锁 15 分钟；首登强制改密）")
    @PostMapping("/login")
    public Result<LoginResponse> login(@Valid @RequestBody LoginRequest request,
                                       HttpServletRequest httpRequest) {
        return Result.ok(authService.login(request.getLoginName(), request.getPassword(),
                clientIp(httpRequest)));
    }

    @Operation(summary = "修改密码（强制改密/自助改密；改密后全清会话）")
    @PostMapping("/change-password")
    public Result<Void> changePassword(@Valid @RequestBody ChangePasswordRequest request) {
        authService.changePassword(request.getOldPassword(), request.getNewPassword());
        return Result.ok();
    }

    @Operation(summary = "刷新访问令牌（旋转：旧 refresh 即作废）")
    @PostMapping("/refresh")
    public Result<LoginResponse> refresh(@Valid @RequestBody RefreshRequest request) {
        return Result.ok(authService.refresh(request.getRefreshToken()));
    }

    @Operation(summary = "登出")
    @PostMapping("/logout")
    public Result<Void> logout(@RequestHeader(value = "Authorization", required = false) String authorization,
                               @RequestParam(required = false) String refreshToken) {
        String accessToken = authorization != null && authorization.startsWith("Bearer ")
                ? authorization.substring(7) : null;
        authService.logout(accessToken, refreshToken);
        return Result.ok();
    }

    @Operation(summary = "当前登录用户信息")
    @GetMapping("/me")
    public Result<UserInfoVO> me() {
        return Result.ok(authService.me());
    }

    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (forwarded != null && !forwarded.isBlank()) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
