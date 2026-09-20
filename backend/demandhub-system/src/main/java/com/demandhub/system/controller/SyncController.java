package com.demandhub.system.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.system.service.MasterDataSyncService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 主数据同步手动触发（仅系统管理员）
 */
@Tag(name = "主数据同步")
@RestController
@RequestMapping("/system/sync")
public class SyncController {

    private final MasterDataSyncService syncService;

    public SyncController(MasterDataSyncService syncService) {
        this.syncService = syncService;
    }

    @Operation(summary = "手动触发同步（mode=full 全量 / incr 增量）")
    @RequireRole("ADMIN")
    @PostMapping("/trigger")
    public Result<MasterDataSyncService.SyncResult> trigger(@RequestParam(defaultValue = "incr") String mode) {
        if ("full".equalsIgnoreCase(mode)) {
            return Result.ok(syncService.fullSync());
        }
        return Result.ok(syncService.incrementalSync());
    }
}
