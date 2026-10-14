package com.demandhub.agent.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.agent.entity.AgentDraftEntity;
import com.demandhub.agent.entity.AgentSessionEntity;
import com.demandhub.agent.entity.DemandView;
import com.demandhub.agent.entity.KnowledgeDocEntity;
import com.demandhub.agent.entity.SolutionRowEntity;
import com.demandhub.agent.llm.LlmClient;
import com.demandhub.agent.mapper.AgentDraftMapper;
import com.demandhub.agent.mapper.AgentDemandViewMapper;
import com.demandhub.agent.mapper.SolutionRowMapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 处理辅助 Agent（FR-M9-02）：调研问题清单 + 方案初稿。
 * 产出先写 agent_draft 草稿区（PENDING，内容标注"AI 生成需人工确认"）；
 * 人工确认（可编辑后提交）才写入 solution 表：版本号 = 当前最大 + 1、状态 DRAFT，
 * 与 demand 模块 SolutionService.create 约定一致，之后走既有评审流程。
 */
@Service
public class AgentAssistService {

    public static final String SCENE = "HANDLE_ASSIST";
    public static final String TYPE_QUESTIONS = "QUESTIONS";
    public static final String TYPE_SOLUTION = "SOLUTION";

    private final AgentSessionService sessionService;
    private final PromptTemplateService promptTemplateService;
    private final RagService ragService;
    private final LlmClient llmClient;
    private final AgentDraftMapper draftMapper;
    private final AgentDemandViewMapper demandViewMapper;
    private final SolutionRowMapper solutionRowMapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public AgentAssistService(AgentSessionService sessionService, PromptTemplateService promptTemplateService,
                              RagService ragService, LlmClient llmClient, AgentDraftMapper draftMapper,
                              AgentDemandViewMapper demandViewMapper, SolutionRowMapper solutionRowMapper) {
        this.sessionService = sessionService;
        this.promptTemplateService = promptTemplateService;
        this.ragService = ragService;
        this.llmClient = llmClient;
        this.draftMapper = draftMapper;
        this.demandViewMapper = demandViewMapper;
        this.solutionRowMapper = solutionRowMapper;
    }

    /** 生成调研问题清单（写草稿区 PENDING，同时追加一条会话消息） */
    public AgentDraftEntity generateQuestions(Long sessionId) {
        AgentSessionEntity session = requireAssistSession(sessionId);
        DemandView demand = requireDemand(session.getDemandId());
        List<KnowledgeDocEntity> similarDocs = ragService.similarDocs(demand.getId(), 3);
        String prompt = promptTemplateService.render("HANDLE_ASSIST_QUESTIONS",
                Map.of("demand_no", demand.getDemandNo(), "title", demand.getTitle(),
                        "type", demand.getDemandTypeCode() == null ? "" : demand.getDemandTypeCode()));
        List<String> questions = llmClient.generateQuestions(prompt, demand, similarDocs);
        AgentDraftEntity draft = saveDraft(demand.getId(), sessionId, TYPE_QUESTIONS, toJson(questions));
        sessionService.appendMessage(sessionId, "ASSISTANT",
                "【AI 生成 · 调研问题清单】（需人工确认）\n" + String.join("\n",
                        questions.stream().map(q -> "· " + q).toList()),
                null);
        return draft;
    }

    /** 生成方案初稿（写草稿区 PENDING；确认后才入 solution 表） */
    public AgentDraftEntity generateSolution(Long sessionId) {
        AgentSessionEntity session = requireAssistSession(sessionId);
        DemandView demand = requireDemand(session.getDemandId());
        List<KnowledgeDocEntity> similarDocs = ragService.similarDocs(demand.getId(), 3);
        String prompt = promptTemplateService.render("HANDLE_ASSIST_SOLUTION",
                Map.of("demand_no", demand.getDemandNo(), "title", demand.getTitle(),
                        "type", demand.getDemandTypeCode() == null ? "" : demand.getDemandTypeCode()));
        LlmClient.SolutionDraftContent content = llmClient.generateSolutionDraft(prompt, demand, similarDocs);
        AgentDraftEntity draft = saveDraft(demand.getId(), sessionId, TYPE_SOLUTION, toJson(content));
        sessionService.appendMessage(sessionId, "ASSISTANT",
                content.specContent() + "\n\n" + content.solutionContent(), null);
        return draft;
    }

    /** 需求的草稿列表（PENDING 优先，再按时间倒序） */
    public List<AgentDraftEntity> drafts(Long demandId) {
        requireDemand(demandId);
        List<AgentDraftEntity> drafts = draftMapper.selectList(new LambdaQueryWrapper<AgentDraftEntity>()
                .eq(AgentDraftEntity::getDemandId, demandId)
                .orderByDesc(AgentDraftEntity::getId));
        drafts.sort((a, b) -> {
            if (a.getStatus().equals(b.getStatus())) {
                return b.getId().compareTo(a.getId());
            }
            return "PENDING".equals(a.getStatus()) ? -1 : 1;
        });
        return drafts;
    }

