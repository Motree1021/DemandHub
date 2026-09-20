package com.demandhub.system.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.system.integration.pcenter.PermissionCenterClient;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 一期 Mock 辅助接口：模拟权限中心数据变更（验证增量同步与数据范围联动）。
 * 二期对接真实权限中心后删除。
 */
@Tag(name = "Mock 辅助（一期）")
@RestController
@RequestMapping("/system/mock/pcenter")
public class MockPcenterController {

    private final PermissionCenterClient pcenterClient;

    public MockPcenterController(PermissionCenterClient pcenterClient) {
        this.pcenterClient = pcenterClient;
    }

    @Operation(summary = "模拟用户调岗（随后增量同步生效，≤5 分钟）")
    @RequireRole("ADMIN")
    @PostMapping("/move-user")
    public Result<Void> moveUser(@RequestParam String userId, @RequestParam Long orgId) {
        pcenterClient.simulateUserMove(userId, orgId);
        return Result.ok();
    }
}
