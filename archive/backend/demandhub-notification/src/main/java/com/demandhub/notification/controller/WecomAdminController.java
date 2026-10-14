package com.demandhub.notification.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.notification.integration.wecom.MockWecomMessageClient;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 企微 Mock 控制台（一期自测工具，限 ADMIN）：
 * 热切换 Mock 发送结果（OK 成功 / FAIL 模拟 500），用于验证失败重试链路。
 */
@Tag(name = "系统管理-企微Mock")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/notification/admin/wecom")
public class WecomAdminController {

    private final MockWecomMessageClient mockWecomMessageClient;

    public WecomAdminController(MockWecomMessageClient mockWecomMessageClient) {
        this.mockWecomMessageClient = mockWecomMessageClient;
    }

    @Operation(summary = "查看 Mock 模式（OK/FAIL）")
    @GetMapping("/mock-mode")
    public Result<Map<String, String>> getMode() {
        return Result.ok(Map.of("mode", mockWecomMessageClient.getMode()));
    }

    @Operation(summary = "切换 Mock 模式（FAIL 模拟企微 500，验证重试）")
    @PutMapping("/mock-mode")
    public Result<Map<String, String>> setMode(@RequestBody Map<String, String> body) {
        String mode = body.get("mode");
        try {
            mockWecomMessageClient.setMode(mode);
        } catch (IllegalArgumentException e) {
            throw new BizException(ErrorCode.PARAM_INVALID, e.getMessage());
        }
        return Result.ok(Map.of("mode", mockWecomMessageClient.getMode()));
    }
}
