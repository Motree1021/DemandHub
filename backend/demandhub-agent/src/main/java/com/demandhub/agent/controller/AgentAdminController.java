package com.demandhub.agent.controller;

import com.demandhub.agent.entity.AgentPromptTemplateEntity;
import com.demandhub.agent.llm.LlmSwitch;
import com.demandhub.agent.service.PromptTemplateService;
import com.demandhub.agent.service.RagService;
import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
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
 * Agent 管理端（限 ADMIN）：Prompt 模板配置、大模型开关（降级自测）、RAG 运维。
 */
@Tag(name = "Agent-管理端")
@RestController
@RequestMapping("/agent/admin")
@RequireRole("ADMIN")
public class AgentAdminController {

    private final PromptTemplateService promptTemplateService;
    private final LlmSwitch llmSwitch;
    private final RagService ragService;

    public AgentAdminController(PromptTemplateService promptTemplateService, LlmSwitch llmSwitch,
                                RagService ragService) {
        this.promptTemplateService = promptTemplateService;
        this.llmSwitch = llmSwitch;
        this.ragService = ragService;
    }

    @Operation(summary = "Prompt 模板列表")
    @GetMapping("/prompts")
    public Result<List<AgentPromptTemplateEntity>> prompts() {
        return Result.ok(promptTemplateService.listAll());
    }

    public record PromptUpdateRequest(String content, String status, String remark) {
    }

    @Operation(summary = "更新 Prompt 模板（即时生效无需重启）")
    @PutMapping("/prompts/{id}")
    public Result<AgentPromptTemplateEntity> updatePrompt(@PathVariable("id") Long id,
                                                          @RequestBody PromptUpdateRequest request) {
        return Result.ok(promptTemplateService.update(id, request.content(), request.status(), request.remark()));
    }

    @Operation(summary = "大模型平台可用状态（一期 Mock 开关）")
    @GetMapping("/llm-switch")
    public Result<Map<String, Object>> llmSwitchStatus() {
        return Result.ok(Map.of("available", llmSwitch.available()));
    }

    public record LlmSwitchRequest(boolean available) {
    }

    @Operation(summary = "切换大模型可用状态（自测降级：关闭后 Agent 接口返回 1401）")
    @PostMapping("/llm-switch")
    public Result<Map<String, Object>> toggleLlmSwitch(@RequestBody LlmSwitchRequest request) {
        llmSwitch.setAvailable(request.available());
        return Result.ok(Map.of("available", llmSwitch.available()));
    }

    @Operation(summary = "RAG 知识库规模")
    @GetMapping("/rag/stats")
    public Result<Map<String, Object>> ragStats() {
        return Result.ok(Map.of("docCount", ragService.docCount()));
    }

    @Operation(summary = "手动触发 DONE 需求向量化（自测/补偿用，幂等）")
    @PostMapping("/rag/vectorize/{demandId}")
    public Result<Void> vectorize(@PathVariable Long demandId) {
        ragService.vectorizeDoneDemand(demandId);
        return Result.ok();
    }
}
