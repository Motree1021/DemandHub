package com.demandhub.agent.llm;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 提报启发对话结果
 *
 * @param reply        Assistant 回复文本（SSE 流式输出）
 * @param structured   结构化字段（已提取的表单字段，前端增量回填；用户可编辑）
 * @param missing      仍缺失的关键字段（title/demandTypeCode/content）
 * @param ready        关键字段已齐备，可回填提交
 * @param elements     要素质量状态清单（P10：科技需求要素 rubric，前端三态完备度清单）
 * @param quickReplies 建议快捷回复（P10：追问阶梯 L3 选项 / 选项类问题，前端渲染为 chips）
 */
public record GuideChatResult(String reply, Map<String, Object> structured, List<String> missing, boolean ready,
                              List<ElementStatus> elements, List<String> quickReplies) {

    /**
     * 要素质量状态
     *
     * @param key      要素键（title/content/techSubtype/businessScenario/acceptanceCriteria/valueImpact）
     * @param status   OK 到位 / VAGUE 模糊（缺可检验事实）/ MISSING 未填 / SKIP 用户主动跳过（不再追问）
     * @param note     状态说明（如"VAGUE：只有形容词，无量化指标"）
     * @param attempts 该要素已被追问次数（≥2 停止追问，保留 VAGUE 标黄待补充）
     */
    public record ElementStatus(String key, String status, String note, int attempts) {
    }

    public static GuideChatResult of(String reply, Map<String, Object> structured, List<String> missing) {
        return new GuideChatResult(reply, structured, missing, missing.isEmpty(), List.of(), List.of());
    }

    public static GuideChatResult empty() {
        return new GuideChatResult("", new HashMap<>(), List.of(), false, List.of(), List.of());
    }
}
