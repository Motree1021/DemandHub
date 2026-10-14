package com.demandhub.agent.controller;

import com.demandhub.agent.entity.AgentMessageEntity;
import com.demandhub.agent.entity.AgentSessionEntity;
import com.demandhub.agent.service.AgentSessionService;
import com.demandhub.common.core.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Agent 会话管理（FR-M9-01/02）
 */
@Tag(name = "Agent-会话管理")
@RestController
@RequestMapping("/agent/session")
public class AgentSessionController {

    private final AgentSessionService sessionService;

    public AgentSessionController(AgentSessionService sessionService) {
        this.sessionService = sessionService;
    }

    public record CreateSessionRequest(String scene, Long demandId, String firstMessage) {
    }

    @Operation(summary = "新建会话（scene：SUBMIT_GUIDE 提报启发 / HANDLE_ASSIST 处理辅助）")
    @PostMapping
    public Result<AgentSessionEntity> create(@RequestBody CreateSessionRequest request) {
        return Result.ok(sessionService.create(request.scene(), request.demandId(), request.firstMessage()));
    }

    @Operation(summary = "我的会话列表")
    @GetMapping("/list")
    public Result<List<AgentSessionEntity>> listMine(@RequestParam(required = false) String scene) {
        return Result.ok(sessionService.listMine(scene));
    }

    @Operation(summary = "会话历史消息")
    @GetMapping("/{id}/messages")
    public Result<List<AgentMessageEntity>> messages(@PathVariable("id") Long sessionId) {
        return Result.ok(sessionService.messages(sessionId));
    }

    @Operation(summary = "关闭会话")
    @PostMapping("/{id}/close")
    public Result<Void> close(@PathVariable("id") Long sessionId) {
        sessionService.close(sessionId);
        return Result.ok();
    }
}
