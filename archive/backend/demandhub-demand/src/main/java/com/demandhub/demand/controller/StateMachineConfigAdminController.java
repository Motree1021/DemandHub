package com.demandhub.demand.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.demand.entity.StateMachineConfigEntity;
import com.demandhub.demand.service.StateMachineConfigService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * M8 状态机配置管理（FR-M8-02，限 ADMIN）：JSON 配置存储，保存即热加载，不重启即时生效。
 */
@Tag(name = "系统管理-状态机配置")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/demand/admin/state-machines")
public class StateMachineConfigAdminController {

    private final StateMachineConfigService configService;

    public StateMachineConfigAdminController(StateMachineConfigService configService) {
        this.configService = configService;
    }

    @Operation(summary = "配置列表")
    @GetMapping
    public Result<List<StateMachineConfigEntity>> list() {
        return Result.ok(configService.list());
    }

    @Operation(summary = "配置详情")
    @GetMapping("/{id}")
    public Result<StateMachineConfigEntity> detail(@PathVariable Long id) {
        return Result.ok(configService.requireById(id));
    }

    @Operation(summary = "导出当前生效的 DEFAULT 流转表 JSON（新建配置的起点模板）")
    @GetMapping("/default-json")
    public Result<Map<String, String>> defaultJson() {
        return Result.ok(Map.of("configJson", configService.exportDefaultJson()));
    }

    @Operation(summary = "新增配置（保存前校验 JSON 合法性，保存即生效）")
    @PostMapping
    public Result<StateMachineConfigEntity> create(@RequestBody StateMachineConfigEntity request) {
        return Result.ok(configService.create(request));
    }

    @Operation(summary = "编辑配置（保存即热加载生效）")
    @PutMapping("/{id}")
    public Result<StateMachineConfigEntity> update(@PathVariable Long id, @RequestBody StateMachineConfigEntity request) {
        return Result.ok(configService.update(id, request));
    }

    @Operation(summary = "手动触发全量热加载")
    @PostMapping("/reload")
    public Result<Void> reload() {
        configService.refreshFromDb();
        return Result.ok();
    }
}
