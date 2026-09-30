package com.demandhub.agent.llm;

import com.demandhub.agent.entity.DemandView;
import com.demandhub.agent.entity.KnowledgeDocEntity;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 火山方舟大模型客户端（OpenAI 兼容协议，REST 直连，无 SDK 依赖）。
 * chat 三方法走 /chat/completions + JSON mode（response_format=json_object，方舟对 DeepSeek/Doubao 均支持）；
 * embed 走 /embeddings。配置见 application.yml demandhub.agent.llm.ark.*。
 * 降级策略与 Mock 一致：超时/5xx/解析失败 → {@link LlmUnavailableException}（1401，前端降级为手动流程）；
 * 连续失败达阈值进入冷却期，期间直接降级不打平台，冷却结束自动恢复探测。
 */
@Slf4j
@Component
@ConditionalOnProperty(name = "demandhub.integration.llm.mock", havingValue = "false")
public class RealLlmClient implements LlmClient {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /** 送入模型的会话历史上限（控制 token 消耗） */
    private static final int HISTORY_LIMIT = 20;

    private final LlmSwitch llmSwitch;
    private final RestClient http;
    private final String apiKey;
    private final String chatModel;
    private final String embeddingModel;
    /** true=多模态向量接口（/embeddings/multimodal，data 为对象，vision 类模型）；false=标准文本向量接口（/embeddings，data 为数组） */
    private final boolean embeddingMultimodal;
    private final int maxTokens;
    private final double temperature;
    private final int failureThreshold;
    private final long failureCooldownMs;

    private final AtomicInteger consecutiveFailures = new AtomicInteger();
    private volatile long cooldownUntilMs;

