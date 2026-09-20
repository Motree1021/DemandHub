package com.demandhub.demand.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.service.DemandTypeAdminService;
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

/**
 * M8 需求类型字典管理（FR-M8-01，限 ADMIN）：类型编码、名称、默认承接组织、状态机绑定、排序、启停。
 */
@Tag(name = "系统管理-需求类型")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/demand/admin/types")
public class DemandTypeAdminController {

    private final DemandTypeAdminService typeAdminService;

    public DemandTypeAdminController(DemandTypeAdminService typeAdminService) {
        this.typeAdminService = typeAdminService;
    }

    @Operation(summary = "类型列表（含停用）")
    @GetMapping
    public Result<List<DemandTypeEntity>> list() {
        return Result.ok(typeAdminService.list());
    }

    @Operation(summary = "新增类型（编码唯一，创建后提报即可选）")
    @PostMapping
    public Result<DemandTypeEntity> create(@RequestBody DemandTypeEntity request) {
        return Result.ok(typeAdminService.create(request));
    }

    @Operation(summary = "编辑类型（编码不可改；停用不影响历史数据）")
    @PutMapping("/{id}")
    public Result<DemandTypeEntity> update(@PathVariable Long id, @RequestBody DemandTypeEntity request) {
        return Result.ok(typeAdminService.update(id, request));
    }
}
