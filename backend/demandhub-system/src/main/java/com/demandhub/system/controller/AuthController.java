package com.demandhub.system.controller;

import com.demandhub.common.core.Result;
import com.demandhub.system.dto.LoginResponse;
import com.demandhub.system.dto.MockUserVO;
import com.demandhub.system.dto.RefreshRequest;
import com.demandhub.system.dto.UserInfoVO;
import com.demandhub.system.integration.wecom.WecomClient;
import com.demandhub.system.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * 认证接口（FR-M1-01）：企微 OAuth 登录、H5 静默授权、刷新、登出、当前用户
 */
@Tag(name = "认证")
@Validated
@RestController
@RequestMapping("/system/auth")
public class AuthController {

    private final AuthService authService;
    private final WecomClient wecomClient;

    public AuthController(AuthService authService, WecomClient wecomClient) {
        this.authService = authService;
        this.wecomClient = wecomClient;
    }

    @Operation(summary = "获取企微 OAuth 授权链接（PC 扫码/H5 静默）")
    @GetMapping("/oauth-url")
    public Result<Map<String, String>> oauthUrl(@RequestParam(required = false) String redirectUri,
                                                @RequestParam(required = false) String state) {
        return Result.ok(Map.of("url", wecomClient.buildOAuthUrl(redirectUri, state)));
    }

    @Operation(summary = "企微回调登录（PC 扫码）")
    @GetMapping("/callback")
    public Result<LoginResponse> callback(@RequestParam String code) {
        return Result.ok(authService.loginByCode(code));
    }

    @Operation(summary = "H5 静默授权登录（企微 webview 内，支持 from=chuangjinls）")
    @GetMapping("/silent")
    public Result<LoginResponse> silent(@RequestParam String code,
                                        @RequestParam(required = false) String from) {
        return Result.ok(authService.loginByCode(code));
    }

    @Operation(summary = "刷新访问令牌")
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

    @Operation(summary = "Mock 登录用户列表（一期开发用）")
    @GetMapping("/mock-users")
    public Result<List<MockUserVO>> mockUsers() {
        return Result.ok(authService.listMockUsers());
    }
}
