package com.demandhub.agent.controller;

import com.demandhub.agent.service.RagService;
import com.demandhub.common.annotation.RequireRole;
import com.demandhub.common.core.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * RAG 知识库检索（FR-M9-03）：处理人打开需求时推荐相似历史需求 Top N。
 * 返回 DONE 需求低敏元数据（编号/标题/类型/相似度），详情跳转仍受 demand 服务数据权限控制。
 */
@Tag(name = "Agent-RAG 检索")
@RestController
@RequestMapping("/agent/rag")
@RequireRole({"HANDLER", "DEMAND_MANAGER", "ADMIN", "EXECUTIVE"})
public class RagController {

    private final RagService ragService;

    public RagController(RagService ragService) {
        this.ragService = ragService;
    }

    @Operation(summary = "相似历史需求 Top N（按语义相似度，含阈值过滤）")
    @GetMapping("/similar")
    public Result<List<RagService.SimilarDoc>> similar(@RequestParam Long demandId,
                                                       @RequestParam(defaultValue = "5") int topN) {
        return Result.ok(ragService.similar(demandId, Math.min(Math.max(topN, 1), 10)));
    }
}
