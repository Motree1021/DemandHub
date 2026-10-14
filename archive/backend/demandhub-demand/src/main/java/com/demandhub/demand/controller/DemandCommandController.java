package com.demandhub.demand.controller;

import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.AcceptanceReviewRequest;
import com.demandhub.demand.dto.HoldRequest;
import com.demandhub.demand.dto.ResubmitRequest;
import com.demandhub.demand.dto.SplitRequest;
import com.demandhub.demand.dto.SubmitRequest;
import com.demandhub.demand.dto.WithdrawRequest;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.service.AcceptanceService;
import com.demandhub.demand.service.DemandSubmitService;
import com.demandhub.demand.service.LifecycleService;
import com.demandhub.demand.service.RelationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 需求命令操作（M2 提报/撤销/补充重提，M4 开始处理/挂起/恢复，M5 验收，拆分）。
 */
@Tag(name = "需求操作")
@RestController
@RequestMapping("/demand/demand")
public class DemandCommandController {

    private final DemandSubmitService submitService;
    private final LifecycleService lifecycleService;
    private final AcceptanceService acceptanceService;
    private final RelationService relationService;

    public DemandCommandController(DemandSubmitService submitService, LifecycleService lifecycleService,
                                   AcceptanceService acceptanceService, RelationService relationService) {
        this.submitService = submitService;
        this.lifecycleService = lifecycleService;
        this.acceptanceService = acceptanceService;
        this.relationService = relationService;
    }

    @Operation(summary = "提交需求（M2：生成编号、按类型路由、写扩展表，可带草稿/代办/附件）")
    @PostMapping("/submit")
    public Result<DemandEntity> submit(@RequestBody SubmitRequest request) {
        return Result.ok(submitService.submit(request));
    }

    @Operation(summary = "提报人撤销（仅 SUBMITTED，原因必填）")
    @PostMapping("/{id}/withdraw")
    public Result<Void> withdraw(@PathVariable Long id, @RequestBody WithdrawRequest request) {
        submitService.withdraw(id, request.reason());
        return Result.ok();
    }

    @Operation(summary = "退回补充后重新提交（NEED_INFO → SUBMITTED）")
    @PostMapping("/{id}/resubmit")
    public Result<DemandEntity> resubmit(@PathVariable Long id, @RequestBody ResubmitRequest request) {
        return Result.ok(submitService.resubmit(id, request));
    }

    @Operation(summary = "开始处理（CONFIRMED → IN_PROGRESS，仅处理人）")
    @PostMapping("/{id}/start")
    public Result<Void> start(@PathVariable Long id) {
        lifecycleService.start(id);
        return Result.ok();
    }

    @Operation(summary = "挂起（在途态 → 主态+ON_HOLD，原因必填）")
    @PostMapping("/{id}/hold")
    public Result<Void> hold(@PathVariable Long id, @RequestBody HoldRequest request) {
        lifecycleService.hold(id, request.reason());
        return Result.ok();
    }

    @Operation(summary = "恢复（ON_HOLD → 挂起前主状态）")
    @PostMapping("/{id}/resume")
    public Result<Void> resume(@PathVariable Long id) {
        lifecycleService.resume(id);
        return Result.ok();
    }

    @Operation(summary = "提交验收（M5：校验方案已确认/工时已填/交付物已传）")
    @PostMapping("/{id}/submit-acceptance")
    public Result<Void> submitAcceptance(@PathVariable Long id) {
        acceptanceService.submitAcceptance(id);
        return Result.ok();
    }

    @Operation(summary = "验收结论（M5：PASS → DONE 评分归档 / REJECT → IN_PROGRESS）")
    @PostMapping("/{id}/acceptance-review")
    public Result<Void> acceptanceReview(@PathVariable Long id, @RequestBody AcceptanceReviewRequest request) {
        acceptanceService.review(id, request);
        return Result.ok();
    }

    @Operation(summary = "拆分子需求（独立编号，直接入父需求承接组织需求池）")
    @PostMapping("/{id}/split")
    public Result<DemandEntity> split(@PathVariable Long id, @RequestBody SplitRequest request) {
        return Result.ok(relationService.split(id, request));
    }
}
