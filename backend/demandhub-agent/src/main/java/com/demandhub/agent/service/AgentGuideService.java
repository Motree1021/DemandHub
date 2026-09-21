package com.demandhub.agent.service;

import com.demandhub.agent.entity.AgentMessageEntity;
import com.demandhub.agent.entity.AgentSessionEntity;
import com.demandhub.agent.llm.GuideChatResult;
import com.demandhub.agent.llm.LlmClient;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 提报启发 Agent（FR-M9-01）：自然语言对话 → 多轮追问补齐字段 → 结构化回填表单（用户可编辑）。
 * 编排：会话校验 → 历史加载 → Prompt 渲染（模板可配置）→ 大模型调用（一期 Mock）→ 消息落库。
 * 大模型不可用时抛 LlmUnavailableException（1401），前端降级提示，提报主流程不受影响。
 */
@Service
public class AgentGuideService {

    public static final String SCENE = "SUBMIT_GUIDE";

    private final AgentSessionService sessionService;
    private final PromptTemplateService promptTemplateService;
    private final LlmClient llmClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public AgentGuideService(AgentSessionService sessionService, PromptTemplateService promptTemplateService,
                             LlmClient llmClient) {
        this.sessionService = sessionService;
        this.promptTemplateService = promptTemplateService;
        this.llmClient = llmClient;
    }

    /**
     * 一轮对话：保存用户消息 → 生成回复 → 保存助手消息（含结构化 payload）。
     *
     * @param sessionId   会话 ID（scene=SUBMIT_GUIDE，仅归属人）
     * @param userMessage 用户输入
     * @param formContext 前端当前表单快照（用户手填优先于 AI 抽取）
     */
    public GuideChatResult chat(Long sessionId, String userMessage, Map<String, Object> formContext) {
        if (userMessage == null || userMessage.isBlank()) {
            throw new BizException(ErrorCode.PARAM_INVALID, "消息内容不能为空");
        }
        AgentSessionEntity session = sessionService.requireOwned(sessionId);
        if (!SCENE.equals(session.getScene())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "会话场景不是提报启发");
        }
        if (!"ACTIVE".equals(session.getStatus())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "会话已关闭，请新建会话");
        }
        List<String> history = new ArrayList<>();
        for (AgentMessageEntity m : sessionService.messages(sessionId)) {
            history.add(m.getRole() + ": " + m.getContent());
        }
        String prompt = promptTemplateService.render("SUBMIT_GUIDE", Map.of());
        GuideChatResult result = llmClient.chatSubmitGuide(prompt, history, userMessage.trim(), formContext);
        sessionService.appendMessage(sessionId, "USER", userMessage.trim(), null);
        sessionService.appendMessage(sessionId, "ASSISTANT", result.reply(), toJson(result));
        return result;
    }

    private String toJson(GuideChatResult result) {
        try {
            if (result.structured() == null || result.structured().isEmpty()) {
                return null;
            }
            return objectMapper.writeValueAsString(Map.of(
                    "structured", result.structured(),
                    "missing", result.missing(),
                    "ready", result.ready()));
        } catch (Exception e) {
            return null;
        }
    }
}
