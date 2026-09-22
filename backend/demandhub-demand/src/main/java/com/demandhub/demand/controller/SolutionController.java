package com.demandhub.demand.controller;

import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.SolutionReviewRequest;
import com.demandhub.demand.dto.SolutionSaveRequest;
import com.demandhub.demand.dto.SolutionUpdateRequest;
import com.demandhub.demand.entity.ReviewEntity;
import com.demandhub.demand.entity.SolutionEntity;
import com.demandhub.demand.service.SolutionService;
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
 * M4 方案协作：多版本、提交评审、评审通过/打回、版本对比、评审记录。
 */
@Tag(name = "方案与评审")
@RestController
@RequestMapping("/demand/solution")
public class SolutionController {

    private final SolutionService solutionService;

    public SolutionController(SolutionService solutionService) {
        this.solutionService = solutionService;
    }

    @Operation(summary = "新建方案版本（版本号递增）")
    @PostMapping
    public Result<SolutionEntity> create(@RequestBody SolutionSaveRequest request) {
        return Result.ok(solutionService.create(request));
    }

    @Operation(summary = "更新方案草稿（仅作者、仅 DRAFT）")
    @PutMapping("/{id}")
    public Result<SolutionEntity> update(@PathVariable Long id, @RequestBody SolutionUpdateRequest request) {
        return Result.ok(solutionService.update(id, request));
    }

    @Operation(summary = "提交评审（需求 → SOLUTION_REVIEW）")
    @PostMapping("/{id}/submit-review")
    public Result<Void> submitReview(@PathVariable Long id) {
        solutionService.submitReview(id);
        return Result.ok();
    }

    @Operation(summary = "方案评审（本类型本组织经理：PASS → CONFIRMED / REJECT → ANALYZING）")
    @RequireRole("MANAGER")
    @PostMapping("/{id}/review")
    public Result<Void> review(@PathVariable Long id, @RequestBody SolutionReviewRequest request) {
        solutionService.review(id, request);
        return Result.ok();
    }

    @Operation(summary = "方案版本列表")
    @GetMapping("/list")
    public Result<List<SolutionEntity>> list(@RequestParam Long demandId) {
        return Result.ok(solutionService.listByDemand(demandId));
    }

    @Operation(summary = "版本对比（返回两个版本完整内容）")
    @GetMapping("/compare")
    public Result<List<SolutionEntity>> compare(@RequestParam Long demandId,
                                                @RequestParam Integer v1,
                                                @RequestParam Integer v2) {
        return Result.ok(solutionService.compare(demandId, v1, v2));
    }

    @Operation(summary = "评审/验收记录列表")
    @GetMapping("/reviews")
    public Result<List<ReviewEntity>> reviews(@RequestParam Long demandId,
                                              @RequestParam(required = false) String reviewType) {
        return Result.ok(solutionService.listReviews(demandId, reviewType));
    }
}
