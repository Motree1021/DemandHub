package com.demandhub.agent.llm;

import com.demandhub.agent.entity.DemandView;
import com.demandhub.agent.entity.KnowledgeDocEntity;
import org.springframework.stereotype.Component;

import java.time.LocalDate;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 大模型平台 Mock 实现（一期）：确定性规则模拟对话/生成/向量化。
 * 所有能力先检查 {@link LlmSwitch}，不可用时抛 {@link LlmUnavailableException}（降级）。
 * 二期替换为真实 HTTP 客户端（超时/异常 → 同样抛 LlmUnavailableException），调用方不变。
 */
@Component
public class MockLlmClient implements LlmClient {

    private final LlmSwitch llmSwitch;

    public MockLlmClient(LlmSwitch llmSwitch) {
        this.llmSwitch = llmSwitch;
    }

    @Override
    public boolean available() {
        return llmSwitch.available();
    }

    private void requireAvailable() {
        if (!llmSwitch.available()) {
            throw new LlmUnavailableException();
        }
    }

    // ---------------- 提报启发（FR-M9-01） ----------------

    @Override
    public GuideChatResult chatSubmitGuide(String renderedPrompt, List<String> history, String userMessage,
                                           Map<String, Object> formContext) {
        requireAvailable();
        Map<String, Object> merged = new LinkedHashMap<>();
        // 先放本轮抽取，再叠加表单已有值（用户手动编辑优先）
        Map<String, Object> extracted = extract(userMessage);
        merged.putAll(extracted);
        if (formContext != null) {
            formContext.forEach((k, v) -> {
                if (v != null && !String.valueOf(v).isBlank()) {
                    merged.put(k, v);
                }
            });
        }
        // content 兜底：若描述为空且本轮输入够长，视为需求描述
        if (isBlank(merged.get("content")) && userMessage != null && userMessage.trim().length() >= 15
                && !isTitleLike(userMessage)) {
            merged.put("content", userMessage.trim());
        }

        List<String> missing = new ArrayList<>();
        if (isBlank(merged.get("title"))) {
            missing.add("title");
        }
        if (isBlank(merged.get("demandTypeCode"))) {
            missing.add("demandTypeCode");
        }
        if (isBlank(merged.get("content"))) {
            missing.add("content");
        }

        Map<String, Object> structured = new LinkedHashMap<>();
        copyIfPresent(structured, merged, "title");
        copyIfPresent(structured, merged, "demandTypeCode");
        copyIfPresent(structured, merged, "content");
        structured.put("urgency", merged.getOrDefault("urgency", "NORMAL"));
        copyIfPresent(structured, merged, "expectDeliveryAt");
        if (merged.containsKey("ext")) {
            structured.put("ext", merged.get("ext"));
        }

        String reply;
        if (missing.contains("title")) {
            reply = "好的，我来帮你整理这个需求。先用一句话概括一下它吧，比如「代销看板增加机构持仓维度」——这就是需求标题。";
        } else if (missing.contains("demandTypeCode")) {
            reply = "明白，标题是「" + merged.get("title") + "」。这个需求属于哪一类？科技（系统功能/数据报表/接口）、物料（宣传品/印刷品）还是培训（课程/组织培训）？";
        } else if (missing.contains("content")) {
            String typeName = typeName(String.valueOf(merged.get("demandTypeCode")));
            reply = "好的，已按「" + typeName + "」需求准备。请描述一下业务背景、使用场景和期望效果，越具体越好，我会整理成需求描述。";
        } else {
            StringBuilder sb = new StringBuilder("已经整理好啦，关键信息如下：\n");
            sb.append("· 标题：").append(merged.get("title")).append('\n');
            sb.append("· 类型：").append(typeName(String.valueOf(merged.get("demandTypeCode")))).append('\n');
            sb.append("· 紧急程度：").append(urgencyName(String.valueOf(structured.get("urgency"))));
            if (!merged.containsKey("urgency")) {
                sb.append("（未提及，默认普通，可改）");
            }
            sb.append('\n');
            if (merged.get("expectDeliveryAt") != null) {
                sb.append("· 期望交付：").append(merged.get("expectDeliveryAt")).append('\n');
            }
            sb.append("\n字段已自动回填到左侧表单，可直接编辑修改；都确认无误后点「提交需求」即可。");
            reply = sb.toString();
        }
        return new GuideChatResult(reply, structured, missing, missing.isEmpty());
    }

