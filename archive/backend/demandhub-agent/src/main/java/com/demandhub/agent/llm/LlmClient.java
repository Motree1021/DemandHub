package com.demandhub.agent.llm;

import com.demandhub.agent.entity.DemandView;
import com.demandhub.agent.entity.KnowledgeDocEntity;

import java.util.List;
import java.util.Map;

/**
 * 大模型平台客户端（架构 4.7，一期 Mock 实现）。
 * 二期对接公司大模型平台时替换实现类即可，接口与降级逻辑保持不变：
 * 所有方法在大模型不可用时应抛出 {@link LlmUnavailableException}。
 */
public interface LlmClient {

    /** 大模型平台当前是否可用（降级探测） */
    boolean available();

    /**
     * 提报启发对话（FR-M9-01）：自然语言 → 追问 → 结构化字段。
     *
     * @param renderedPrompt 已渲染的 Prompt（模板来自 agent_prompt_template）
     * @param history        会话历史（按时间升序）
     * @param userMessage    本轮用户输入
     * @param formContext    前端当前表单字段快照（用户手填 + 已回填）
     * @param prevElements   上一轮要素质量状态（P10：追问阶梯计次/SKIP 粘性；首轮为空）
     */
    GuideChatResult chatSubmitGuide(String renderedPrompt, List<String> history, String userMessage,
                                    Map<String, Object> formContext, List<GuideChatResult.ElementStatus> prevElements);

    /** 处理辅助：生成调研问题清单（FR-M9-02） */
    List<String> generateQuestions(String renderedPrompt, DemandView demand, List<KnowledgeDocEntity> similarDocs);

    /** 处理辅助：生成方案初稿（FR-M9-02；仅写草稿区，人工确认后入库） */
    SolutionDraftContent generateSolutionDraft(String renderedPrompt, DemandView demand, List<KnowledgeDocEntity> similarDocs);

    /** 文本向量化（FR-M9-03；一期 Mock embedding，二期换平台 embedding 模型） */
    double[] embed(String text);

    /** 方案初稿内容（specContent 需求理解 / solutionContent 方案内容） */
    record SolutionDraftContent(String specContent, String solutionContent) {
    }
}
