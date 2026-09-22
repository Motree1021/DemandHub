package com.demandhub.agent.controller;

import com.demandhub.agent.entity.AgentDraftEntity;
import com.demandhub.agent.service.AgentAssistService;
import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 处理辅助 Agent（FR-M9-02）：调研问题清单 + 方案初稿（草稿区，人工确认后入 solution 表）。
 * 限处理人/经理使用；大模型不可用 → 1401 降级提示，处理主流程不受影响。
 */
@Tag(name = "Agent-处理辅助")
@RestController
@RequestMapping("/agent/assist")
@RequireRole({"HANDLER", "MANAGER", "ADMIN"})
public class AgentAssistController {

    private final AgentAssistService assistService;

    public AgentAssistController(AgentAssistService assistService) {
        this.assistService = assistService;
    }

    public record GenerateRequest(Long sessionId) {
    }

    public record ConfirmRequest(String specContent, String solutionContent,
                                 @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime planDeliveryAt) {
    }

    @Operation(summary = "生成调研问题清单（写草稿区 PENDING）")
    @PostMapping("/questions")
    public Result<AgentDraftEntity> questions(@RequestBody GenerateRequest request) {
        return Result.ok(assistService.generateQuestions(request.sessionId()));
    }

    @Operation(summary = "生成方案初稿（写草稿区 PENDING，标注 AI 生成需确认）")
    @PostMapping("/solution")
    public Result<AgentDraftEntity> solution(@RequestBody GenerateRequest request) {
        return Result.ok(assistService.generateSolution(request.sessionId()));
    }

    @Operation(summary = "需求草稿列表（PENDING 优先）")
    @GetMapping("/drafts")
    public Result<List<AgentDraftEntity>> drafts(@RequestParam Long demandId) {
        return Result.ok(assistService.drafts(demandId));
    }

    @Operation(summary = "确认方案初稿入库（可编辑后提交；写 solution DRAFT 新版本）")
    @PostMapping("/drafts/{id}/confirm")
    public Result<AgentDraftEntity> confirm(@PathVariable("id") Long draftId,
                                            @RequestBody(required = false) ConfirmRequest request) {
        ConfirmRequest body = request == null ? new ConfirmRequest(null, null, null) : request;
        return Result.ok(assistService.confirmSolution(draftId, body.specContent(), body.solutionContent(),
                body.planDeliveryAt()));
    }

    @Operation(summary = "废弃草稿")
    @PostMapping("/drafts/{id}/discard")
    public Result<Void> discard(@PathVariable("id") Long draftId) {
        assistService.discard(draftId);
        return Result.ok();
    }
}
