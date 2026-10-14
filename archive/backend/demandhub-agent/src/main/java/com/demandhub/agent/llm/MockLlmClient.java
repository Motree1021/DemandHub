package com.demandhub.agent.llm;

import com.demandhub.agent.entity.DemandView;
import com.demandhub.agent.entity.KnowledgeDocEntity;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
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
 * 二期替换为真实 HTTP 客户端（超时/异常 → 同样抛 LlmUnavailableException），调用方不变；
 * 新增 LlmClient 真实实现并设 demandhub.integration.llm.mock=false 即可切换。
 */
@Component
@ConditionalOnProperty(name = "demandhub.integration.llm.mock", havingValue = "true", matchIfMissing = true)
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

    /** 科技需求要素追问优先级（P10：title/content 走 missing 主流程，此处只跟踪扩展要素） */
    private static final List<String> TECH_ELEMENT_ORDER = List.of(
            "techSubtype", "businessScenario", "acceptanceCriteria", "valueImpact");

    /** 歧义词黑名单：命中即疑似 VAGUE（Wiegers：不可检验的形容词/副词） */
    private static final String[] VAGUE_WORDS = {"尽快", "好用", "方便", "优化一下", "越快越好", "体验", "满意", "顺便"};

    @Override
    public GuideChatResult chatSubmitGuide(String renderedPrompt, List<String> history, String userMessage,
                                           Map<String, Object> formContext,
                                           List<GuideChatResult.ElementStatus> prevElements) {
        requireAvailable();
        Map<String, Object> merged = new LinkedHashMap<>();
        // 语音转文字容错：清洗口语填充词后再抽取（那个/嗯/呃/就是 等）
        String cleaned = cleanFiller(userMessage);
        // 先放本轮抽取，再叠加表单已有值（用户手动编辑优先）
        Map<String, Object> extracted = extract(cleaned);
        merged.putAll(extracted);
        if (formContext != null) {
            formContext.forEach((k, v) -> {
                if ("ext".equals(k)) {
                    return; // ext 走深合并，避免表单快照整体覆盖本轮抽取的扩展字段
                }
                if (v != null && !String.valueOf(v).isBlank()) {
                    merged.put(k, v);
                }
            });
        }
        merged.put("ext", mergeExt(extracted.get("ext"), formContext == null ? null : formContext.get("ext")));
        // content 兜底：若描述为空且本轮输入够长，视为需求描述
        if (isBlank(merged.get("content")) && cleaned != null && cleaned.trim().length() >= 15
                && !isTitleLike(cleaned)) {
            merged.put("content", cleaned.trim());
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
        Map<String, Object> ext = asMap(merged.get("ext"));
        if (ext != null && !ext.isEmpty()) {
            structured.put("ext", ext);
        }

        // ---- P10：科技需求要素质量评估（rubric 四态 + 追问阶梯） ----
        boolean skipIntent = containsAny(cleaned == null ? "" : cleaned,
                "不知道", "跳过", "后续补充", "再说吧", "以后再说", "不清楚", "先这样");
        boolean isTech = "TECH".equals(String.valueOf(merged.getOrDefault("demandTypeCode", "")));
        List<GuideChatResult.ElementStatus> elements = isTech
                ? evaluateTechElements(merged, ext, prevElements, skipIntent)
                : List.of();

        List<String> quickReplies = new ArrayList<>();
        String reply;
        if (missing.contains("title")) {
            reply = "好的，我来帮你整理这个需求。先用一句话概括一下它吧，比如「代销看板增加机构持仓维度」——这就是需求标题。";
        } else if (missing.contains("demandTypeCode")) {
            reply = "明白，标题是「" + merged.get("title") + "」。这个需求属于哪一类？科技（系统功能/数据报表/接口）、物料（宣传品/印刷品）还是培训（课程/组织培训）？";
            quickReplies.addAll(List.of("科技需求", "物料需求", "培训需求"));
        } else if (missing.contains("content")) {
            String typeName = typeName(String.valueOf(merged.get("demandTypeCode")));
            reply = "好的，已按「" + typeName + "」需求准备。请描述一下业务背景、使用场景和期望效果，越具体越好，我会整理成需求描述。";
        } else if (isTech) {
            GuideChatResult.ElementStatus target = pickFollowUp(elements);
            if (target != null) {
                reply = followUpText(target, ext);
                quickReplies.addAll(quickRepliesFor(target));
            } else {
                reply = techSummaryText(merged, structured, elements);
            }
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
        return new GuideChatResult(reply, structured, missing, missing.isEmpty(), elements, quickReplies);
    }

    /** 语音口语填充词清洗（输入法语音转文字容错） */
    private String cleanFiller(String message) {
        if (message == null) {
            return null;
        }
        return message.replaceAll("(那个|嗯嗯|嗯|呃|额|就是呢|然后呢|的话呢)", "")
                .replaceAll("\\s{2,}", " ").trim();
    }

    /** ext 深合并：本轮抽取打底，表单快照按键覆盖（用户手填优先） */
    @SuppressWarnings("unchecked")
    private Map<String, Object> mergeExt(Object extractedExt, Object formExt) {
        Map<String, Object> merged = new LinkedHashMap<>();
        if (extractedExt instanceof Map<?, ?> m) {
            m.forEach((k, v) -> merged.put(String.valueOf(k), v));
        }
        if (formExt instanceof Map<?, ?> m) {
            m.forEach((k, v) -> {
                if (v != null && !String.valueOf(v).isBlank()) {
                    merged.put(String.valueOf(k), v);
                }
            });
        }
        return merged;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> asMap(Object v) {
        return v instanceof Map<?, ?> ? (Map<String, Object>) v : null;
    }

    /**
     * 科技需求要素质量评估：title/content/techSubtype/businessScenario/acceptanceCriteria/valueImpact 六要素。
     * SKIP 粘性继承上一轮；attempts 仅对上一轮追问目标计次（≥2 停止追问，标黄待补充）。
     */
    private List<GuideChatResult.ElementStatus> evaluateTechElements(Map<String, Object> merged,
                                                                     Map<String, Object> ext,
                                                                     List<GuideChatResult.ElementStatus> prevElements,
                                                                     boolean skipIntent) {
        Map<String, GuideChatResult.ElementStatus> prev = new HashMap<>();
        if (prevElements != null) {
            for (GuideChatResult.ElementStatus e : prevElements) {
                prev.put(e.key(), e);
            }
        }
        GuideChatResult.ElementStatus prevTarget = pickFollowUp(new ArrayList<>(prev.values()));

        List<GuideChatResult.ElementStatus> elements = new ArrayList<>();
        elements.add(evaluatePresence("title", merged.get("title"), prev, prevTarget, skipIntent));
        elements.add(evaluateContent(merged.get("content"), prev, prevTarget, skipIntent));
        elements.add(evaluatePresence("techSubtype", ext == null ? null : ext.get("techSubtype"), prev, prevTarget, skipIntent));
        elements.add(evaluateScenario(ext == null ? null : ext.get("businessScenario"), prev, prevTarget, skipIntent));
        elements.add(evaluateAcceptance(ext == null ? null : ext.get("acceptanceCriteria"), prev, prevTarget, skipIntent));
        elements.add(evaluateValueImpact(ext == null ? null : ext.get("valueImpact"), prev, prevTarget, skipIntent));
        return elements;
    }

    /** 统一封装：SKIP 粘性 + attempts 计次 */
    private GuideChatResult.ElementStatus buildStatus(String key, String status, String note,
                                                      Map<String, GuideChatResult.ElementStatus> prev,
                                                      GuideChatResult.ElementStatus prevTarget, boolean skipIntent) {
        GuideChatResult.ElementStatus p = prev.get(key);
        if (p != null && "SKIP".equals(p.status())) {
            return new GuideChatResult.ElementStatus(key, "SKIP", "用户选择后续补充", p.attempts());
        }
        if (skipIntent && prevTarget != null && prevTarget.key().equals(key) && !"OK".equals(status)) {
            return new GuideChatResult.ElementStatus(key, "SKIP", "用户选择后续补充", p == null ? 0 : p.attempts());
        }
        int attempts = 0;
        if (p != null && prevTarget != null && prevTarget.key().equals(key) && !"OK".equals(status)) {
            attempts = p.attempts() + 1;
        } else if (p != null && !"OK".equals(status)) {
            attempts = p.attempts();
        }
        return new GuideChatResult.ElementStatus(key, status, note, attempts);
    }

    private GuideChatResult.ElementStatus evaluatePresence(String key, Object value,
                                                           Map<String, GuideChatResult.ElementStatus> prev,
                                                           GuideChatResult.ElementStatus prevTarget, boolean skipIntent) {
        if (isBlank(value)) {
            return buildStatus(key, "MISSING", "未填写", prev, prevTarget, skipIntent);
        }
        return buildStatus(key, "OK", "", prev, prevTarget, skipIntent);
    }

    private GuideChatResult.ElementStatus evaluateContent(Object value,
                                                          Map<String, GuideChatResult.ElementStatus> prev,
                                                          GuideChatResult.ElementStatus prevTarget, boolean skipIntent) {
        if (isBlank(value)) {
            return buildStatus("content", "MISSING", "未填写", prev, prevTarget, skipIntent);
        }
        if (String.valueOf(value).trim().length() < 10) {
            return buildStatus("content", "VAGUE", "描述过短，缺业务背景与期望效果", prev, prevTarget, skipIntent);
        }
        return buildStatus("content", "OK", "", prev, prevTarget, skipIntent);
    }

    /** 业务场景到位线：≥15字、含角色或时机词、无歧义词 */
    private GuideChatResult.ElementStatus evaluateScenario(Object value,
                                                           Map<String, GuideChatResult.ElementStatus> prev,
                                                           GuideChatResult.ElementStatus prevTarget, boolean skipIntent) {
        if (isBlank(value)) {
            return buildStatus("businessScenario", "MISSING", "未填写", prev, prevTarget, skipIntent);
        }
        String s = String.valueOf(value);
        if (containsAny(s, VAGUE_WORDS) || s.trim().length() < 15) {
            return buildStatus("businessScenario", "VAGUE", "缺角色/时机/任务中的至少一项", prev, prevTarget, skipIntent);
        }
        if (!containsAny(s, "每天", "每周", "每月", "每次", "当", "时", "晨会", "月底", "季",
                "客户经理", "理财经理", "专员", "机构", "营业部", "部门", "经理", "同事")) {
            return buildStatus("businessScenario", "VAGUE", "看不出谁在用、什么时候用", prev, prevTarget, skipIntent);
        }
        return buildStatus("businessScenario", "OK", "", prev, prevTarget, skipIntent);
    }

    /** 验收标准到位线：含量化指标（数字/时间/误差/通过率）或明确检查项，无歧义词 */
    private GuideChatResult.ElementStatus evaluateAcceptance(Object value,
                                                             Map<String, GuideChatResult.ElementStatus> prev,
                                                             GuideChatResult.ElementStatus prevTarget, boolean skipIntent) {
        if (isBlank(value)) {
            return buildStatus("acceptanceCriteria", "MISSING", "未填写", prev, prevTarget, skipIntent);
        }
        String s = String.valueOf(value);
        if (containsAny(s, VAGUE_WORDS)) {
            return buildStatus("acceptanceCriteria", "VAGUE", "只有形容词，无法检验", prev, prevTarget, skipIntent);
        }
        boolean hasMetric = s.matches(".*\\d.*") || containsAny(s, "误差", "对账", "通过率", "准确率", "检查", "为准", "一致");
        if (!hasMetric) {
            return buildStatus("acceptanceCriteria", "VAGUE", "缺可量化的验收指标", prev, prevTarget, skipIntent);
        }
        return buildStatus("acceptanceCriteria", "OK", "", prev, prevTarget, skipIntent);
    }

    /** 价值与影响到位线：含量化事实（多少人/多少时间/什么后果） */
    private GuideChatResult.ElementStatus evaluateValueImpact(Object value,
                                                              Map<String, GuideChatResult.ElementStatus> prev,
                                                              GuideChatResult.ElementStatus prevTarget, boolean skipIntent) {
        if (isBlank(value)) {
            return buildStatus("valueImpact", "MISSING", "未填写", prev, prevTarget, skipIntent);
        }
        String s = String.valueOf(value);
        if (!s.matches(".*\\d.*") && !containsAny(s, "不做", "否则", "影响", "风险")) {
            return buildStatus("valueImpact", "VAGUE", "缺量化事实（人数/时长/后果）", prev, prevTarget, skipIntent);
        }
        return buildStatus("valueImpact", "OK", "", prev, prevTarget, skipIntent);
    }

    /** 取下一个追问目标：按优先级第一个非 OK/SKIP 且 attempts<2 的要素（≥2 次放弃追问，标黄待补充） */
    private GuideChatResult.ElementStatus pickFollowUp(List<GuideChatResult.ElementStatus> elements) {
        if (elements == null || elements.isEmpty()) {
            return null;
        }
        for (String key : TECH_ELEMENT_ORDER) {
            for (GuideChatResult.ElementStatus e : elements) {
                if (e.key().equals(key) && !"OK".equals(e.status()) && !"SKIP".equals(e.status())
                        && e.attempts() < 2) {
                    return e;
                }
            }
        }
        // title/content 不在此处追问（走 missing 主流程），其余要素全部 OK/SKIP/放弃 → null
        return null;
    }

    /** 追问话术阶梯：L1 复述+指出缺什么 → L2 给句式模板和示例；MISSING 直接提问 */
    private String followUpText(GuideChatResult.ElementStatus target, Map<String, Object> ext) {
        String key = target.key();
        boolean l2 = target.attempts() >= 1;
        boolean missing = "MISSING".equals(target.status());
        String current = ext == null ? "" : String.valueOf(ext.getOrDefault(key, ""));
        String snippet = current.length() > 20 ? current.substring(0, 20) + "…" : current;
        return switch (key) {
            case "techSubtype" -> "为了让承接团队更准确评估，这个科技需求更接近哪一类？\n"
                        + "· 系统开发：加功能/改流程\n· 数据报表：看数/取数/导出\n"
                        + "· 系统集成：和其他系统对接\n· 运维优化：现有功能提速/修问题";
            case "businessScenario" -> {
                if (missing) {
                    yield "好的。再说说使用场景吧：谁（角色）、在什么时间/频率、用它来做什么？\n"
                            + "比如「机构业务部客户经理，每天晨会前查各机构持仓」。";
                }
                if (!l2) {
                    yield "记下了。不过「" + snippet + "」还有点概括——为了承接方能准确理解，"
                            + "能再具体说说哪些人、在什么时机用吗？比如「20多个客户经理，每天8点半晨会前」。";
                }
                yield "可以这样写：「作为__（角色），在__（时间/频率），需要__（做什么）」。\n"
                        + "示例：作为机构业务部专员，每周一早上，需要汇总各渠道销量。";
            }
            case "acceptanceCriteria" -> {
                if (missing) {
                    yield "怎样算这个需求做完了？给一个可检查的标准，排期和验收都靠它。\n"
                            + "比如「连续一周与核心系统对账误差为0」或「8:30前能查到前一交易日数据」。";
                }
                if (!l2) {
                    yield "「" + snippet + "」还不太可检验——能加个量化指标吗？"
                            + "比如时间（几点前/多少秒内）、准确率（误差=0）或覆盖范围。";
                }
                yield "参考句式：「当__时，系统应__；检查项：①__②__」。\n"
                        + "示例：当客户经理晨会查询时，3秒内返回；检查项：①数据与核心系统一致②支持导出Excel。";
            }
            case "valueImpact" -> {
                if (missing) {
                    yield "这个需求不做的话有什么影响？量化一下，评审排期时更有说服力。\n"
                            + "比如「20多个客户经理每人每天花40分钟手工整理，还容易出错」。";
                }
                if (!l2) {
                    yield "再具体一点点：大概影响多少人或几个部门？每次能省多少时间，或者不做的后果是什么？";
                }
                yield "参考句式：「影响__人/__个部门，每次节省约__分钟；不做会__」。";
            }
            default -> "还有什么要补充的吗？";
        };
    }

    /** 选项类问题与 L3 逃生门（快捷回复 chips） */
    private List<String> quickRepliesFor(GuideChatResult.ElementStatus target) {
        List<String> replies = new ArrayList<>();
        if ("techSubtype".equals(target.key())) {
            replies.add("系统开发");
            replies.add("数据报表");
            replies.add("系统集成");
            replies.add("运维优化");
        }
        if (target.attempts() >= 1) {
            replies.add("后续补充");
        }
        return replies;
    }

    /** 信息齐备（或仅剩待补充项）时的要素清单回显 */
    private String techSummaryText(Map<String, Object> merged, Map<String, Object> structured,
                                   List<GuideChatResult.ElementStatus> elements) {
        Map<String, String> labels = Map.of(
                "techSubtype", "需求子类", "businessScenario", "业务场景",
                "acceptanceCriteria", "验收标准", "valueImpact", "价值与影响");
        StringBuilder sb = new StringBuilder("我整理好了，理解到的关键信息如下：\n");
        sb.append("· 标题：").append(merged.get("title")).append('\n');
        sb.append("· 类型：科技需求\n");
        sb.append("· 紧急程度：").append(urgencyName(String.valueOf(structured.get("urgency"))));
        if (!merged.containsKey("urgency")) {
            sb.append("（未提及，默认普通，可改）");
        }
        sb.append('\n');
        List<String> yellow = new ArrayList<>();
        for (GuideChatResult.ElementStatus e : elements) {
            String label = labels.get(e.key());
            if (label == null) {
                continue;
            }
            if ("OK".equals(e.status())) {
                sb.append("· ").append(label).append("：已理解\n");
            } else if (!"SKIP".equals(e.status())) {
                yellow.add(label);
            }
        }
        if (!yellow.isEmpty()) {
            sb.append("\n「").append(String.join("」「", yellow)).append("」还不够具体，已标为待补充；")
                    .append("可以现在补两句，也可以先提交，受理时经理会再和你确认。\n");
        }
        sb.append("\n字段已自动回填到左侧表单，如有理解偏差请直接改表单或告诉我；确认无误后点「提交需求」即可。");
        return sb.toString();
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
        // 科技子类识别（P10：顺序敏感，报表/集成/运维优先于泛化的"功能/开发"）
        if (containsAny(m, "数据报表", "报表", "看板", "取数", "口径", "大屏", "导出", "数据")) {
            ext.put("techSubtype", "DATA_RPT");
        } else if (containsAny(m, "系统集成", "接口", "对接", "集成", "推送", "打通")) {
            ext.put("techSubtype", "SYS_INT");
        } else if (containsAny(m, "运维优化", "优化", "太慢", "很卡", "卡顿", "提速", "运维", "性能", "故障")) {
            ext.put("techSubtype", "OPS_OPT");
        } else if (containsAny(m, "系统开发", "功能", "开发", "新增", "增加", "改造")) {
            ext.put("techSubtype", "SYS_DEV");
        }
        if (containsAny(m, "代销")) {
            ext.put("relatedSystem", "代销系统");
        } else if (containsAny(m, "直销")) {
            ext.put("relatedSystem", "直销系统");
        } else if (containsAny(m, "估值")) {
            ext.put("relatedSystem", "估值系统");
        } else if (containsAny(m, "CRM", "crm")) {
            ext.put("relatedSystem", "CRM");
        } else if (containsAny(m, "数据中心")) {
            ext.put("relatedSystem", "数据中心");
        }
        if (containsAny(m, "看板", "报表", "数据")) {
            ext.put("relatedModule", "数据看板");
        }
        // 长文本句级要素抽取（P10：一段话/语音整段解析）
        extractSentences(m, ext);
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

    /**
     * 长文本句级要素抽取（P10）：按句切分，命中特征词的句子归类到对应要素。
     * 场景句=含角色/时机词；验收句=含对账/误差/通过率等；价值句=含量化事实（数字+效率词）。
     */
    private void extractSentences(String m, Map<String, Object> ext) {
        if (m == null || m.trim().length() < 30) {
            return;
        }
        String[] sentences = m.split("[。！？!?；;\\n]+");
        StringBuilder scenario = new StringBuilder();
        for (String raw : sentences) {
            String s = raw.trim();
            if (s.isEmpty()) {
                continue;
            }
            if (!ext.containsKey("businessScenario") && scenario.length() < 60
                    && containsAny(s, "每天", "每周", "每月", "每次", "晨会", "月底", "季末",
                    "客户经理", "理财经理", "专员", "机构业务", "营业部", "当")) {
                scenario.append(s).append('。');
                if (scenario.length() >= 15) {
                    ext.put("businessScenario", scenario.toString());
                }
            }
            if (!ext.containsKey("acceptanceCriteria")
                    && containsAny(s, "验收", "误差", "对账", "通过率", "准确率", "就算", "为准")) {
                ext.put("acceptanceCriteria", s);
            }
            if (!ext.containsKey("valueImpact") && s.matches(".*\\d.*")
                    && containsAny(s, "节省", "手工", "分钟", "小时", "效率", "加班", "人手", "耗时")) {
                ext.put("valueImpact", s);
            }
        }
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