    /** 关键词抽取（模拟 NER/意图识别） */
    private Map<String, Object> extract(String message) {
        Map<String, Object> out = new HashMap<>();
        if (message == null || message.isBlank()) {
            return out;
        }
        String m = message.trim();

        // 类型识别
        if (containsAny(m, "培训", "课程", "讲师", "训练营")) {
            out.put("demandTypeCode", "TRAIN");
        } else if (containsAny(m, "物料", "海报", "折页", "易拉宝", "宣传品", "印刷", "礼品", "周边")) {
            out.put("demandTypeCode", "MATL");
        } else if (containsAny(m, "报表", "数据", "看板", "系统", "接口", "功能", "大屏", "导出", "科技", "开发")) {
            out.put("demandTypeCode", "TECH");
        }

        // 紧急程度
        if (containsAny(m, "特急", "立刻", "立即", "马上", "火烧眉毛")) {
            out.put("urgency", "CRITICAL");
        } else if (containsAny(m, "紧急", "尽快", "着急", "急用")) {
            out.put("urgency", "URGENT");
        }

        // 期望交付
        if (m.contains("明天")) {
            out.put("expectDeliveryAt", LocalDate.now().plusDays(1) + "T00:00:00");
        } else if (m.contains("下周")) {
            out.put("expectDeliveryAt", LocalDate.now().with(TemporalAdjusters.next(java.time.DayOfWeek.FRIDAY)) + "T00:00:00");
        } else if (m.contains("月底")) {
            out.put("expectDeliveryAt", LocalDate.now().with(TemporalAdjusters.lastDayOfMonth()) + "T00:00:00");
        }

        // 扩展字段提示（科技类）
        Map<String, Object> ext = new HashMap<>();
        if (containsAny(m, "代销")) {
            ext.put("relatedSystem", "代销系统");
        } else if (containsAny(m, "直销")) {
            ext.put("relatedSystem", "直销系统");
        } else if (containsAny(m, "估值")) {
            ext.put("relatedSystem", "估值系统");
        }
        if (containsAny(m, "看板", "报表", "数据")) {
            ext.put("relatedModule", "数据看板");
        }
        if (!ext.isEmpty()) {
            out.put("ext", ext);
        }

        // 标题候选：短句且不像描述性长文时，去引导词后作为标题
        if (isTitleLike(m)) {
            String title = m.replaceAll("^(我想要个?|我想|我要|我需要|需要一个?|帮我做个?|帮我|请帮我)", "").trim();
            title = title.replaceAll("[。！？!?]$", "");
            if (title.length() >= 2 && title.length() <= 30) {
                out.put("title", title);
            }
        }
        return out;
    }

    /** 短句（≤30 字）视为标题候选；长句视为描述 */
    private boolean isTitleLike(String m) {
        return m != null && m.trim().length() <= 30;
    }

    // ---------------- 处理辅助（FR-M9-02） ----------------

    @Override
    public List<String> generateQuestions(String renderedPrompt, DemandView demand, List<KnowledgeDocEntity> similarDocs) {
        requireAvailable();
        List<String> questions = new ArrayList<>();
        questions.add("需求的核心使用角色与使用频次是什么？日常谁在什么节点会使用？");
        if ("TECH".equals(demand.getDemandTypeCode())) {
            questions.add("「" + demand.getTitle() + "」涉及的数据来源与更新链路是否已梳理清楚？口径由谁确认？");
            questions.add("与上下游系统的边界如何划分？哪些字段由本需求维护，哪些依赖外部？");
            questions.add("性能与数据权限有何约束？是否需要考虑灰度发布？");
        } else if ("MATL".equals(demand.getDemandTypeCode())) {
            questions.add("物料的使用场景、投放渠道与预计用量是多少？");
            questions.add("设计稿由谁提供？品牌合规（LOGO/色号/ disclaimer）是否已确认？");
            questions.add("期望到位时间是否考虑了制作与物流周期？");
        } else if ("TRAIN".equals(demand.getDemandTypeCode())) {
            questions.add("培训对象、人数与基础水平如何？是否有训前调研？");
            questions.add("培训形式（线上/线下/混合）与时长要求？");
            questions.add("培训效果如何评估？是否需要考试或满意度问卷？");
        } else {
            questions.add("该需求的业务背景与目标收益是什么？");
            questions.add("验收口径如何量化？");
        }
        if (similarDocs != null && !similarDocs.isEmpty()) {
            KnowledgeDocEntity top = similarDocs.get(0);
            questions.add("相似历史需求 " + top.getDemandNo() + "「" + top.getTitle() + "」的方案与验收经验是否可复用？有哪些差异点？");
        }
        questions.add("期望交付里程碑如何拆分？关键依赖（数据/人员/外部系统）是否已就绪？");
        return questions;
    }

