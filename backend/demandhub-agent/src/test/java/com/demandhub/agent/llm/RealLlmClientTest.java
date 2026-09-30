package com.demandhub.agent.llm;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * RealLlmClient 契约单测（P11）：MockWebServer 模拟火山方舟 OpenAI 兼容接口。
 * 覆盖：正常 JSON mode 响应、要素状态归一、非 JSON 重试一次后降级、HTTP 500 快速失败、
 * 连续失败达阈值进入冷却（冷却期不再发请求）、embedding 解析与降级。
 */
class RealLlmClientTest {

    private MockWebServer server;
    private RealLlmClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
        // 每用例新实例：失败计数/冷却状态实例级隔离；冷却参数调小便于断言
        client = new RealLlmClient(new LlmSwitch(true),
                server.url("").toString().replaceAll("/$", ""),
                "ark-test-key", "chat-model-ep", "embed-model-ep", false,
                1000, 3000, 2000, 0.3, 3, 200);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    private void enqueueChat(String contentJson) {
        server.enqueue(new MockResponse().setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"choices\":[{\"message\":{\"role\":\"assistant\",\"content\":"
                        + toJsonString(contentJson) + "}}]}"));
    }

    /** content 是嵌套 JSON 字符串，需整体转义 */
    private String toJsonString(String raw) {
        StringBuilder sb = new StringBuilder("\"");
        for (char c : raw.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                default -> sb.append(c);
            }
        }
        return sb.append('"').toString();
    }

    @Test
    void guideChat_parsesJsonModeResponse() throws InterruptedException {
        enqueueChat("{\"reply\":\"我先了解下场景\",\"structured\":{\"title\":\"代销报表\",\"ext\":{\"techSubtype\":\"DATA_RPT\"}},"
                + "\"missing\":[\"content\"],\"ready\":false,"
                + "\"elements\":[{\"key\":\"title\",\"status\":\"OK\",\"note\":\"具体\",\"attempts\":0},"
                + "{\"key\":\"content\",\"status\":\"MISSING\",\"note\":\"未填\",\"attempts\":0}],"
                + "\"quickReplies\":[\"系统开发\",\"数据报表\"]}");

        GuideChatResult result = client.chatSubmitGuide("系统提示词",
                List.of("USER: 我想做个报表", "ASSISTANT: 哪类报表？"),
                "代销业绩的", Map.of("title", ""), List.of());

        assertEquals("我先了解下场景", result.reply());
        assertEquals("代销报表", result.structured().get("title"));
        assertEquals(Map.of("techSubtype", "DATA_RPT"), result.structured().get("ext"));
        assertEquals(List.of("content"), result.missing());
        assertFalse(result.ready());
        assertEquals(2, result.elements().size());
        assertEquals("OK", result.elements().get(0).status());
        assertEquals(List.of("系统开发", "数据报表"), result.quickReplies());

        RecordedRequest req = server.takeRequest(1, TimeUnit.SECONDS);
        assertEquals("/chat/completions", req.getPath());
        assertEquals("Bearer ark-test-key", req.getHeader("Authorization"));
        String body = req.getBody().readUtf8();
        assertTrue(body.contains("\"response_format\":{\"type\":\"json_object\"}"));
        assertTrue(body.contains("\"chat-model-ep\""));
        // 历史前缀格式被拆为 role/content
        assertTrue(body.contains("\\\"role\\\":\\\"assistant\\\"".replace("\\\"", "\"")));
    }

    @Test
    void guideChat_normalizesUnknownElementStatus() {
        enqueueChat("{\"reply\":\"嗯\",\"structured\":{},\"missing\":[],\"ready\":false,"
                + "\"elements\":[{\"key\":\"content\",\"status\":\"GOOD\",\"note\":\"\",\"attempts\":-2}],\"quickReplies\":[]}");
        GuideChatResult result = client.chatSubmitGuide("p", List.of(), "随便说说", Map.of(), List.of());
        assertEquals("VAGUE", result.elements().get(0).status());
        assertEquals(0, result.elements().get(0).attempts());
    }

    @Test
    void guideChat_retriesOnceOnNonJsonThenDegrades() throws InterruptedException {
        enqueueChat("这不是 JSON");
        enqueueChat("依然不是 JSON");
        assertThrows(LlmUnavailableException.class,
                () -> client.chatSubmitGuide("p", List.of(), "你好", Map.of(), List.of()));
        // 恰好重试一次：两个请求
        assertEquals(2, server.getRequestCount());
    }

    @Test
    void guideChat_http500FailsFastAndCooldownAfterThreshold() {
        for (int i = 0; i < 3; i++) {
            server.enqueue(new MockResponse().setResponseCode(500).setBody("{\"error\":\"boom\"}"));
        }
        for (int i = 0; i < 3; i++) {
            assertThrows(LlmUnavailableException.class,
                    () -> client.chatSubmitGuide("p", List.of(), "你好", Map.of(), List.of()));
        }
        // 连续 3 次失败 → 进入冷却：第 4 次不再发请求直接降级
        assertEquals(3, server.getRequestCount());
        assertFalse(client.available());
        assertThrows(LlmUnavailableException.class,
                () -> client.chatSubmitGuide("p", List.of(), "你好", Map.of(), List.of()));
        assertEquals(3, server.getRequestCount());
    }

    @Test
    void generateQuestions_requiresNonEmptyList() {
        enqueueChat("{\"questions\":[\"角色与频次？\",\"数据口径谁确认？\"]}");
        List<String> questions = client.generateQuestions("prompt", null, List.of());
        assertEquals(2, questions.size());

        enqueueChat("{\"questions\":[]}");
        assertThrows(LlmUnavailableException.class,
                () -> client.generateQuestions("prompt", null, List.of()));
    }

    @Test
    void generateSolutionDraft_requiresBothContents() {
        enqueueChat("{\"specContent\":\"需求理解\",\"solutionContent\":\"方案初稿\"}");
        LlmClient.SolutionDraftContent draft = client.generateSolutionDraft("prompt", null, List.of());
        assertEquals("需求理解", draft.specContent());
        assertEquals("方案初稿", draft.solutionContent());

        enqueueChat("{\"specContent\":\"只有一半\"}");
        assertThrows(LlmUnavailableException.class,
                () -> client.generateSolutionDraft("prompt", null, List.of()));
    }

    @Test
    void embed_parsesVector() throws InterruptedException {
        server.enqueue(new MockResponse().setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"data\":[{\"embedding\":[0.1,0.2,0.3]}]}"));
        double[] vec = client.embed("测试文本");
        assertEquals(3, vec.length);
        assertEquals(0.2, vec[1], 0.0001);

        RecordedRequest req = server.takeRequest(1, TimeUnit.SECONDS);
        assertEquals("/embeddings", req.getPath());
        assertTrue(req.getBody().readUtf8().contains("\"embed-model-ep\""));
    }

    @Test
    void embed_missingDataDegrades() {
        server.enqueue(new MockResponse().setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"data\":[]}"));
        assertThrows(LlmUnavailableException.class, () -> client.embed("x"));
    }

    @Test
    void embed_multimodalPathAndObjectData() throws InterruptedException {
        RealLlmClient mm = new RealLlmClient(new LlmSwitch(true),
                server.url("").toString().replaceAll("/$", ""),
                "ark-test-key", "chat-model-ep", "embed-model-ep", true,
                1000, 3000, 2000, 0.3, 3, 200);
        // 多模态接口：data 为对象（非数组）
        server.enqueue(new MockResponse().setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"created\":1,\"data\":{\"embedding\":[0.5,0.6]},\"model\":\"m\",\"object\":\"embedding\"}"));
        double[] vec = mm.embed("测试文本");
        assertEquals(2, vec.length);
        assertEquals(0.5, vec[0], 0.0001);

        RecordedRequest req = server.takeRequest(1, TimeUnit.SECONDS);
        assertEquals("/embeddings/multimodal", req.getPath());
        String body = req.getBody().readUtf8();
        assertTrue(body.contains("\"type\":\"text\""));
        assertTrue(body.contains("测试文本"));
    }

    @Test
    void unavailableWhenSwitchOffOrKeyBlank() {
        RealLlmClient off = new RealLlmClient(new LlmSwitch(false),
                "http://localhost", "key", "c", "e", false, 100, 100, 100, 0.3, 3, 100);
        assertFalse(off.available());

        RealLlmClient noKey = new RealLlmClient(new LlmSwitch(true),
                "http://localhost", "", "c", "e", false, 100, 100, 100, 0.3, 3, 100);
        assertFalse(noKey.available());
    }
}
