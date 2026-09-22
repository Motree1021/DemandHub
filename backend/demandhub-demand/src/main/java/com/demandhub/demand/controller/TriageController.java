package com.demandhub.demand.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import com.demandhub.demand.dto.AssignRequest;
import com.demandhub.demand.dto.ChangeTypeRequest;
import com.demandhub.demand.dto.CloseRequest;
import com.demandhub.demand.dto.TriageActionRequest;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.service.TriageService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * M3 受理与分派工作台：待受理队列、需求池、受理/退回/关闭/分派/领取/类型修正。
 * 列表由数据权限拦截器自动按当前用户组织范围过滤。
 */
@Tag(name = "受理与分派")
@RestController
@RequestMapping("/demand/triage")
public class TriageController {

    private final TriageService triageService;
    private final DemandMapper demandMapper;

    public TriageController(TriageService triageService, DemandMapper demandMapper) {
        this.triageService = triageService;
        this.demandMapper = demandMapper;
    }

    @Operation(summary = "待受理队列（本类型本组织 SUBMITTED，分页+筛选+排序）")
    @RequireRole({"MANAGER", "EXECUTIVE"})
    @GetMapping("/queue")
    public Result<Page<DemandEntity>> queue(@RequestParam(defaultValue = "1") long current,
                                            @RequestParam(defaultValue = "10") long size,
                                            @RequestParam(required = false) String urgency,
                                            @RequestParam(required = false) String demandTypeCode,
                                            @RequestParam(defaultValue = "asc") String submittedOrder) {
        return Result.ok(demandMapper.selectPage(new Page<>(current, size), queueWrapper(urgency, demandTypeCode, submittedOrder)));
    }

    @Operation(summary = "待受理计数（工作台首屏角标）")
    @RequireRole({"MANAGER", "EXECUTIVE"})
    @GetMapping("/queue/count")
    public Result<Long> queueCount(@RequestParam(required = false) String urgency,
                                   @RequestParam(required = false) String demandTypeCode) {
        return Result.ok(demandMapper.selectCount(queueWrapper(urgency, demandTypeCode, "asc")));
    }

    @Operation(summary = "需求池（本类型本组织 TRIAGE，按紧急程度+提交时间）")
    @RequireRole({"MANAGER", "HANDLER", "EXECUTIVE"})
    @GetMapping("/pool")
    public Result<Page<DemandEntity>> pool(@RequestParam(defaultValue = "1") long current,
                                           @RequestParam(defaultValue = "10") long size,
                                           @RequestParam(required = false) String urgency) {
        // 紧急程度：特急 > 紧急 > 普通；同级按提交时间升序（停留久优先）
        return Result.ok(demandMapper.selectPage(new Page<>(current, size),
                new LambdaQueryWrapper<DemandEntity>()
                        .eq(DemandEntity::getStatus, "TRIAGE")
                        .eq(StringUtils.hasText(urgency), DemandEntity::getUrgency, urgency)
                        .last("ORDER BY FIELD(urgency,'CRITICAL','URGENT','NORMAL'), submitted_at ASC")));
    }

    @Operation(summary = "受理通过 → TRIAGE")
    @RequireRole("MANAGER")
    @PostMapping("/{id}/accept")
    public Result<Void> accept(@PathVariable Long id, @RequestBody(required = false) TriageActionRequest request) {
        triageService.accept(id, request == null ? null : request.comment());
        return Result.ok();
    }

    @Operation(summary = "退回补充 → NEED_INFO（说明必填）")
    @RequireRole("MANAGER")
    @PostMapping("/{id}/return")
    public Result<Void> returnForInfo(@PathVariable Long id, @RequestBody TriageActionRequest request) {
        triageService.returnForInfo(id, request.comment());
        return Result.ok();
    }

    @Operation(summary = "关闭（不受理/重复/其他，原因必填）")
    @RequireRole("MANAGER")
    @PostMapping("/{id}/close")
    public Result<Void> close(@PathVariable Long id, @RequestBody CloseRequest request) {
        triageService.close(id, request);
        return Result.ok();
    }

    @Operation(summary = "经理分派 → ANALYZING")
    @RequireRole("MANAGER")
    @PostMapping("/{id}/assign")
    public Result<Void> assign(@PathVariable Long id, @RequestBody AssignRequest request) {
        triageService.assign(id, request);
        return Result.ok();
    }

    @Operation(summary = "处理人领取 → ANALYZING（并发先抢先得）")
    @RequireRole("HANDLER")
    @PostMapping("/{id}/claim")
    public Result<Void> claim(@PathVariable Long id) {
        triageService.claim(id);
        return Result.ok();
    }

    @Operation(summary = "类型修正（仅需求管理者，修正后重新路由）")
    @RequireRole("EXECUTIVE")
    @PostMapping("/{id}/change-type")
    public Result<Void> changeType(@PathVariable Long id, @RequestBody ChangeTypeRequest request) {
        triageService.changeType(id, request);
        return Result.ok();
    }

    private LambdaQueryWrapper<DemandEntity> queueWrapper(String urgency, String demandTypeCode, String submittedOrder) {
        LambdaQueryWrapper<DemandEntity> wrapper = new LambdaQueryWrapper<DemandEntity>()
                .eq(DemandEntity::getStatus, "SUBMITTED")
                .eq(StringUtils.hasText(urgency), DemandEntity::getUrgency, urgency)
                .eq(StringUtils.hasText(demandTypeCode), DemandEntity::getDemandTypeCode, demandTypeCode);
        wrapper.orderBy(true, "asc".equalsIgnoreCase(submittedOrder), DemandEntity::getSubmittedAt);
        return wrapper;
    }
}
