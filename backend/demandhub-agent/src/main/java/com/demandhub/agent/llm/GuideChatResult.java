package com.demandhub.agent.llm;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 提报启发对话结果
 *
 * @param reply      Assistant 回复文本（SSE 流式输出）
 * @param structured 结构化字段（已提取的表单字段，前端增量回填；用户可编辑）
 * @param missing    仍缺失的关键字段（title/demandTypeCode/content）
 * @param ready      关键字段已齐备，可回填提交
 */
public record GuideChatResult(String reply, Map<String, Object> structured, List<String> missing, boolean ready) {

    public static GuideChatResult of(String reply, Map<String, Object> structured, List<String> missing) {
        return new GuideChatResult(reply, structured, missing, missing.isEmpty());
    }

    public static GuideChatResult empty() {
        return new GuideChatResult("", new HashMap<>(), List.of(), false);
    }
}