    public RealLlmClient(LlmSwitch llmSwitch,
                         @Value("${demandhub.agent.llm.ark.base-url}") String baseUrl,
                         @Value("${demandhub.agent.llm.ark.api-key:}") String apiKey,
                         @Value("${demandhub.agent.llm.ark.chat-model}") String chatModel,
                         @Value("${demandhub.agent.llm.ark.embedding-model}") String embeddingModel,
                         @Value("${demandhub.agent.llm.ark.embedding-multimodal:true}") boolean embeddingMultimodal,
                         @Value("${demandhub.agent.llm.ark.connect-timeout-ms:3000}") int connectTimeoutMs,
                         @Value("${demandhub.agent.llm.ark.read-timeout-ms:30000}") int readTimeoutMs,
                         @Value("${demandhub.agent.llm.ark.max-tokens:2000}") int maxTokens,
                         @Value("${demandhub.agent.llm.ark.temperature:0.3}") double temperature,
                         @Value("${demandhub.agent.llm.ark.failure-threshold:3}") int failureThreshold,
                         @Value("${demandhub.agent.llm.ark.failure-cooldown-ms:60000}") long failureCooldownMs) {
        this.llmSwitch = llmSwitch;
        this.apiKey = apiKey;
        this.chatModel = chatModel;
        this.embeddingModel = embeddingModel;
        this.embeddingMultimodal = embeddingMultimodal;
        this.maxTokens = maxTokens;
        this.temperature = temperature;
        this.failureThreshold = failureThreshold;
        this.failureCooldownMs = failureCooldownMs;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeoutMs);
        factory.setReadTimeout(readTimeoutMs);
        this.http = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                .build();
    }

    /** 平台可用 = 管理端开关打开 + 密钥已配置 + 不在失败冷却期 */
    @Override
    public boolean available() {
        return llmSwitch.available() && apiKey != null && !apiKey.isBlank()
                && System.currentTimeMillis() >= cooldownUntilMs;
    }

    private void requireAvailable() {
        if (!available()) {
            throw new LlmUnavailableException();
        }
    }

    @Override
    public GuideChatResult chatSubmitGuide(String renderedPrompt, List<String> history, String userMessage,
                                           Map<String, Object> formContext,
                                           List<GuideChatResult.ElementStatus> prevElements) {
        requireAvailable();
        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(Map.of("role", "system", "content", renderedPrompt));
        if (history != null) {
            List<String> recent = history.size() > HISTORY_LIMIT
                    ? history.subList(history.size() - HISTORY_LIMIT, history.size()) : history;
            for (String h : recent) {
                messages.add(parseHistoryMessage(h));
            }
        }
        // 表单快照与上一轮要素状态随本轮输入一起给出（prompt 中约定读取位置）
        StringBuilder user = new StringBuilder(userMessage);
        user.append("\n\n【当前表单快照(JSON)】\n").append(writeJson(formContext == null ? Map.of() : formContext));
        if (prevElements != null && !prevElements.isEmpty()) {
            user.append("\n【上一轮要素状态(JSON)】\n").append(writeJson(prevElements));
        }
        messages.add(Map.of("role", "user", "content", user.toString()));

        JsonNode content = callChatJson(messages, true);
        return toGuideChatResult(content);
    }

    @Override
    public List<String> generateQuestions(String renderedPrompt, DemandView demand, List<KnowledgeDocEntity> similarDocs) {
        requireAvailable();
        JsonNode node = callChatJson(singleTurn(renderedPrompt), true);
        List<String> questions = new ArrayList<>();
        node.path("questions").forEach(q -> {
            if (q.isTextual() && !q.asText().isBlank()) {
                questions.add(q.asText().trim());
            }
        });
        if (questions.isEmpty()) {
            onFailure("响应 JSON 缺少非空 questions");
            throw new LlmUnavailableException();
        }
        return questions;
    }

    @Override
    public SolutionDraftContent generateSolutionDraft(String renderedPrompt, DemandView demand,
                                                      List<KnowledgeDocEntity> similarDocs) {
        requireAvailable();
        JsonNode node = callChatJson(singleTurn(renderedPrompt), true);
        String spec = node.path("specContent").asText("");
        String solution = node.path("solutionContent").asText("");
        if (spec.isBlank() || solution.isBlank()) {
            onFailure("响应 JSON 缺少 specContent/solutionContent");
            throw new LlmUnavailableException();
        }
        return new SolutionDraftContent(spec, solution);
    }

    /** POST 并按原始字节读取（方舟部分响应对 Java 客户端不带 Content-Type，避免消息转换器协商失败） */
    private String postForRawBody(String uri, Map<String, Object> payload) throws Exception {
        byte[] bytes = http.post()
                .uri(uri)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(payload)
                .retrieve()
                .body(byte[].class);
        return bytes == null ? "" : new String(bytes, StandardCharsets.UTF_8);
    }

    @Override
    public double[] embed(String text) {
        requireAvailable();
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("model", embeddingModel);
        // vision 类模型走多模态接口：input 为类型化内容部件数组
        payload.put("input", embeddingMultimodal
                ? List.of(Map.of("type", "text", "text", text == null ? "" : text))
                : (text == null ? "" : text));
        String uri = embeddingMultimodal ? "/embeddings/multimodal" : "/embeddings";
        String raw = "";
        try {
            raw = postForRawBody(uri, payload);
            JsonNode resp = MAPPER.readTree(raw);
            // 多模态接口 data 为对象，标准接口 data 为数组
            JsonNode arr = resp == null ? null
                    : (embeddingMultimodal ? resp.path("data").path("embedding")
                                           : resp.path("data").path(0).path("embedding"));
            if (arr == null || !arr.isArray() || arr.isEmpty()) {
                onFailure("embedding 响应缺少 data[0].embedding");
                throw new LlmUnavailableException();
            }
            double[] vec = new double[arr.size()];
            for (int i = 0; i < arr.size(); i++) {
                vec[i] = arr.get(i).asDouble();
            }
            onSuccess();
            return vec;
        } catch (LlmUnavailableException e) {
            throw e;
        } catch (Exception e) {
            onFailure(e.getClass().getSimpleName() + ": " + e.getMessage() + " | body=" + abbreviate(raw), e);
            throw new LlmUnavailableException();
        }
    }

    // ---------------- 内部 ----------------

    /** "ROLE: content" 前缀格式历史 → OpenAI 消息；无前缀按 user 兜底 */
    private Map<String, String> parseHistoryMessage(String raw) {
        int idx = raw.indexOf(':');
        if (idx > 0) {
            String role = raw.substring(0, idx).trim().toLowerCase();
            if ("user".equals(role) || "assistant".equals(role) || "system".equals(role)) {
                return Map.of("role", role, "content", raw.substring(idx + 1).trim());
            }
        }
        return Map.of("role", "user", "content", raw);
    }

    /** 单轮对话消息（处理辅助两方法：prompt 模板已自含需求与相似文档上下文） */
    private List<Map<String, String>> singleTurn(String userContent) {
        List<Map<String, String>> messages = new ArrayList<>();
        messages.add(Map.of("role", "system", "content", "你是 DemandHub 的需求处理助手，仅输出 JSON。"));
        messages.add(Map.of("role", "user", "content", userContent));
        return messages;
    }

    /** 调 chat/completions 并把 content 解析为 JSON；解析失败重试一次，再失败降级 */
    private JsonNode callChatJson(List<Map<String, String>> messages, boolean allowRetry) {
        String body = chatOnce(messages);
        try {
            return MAPPER.readTree(body);
        } catch (Exception e) {
            if (allowRetry) {
                log.warn("[LLM] 响应非 JSON，重试一次：{}", abbreviate(body));
                return callChatJson(messages, false);
            }
            onFailure("响应 JSON 解析失败");
            throw new LlmUnavailableException();
        }
    }

    private String chatOnce(List<Map<String, String>> messages) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("model", chatModel);
        payload.put("messages", messages);
        payload.put("temperature", temperature);
        payload.put("max_tokens", maxTokens);
        payload.put("response_format", Map.of("type", "json_object"));
        String raw = "";
        try {
            raw = postForRawBody("/chat/completions", payload);
            JsonNode resp = MAPPER.readTree(raw);
            JsonNode content = resp == null ? null : resp.path("choices").path(0).path("message").path("content");
            if (content == null || content.isMissingNode() || content.asText().isBlank()) {
                onFailure("响应缺少 choices[0].message.content | body=" + abbreviate(raw));
                throw new LlmUnavailableException();
            }
            onSuccess();
            return content.asText();
        } catch (LlmUnavailableException e) {
            throw e;
        } catch (Exception e) {
            onFailure(e.getClass().getSimpleName() + ": " + e.getMessage() + " | body=" + abbreviate(raw), e);
            throw new LlmUnavailableException();
        }
    }

    /** 模型 JSON → GuideChatResult（容错：缺省字段给默认值；reply 为空视为失败） */
    private GuideChatResult toGuideChatResult(JsonNode node) {
        String reply = node.path("reply").asText("");
        if (reply.isBlank()) {
            onFailure("响应 JSON 缺少非空 reply");
            throw new LlmUnavailableException();
        }
        Map<String, Object> structured = new LinkedHashMap<>();
        JsonNode s = node.path("structured");
        if (s.isObject()) {
            for (Iterator<Map.Entry<String, JsonNode>> it = s.fields(); it.hasNext(); ) {
                Map.Entry<String, JsonNode> e = it.next();
                // 空值不回填，避免覆盖用户手填
                if (!e.getValue().isNull() && !(e.getValue().isTextual() && e.getValue().asText().isBlank())) {
                    structured.put(e.getKey(), MAPPER.convertValue(e.getValue(), Object.class));
                }
            }
        }
        List<String> missing = new ArrayList<>();
        node.path("missing").forEach(m -> {
            if (m.isTextual()) {
                missing.add(m.asText());
            }
        });
        boolean ready = node.path("ready").asBoolean(false) && missing.isEmpty();
        List<GuideChatResult.ElementStatus> elements = new ArrayList<>();
        node.path("elements").forEach(e -> elements.add(new GuideChatResult.ElementStatus(
                e.path("key").asText(""),
                normalizeStatus(e.path("status").asText("")),
                e.path("note").asText(""),
                Math.max(0, e.path("attempts").asInt(0)))));
        List<String> quickReplies = new ArrayList<>();
        node.path("quickReplies").forEach(q -> {
            if (q.isTextual() && !q.asText().isBlank()) {
                quickReplies.add(q.asText());
            }
        });
        return new GuideChatResult(reply, structured, missing, ready, elements, quickReplies);
    }

    /** 模型返回的非法要素状态归一为 VAGUE（宁可标黄也不丢要素） */
    private String normalizeStatus(String status) {
        return switch (status == null ? "" : status.toUpperCase()) {
            case "OK", "VAGUE", "MISSING", "SKIP" -> status.toUpperCase();
            default -> "VAGUE";
        };
    }

    private void onSuccess() {
        consecutiveFailures.set(0);
    }

    private void onFailure(String reason) {
        onFailure(reason, null);
    }

    private void onFailure(String reason, Throwable cause) {
        int failures = consecutiveFailures.incrementAndGet();
        String causeMsg = cause == null ? "" : " | cause=" + cause.getClass().getSimpleName() + ": " + cause.getMessage();
        log.warn("[LLM] 平台调用失败（连续第 {} 次）：{}{}", failures, reason, causeMsg);
        if (failures >= failureThreshold) {
            cooldownUntilMs = System.currentTimeMillis() + failureCooldownMs;
            consecutiveFailures.set(0);
            log.warn("[LLM] 连续失败达阈值，进入 {}ms 冷却降级", failureCooldownMs);
        }
    }

    private String writeJson(Object obj) {
        try {
            return MAPPER.writeValueAsString(obj);
        } catch (Exception e) {
            return "{}";
        }
    }

    private String abbreviate(String text) {
        return text == null ? "" : text.substring(0, Math.min(text.length(), 200));
    }
}