    @Override
    public SolutionDraftContent generateSolutionDraft(String renderedPrompt, DemandView demand,
                                                      List<KnowledgeDocEntity> similarDocs) {
        requireAvailable();
        String typeName = typeName(demand.getDemandTypeCode());
        StringBuilder spec = new StringBuilder();
        spec.append("【需求理解】（AI 生成，需人工确认）\n");
        spec.append("需求「").append(demand.getTitle()).append("」属于").append(typeName)
                .append("类需求，紧急程度 ").append(urgencyName(demand.getUrgency())).append("。\n");
        if (demand.getContent() != null && !demand.getContent().isBlank()) {
            String brief = demand.getContent().length() > 120 ? demand.getContent().substring(0, 120) + "…" : demand.getContent();
            spec.append("业务背景摘要：").append(brief).append('\n');
        }
        spec.append("建议进一步确认：使用角色、数据口径、验收标准与期望交付节奏。");

        StringBuilder sol = new StringBuilder();
        sol.append("【方案初稿】（AI 生成，需人工确认后入库）\n");
        sol.append("一、目标：交付「").append(demand.getTitle()).append("」，满足提报方业务场景并可量化验收。\n");
        sol.append("二、范围：\n");
        sol.append("  1. 本期交付核心功能/内容；\n");
        sol.append("  2. 边界外事项列入二期清单（需与提报方确认）。\n");
        sol.append("三、实施要点：\n");
        if ("TECH".equals(demand.getDemandTypeCode())) {
            sol.append("  1. 梳理数据来源与口径，与数据提供方对齐字段定义；\n");
            sol.append("  2. 完成开发与自测，重点验证数据准确性与权限控制；\n");
            sol.append("  3. 灰度上线并观察一周后全量。\n");
        } else if ("MATL".equals(demand.getDemandTypeCode())) {
            sol.append("  1. 确认设计稿与品牌合规；\n");
            sol.append("  2. 供应商打样确认后批量制作；\n");
            sol.append("  3. 按使用场景分批配送到位。\n");
        } else if ("TRAIN".equals(demand.getDemandTypeCode())) {
            sol.append("  1. 确认培训大纲与讲师安排；\n");
            sol.append("  2. 发布报名并组织培训实施；\n");
            sol.append("  3. 收集反馈与效果评估，沉淀课件。\n");
        } else {
            sol.append("  1. 明确交付物与负责人；\n  2. 制定排期并跟踪执行；\n  3. 按验收标准逐项确认。\n");
        }
        if (similarDocs != null && !similarDocs.isEmpty()) {
            sol.append("四、参考：相似历史需求 ");
            for (int i = 0; i < Math.min(2, similarDocs.size()); i++) {
                KnowledgeDocEntity d = similarDocs.get(i);
                sol.append(d.getDemandNo()).append("「").append(d.getTitle()).append("」");
                if (i < Math.min(2, similarDocs.size()) - 1) {
                    sol.append("、");
                }
            }
            sol.append(" 的方案可借鉴，注意本期差异点。\n");
        }
        sol.append("五、风险与依赖：数据口径确认、外部排期、验收资源，请在评审前逐项落实。");
        return new SolutionDraftContent(spec.toString(), sol.toString());
    }

    // ---------------- 向量化（FR-M9-03） ----------------

    @Override
    public double[] embed(String text) {
        // Mock embedding 为本地确定性算法，不依赖外部平台，不做可用性拦截
        return MockEmbedding.embed(text);
    }

    // ---------------- 工具 ----------------

    private boolean containsAny(String text, String... keywords) {
        for (String k : keywords) {
            if (text.contains(k)) {
                return true;
            }
        }
        return false;
    }

    private boolean isBlank(Object v) {
        return v == null || String.valueOf(v).isBlank();
    }

    private void copyIfPresent(Map<String, Object> target, Map<String, Object> source, String key) {
        Object v = source.get(key);
        if (v != null && !String.valueOf(v).isBlank()) {
            target.put(key, v);
        }
    }

    private String typeName(String code) {
        return switch (code == null ? "" : code) {
            case "TECH" -> "科技";
            case "MATL" -> "物料";
            case "TRAIN" -> "培训";
            default -> code == null || code.isBlank() ? "（未选择）" : code;
        };
    }

    private String urgencyName(String code) {
        return switch (code == null ? "" : code) {
            case "URGENT" -> "紧急";
            case "CRITICAL" -> "特急";
            default -> "普通";
        };
    }
}
