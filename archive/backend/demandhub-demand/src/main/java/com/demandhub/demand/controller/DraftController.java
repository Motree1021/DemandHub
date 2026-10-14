package com.demandhub.demand.controller;

import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.DraftSaveRequest;
import com.demandhub.demand.entity.DemandDraftEntity;
import com.demandhub.demand.service.DraftService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * M2 草稿（FR-M2-03）：仅本人可见/可编辑。
 */
@Tag(name = "需求草稿")
@RestController
@RequestMapping("/demand/draft")
public class DraftController {

    private final DraftService draftService;

    public DraftController(DraftService draftService) {
        this.draftService = draftService;
    }

    @Operation(summary = "保存草稿（id 为空新建，否则更新）")
    @PostMapping("/save")
    public Result<DemandDraftEntity> save(@RequestBody DraftSaveRequest request) {
        return Result.ok(draftService.save(request));
    }

    @Operation(summary = "我的草稿列表")
    @GetMapping("/list")
    public Result<List<DemandDraftEntity>> listMine() {
        return Result.ok(draftService.listMine());
    }

    @Operation(summary = "草稿详情")
    @GetMapping("/{id}")
    public Result<DemandDraftEntity> get(@PathVariable Long id) {
        return Result.ok(draftService.getMine(id));
    }

    @Operation(summary = "删除草稿")
    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable Long id) {
        draftService.deleteMine(id);
        return Result.ok();
    }
}
