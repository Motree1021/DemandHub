package com.demandhub.demand.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.demand.entity.SlaConfigEntity;
import com.demandhub.demand.service.SlaConfigService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * M8 SLA 配置管理（限 ADMIN）：按 类型 × 状态 配置最长停留时长（分钟）。
 */
@Tag(name = "系统管理-SLA配置")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/demand/admin/sla-configs")
public class SlaConfigAdminController {

    private final SlaConfigService slaConfigService;

    public SlaConfigAdminController(SlaConfigService slaConfigService) {
        this.slaConfigService = slaConfigService;
    }

    @Operation(summary = "SLA 配置列表（可按类型过滤）")
    @GetMapping
    public Result<List<SlaConfigEntity>> list(@RequestParam(required = false) String demandTypeCode) {
        return Result.ok(slaConfigService.list(demandTypeCode));
    }

    @Operation(summary = "新增 SLA 配置（类型 × 状态唯一，预警阈值 < 告警阈值）")
    @PostMapping
    public Result<SlaConfigEntity> create(@RequestBody SlaConfigEntity request) {
        return Result.ok(slaConfigService.create(request));
    }

    @Operation(summary = "编辑 SLA 配置")
    @PutMapping("/{id}")
    public Result<SlaConfigEntity> update(@PathVariable Long id, @RequestBody SlaConfigEntity request) {
        return Result.ok(slaConfigService.update(id, request));
    }

    @Operation(summary = "删除 SLA 配置")
    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable Long id) {
        slaConfigService.delete(id);
        return Result.ok();
    }
}
