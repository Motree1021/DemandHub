package com.demandhub.demand.controller;

import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.RelationAddRequest;
import com.demandhub.demand.entity.DemandRelationEntity;
import com.demandhub.demand.service.RelationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * M4 需求关联：父子/依赖/重复/拆分，双向可见。
 */
@Tag(name = "需求关联")
@RestController
@RequestMapping("/demand/relation")
public class RelationController {

    private final RelationService relationService;

    public RelationController(RelationService relationService) {
        this.relationService = relationService;
    }

    @Operation(summary = "新增关联（PARENT/DEPENDS/DUPLICATE/SPLIT）")
    @PostMapping
    public Result<DemandRelationEntity> add(@RequestBody RelationAddRequest request) {
        return Result.ok(relationService.add(request.demandId(), request.relatedDemandId(), request.relationType()));
    }

    @Operation(summary = "删除关联")
    @DeleteMapping("/{id}")
    public Result<Void> remove(@PathVariable Long id) {
        relationService.remove(id);
        return Result.ok();
    }

    @Operation(summary = "关联列表（双向）")
    @GetMapping("/list")
    public Result<List<DemandRelationEntity>> list(@RequestParam Long demandId) {
        return Result.ok(relationService.listByDemand(demandId));
    }
}