    /**
     * 确认方案初稿入库：写 solution（版本 max+1、DRAFT）→ 草稿标记 CONFIRMED。
     * 允许确认前编辑内容；前置校验与 demand 模块一致（需求需处于 ANALYZING）。
     */
    @Transactional(rollbackFor = Exception.class)
    public AgentDraftEntity confirmSolution(Long draftId, String specContent, String solutionContent,
                                            LocalDateTime planDeliveryAt) {
        CurrentUser user = requireLogin();
        AgentDraftEntity draft = requireDraft(draftId);
        if (!TYPE_SOLUTION.equals(draft.getDraftType())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "仅方案初稿草稿支持确认入库");
        }
        DemandView demand = requireDemand(draft.getDemandId());
        if (!"ANALYZING".equals(demand.getStatus())) {
            throw new BizException(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅分析中的需求可确认方案入库");
        }
        // 用户确认时未编辑 → 用草稿原文
        String spec = specContent;
        String sol = solutionContent;
        if ((spec == null || spec.isBlank()) && (sol == null || sol.isBlank())) {
            LlmClient.SolutionDraftContent origin = parseSolutionContent(draft.getContent());
            spec = origin.specContent();
            sol = origin.solutionContent();
        }
        Integer maxVersion = solutionRowMapper.selectList(new LambdaQueryWrapper<SolutionRowEntity>()
                        .eq(SolutionRowEntity::getDemandId, draft.getDemandId())
                        .orderByDesc(SolutionRowEntity::getVersion)
                        .last("LIMIT 1"))
                .stream().findFirst().map(SolutionRowEntity::getVersion).orElse(0);
        SolutionRowEntity solution = new SolutionRowEntity();
        solution.setDemandId(draft.getDemandId());
        solution.setVersion(maxVersion + 1);
        solution.setAuthorId(user.getId());
        solution.setSpecContent(spec);
        solution.setSolutionContent(sol);
        solution.setPlanDeliveryAt(planDeliveryAt);
        solution.setStatus("DRAFT");
        solution.setRemark("AI 生成，人工确认入库");
        solutionRowMapper.insert(solution);

        draft.setStatus("CONFIRMED");
        draft.setConfirmedBy(user.getId());
        draft.setConfirmedAt(LocalDateTime.now());
        draft.setTargetSolutionId(solution.getId());
        draftMapper.updateById(draft);
        return draft;
    }

    /** 废弃草稿（PENDING → DISCARDED） */
    public void discard(Long draftId) {
        AgentDraftEntity draft = requireDraft(draftId);
        draft.setStatus("DISCARDED");
        draft.setConfirmedBy(requireLogin().getId());
        draft.setConfirmedAt(LocalDateTime.now());
        draftMapper.updateById(draft);
    }

    private AgentSessionEntity requireAssistSession(Long sessionId) {
        AgentSessionEntity session = sessionService.requireOwned(sessionId);
        if (!SCENE.equals(session.getScene())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "会话场景不是处理辅助");
        }
        if (session.getDemandId() == null) {
            throw new BizException(ErrorCode.PARAM_INVALID, "处理辅助会话未关联需求");
        }
        return session;
    }

    private DemandView requireDemand(Long demandId) {
        DemandView demand = demandViewMapper.selectById(demandId);
        if (demand == null) {
            throw new BizException(ErrorCode.DEMAND_NOT_FOUND);
        }
        return demand;
    }

    private AgentDraftEntity requireDraft(Long draftId) {
        AgentDraftEntity draft = draftMapper.selectById(draftId);
        if (draft == null) {
            throw new BizException(ErrorCode.AGENT_DRAFT_NOT_FOUND);
        }
        if (!"PENDING".equals(draft.getStatus())) {
            throw new BizException(ErrorCode.AGENT_DRAFT_CONFIRMED);
        }
        return draft;
    }

    private AgentDraftEntity saveDraft(Long demandId, Long sessionId, String type, String content) {
        AgentDraftEntity draft = new AgentDraftEntity();
        draft.setDemandId(demandId);
        draft.setSessionId(sessionId);
        draft.setDraftType(type);
        draft.setContent(content);
        draft.setStatus("PENDING");
        draft.setCreatedBy(requireLogin().getId());
        draftMapper.insert(draft);
        return draft;
    }

    private LlmClient.SolutionDraftContent parseSolutionContent(String json) {
        try {
            var node = objectMapper.readTree(json);
            return new LlmClient.SolutionDraftContent(
                    node.path("specContent").asText(""), node.path("solutionContent").asText(""));
        } catch (Exception e) {
            return new LlmClient.SolutionDraftContent("", json == null ? "" : json);
        }
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            throw new BizException(ErrorCode.SYSTEM_ERROR, "草稿序列化失败");
        }
    }

    private CurrentUser requireLogin() {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return user;
    }
}
