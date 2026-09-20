package com.demandhub.demand.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.demand.entity.SysDictEntity;
import com.demandhub.demand.service.SysDictAdminService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
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
 * M8 通用字典管理（FR-M8-04，限 ADMIN）：紧急程度、关闭原因、挂起原因等下拉项维护。
 */
@Tag(name = "系统管理-通用字典")
@RequireRole("ADMIN")
@RestController
@RequestMapping("/demand/admin/dicts")
public class SysDictAdminController {

    private final SysDictAdminService dictService;

    public SysDictAdminController(SysDictAdminService dictService) {
        this.dictService = dictService;
    }

    @Operation(summary = "字典项列表（可按分组过滤）")
    @GetMapping
    public Result<List<SysDictEntity>> list(@RequestParam(required = false) String dictType) {
        return Result.ok(dictService.list(dictType));
    }

    @Operation(summary = "字典分组列表")
    @GetMapping("/types")
    public Result<List<String>> types() {
        return Result.ok(dictService.listTypes());
    }

    @Operation(summary = "新增字典项（分组+编码唯一）")
    @PostMapping
    public Result<SysDictEntity> create(@RequestBody SysDictEntity request) {
        return Result.ok(dictService.create(request));
    }

    @Operation(summary = "编辑字典项（编码不可改；停用后历史数据仍展示原名称）")
    @PutMapping("/{id}")
    public Result<SysDictEntity> update(@PathVariable Long id, @RequestBody SysDictEntity request) {
        return Result.ok(dictService.update(id, request));
    }
}
