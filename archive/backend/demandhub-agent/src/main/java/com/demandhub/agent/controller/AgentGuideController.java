package com.demandhub.agent.controller;

import com.demandhub.agent.llm.GuideChatResult;
import com.demandhub.agent.service.AgentGuideService;
import com.demandhub.common.core.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 提报启发 Agent（FR-M9-01）：多轮对话 → 结构化字段回填表单。
 * /chat 一次性返回（降级/调试用）；/chat/stream SSE 流式返回（正式入口）。
 * 大模型不可用时同步抛 1401（统一返回体），前端识别后显示降级提示，提报主流程不受影响。
 */
@Slf4j
@Tag(name = "Agent-提报启发")
@RestController
@RequestMapping("/agent/guide")
public class AgentGuideController {

    private final AgentGuideService guideService;
    private final int chunkSize;
    private final long thinkDelayMs;
    private final ExecutorService streamExecutor = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "agent-guide-stream");
        t.setDaemon(true);
        return t;
    });

    public AgentGuideController(AgentGuideService guideService,
                                @Value("${demandhub.agent.llm.chunk-size:6}") int chunkSize,
                                @Value("${demandhub.agent.llm.think-delay-ms:150}") long thinkDelayMs) {
        this.guideService = guideService;
        this.chunkSize = Math.max(1, chunkSize);
        this.thinkDelayMs = Math.max(0, thinkDelayMs);
    }

    public record GuideChatRequest(Long sessionId, String message, Map<String, Object> formContext) {
    }

    @Operation(summary = "提报启发对话（一次性返回）")
    @PostMapping("/chat")
    public Result<GuideChatResult> chat(@RequestBody GuideChatRequest request) {
        return Result.ok(guideService.chat(request.sessionId(), request.message(), request.formContext()));
    }

    @Operation(summary = "提报启发对话（SSE 流式）",
            description = "事件：message={delta} 文本分片；structured={structured,missing,ready} 结构化回填；done 结束")
    @PostMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chatStream(@RequestBody GuideChatRequest request) {
        // 同步完成对话编排（Mock 很快）：不可用/参数错误 → 全局异常处理返回统一 JSON（如 1401 降级）
        GuideChatResult result = guideService.chat(request.sessionId(), request.message(), request.formContext());
        SseEmitter emitter = new SseEmitter(Duration.ofMinutes(2).toMillis());
        streamExecutor.execute(() -> streamReply(emitter, result));
        return emitter;
    }

    /** 分片回放回复，模拟真实流式体验（一期 Mock） */
    private void streamReply(SseEmitter emitter, GuideChatResult result) {
        try {
            if (thinkDelayMs > 0) {
                Thread.sleep(thinkDelayMs);
            }
            String reply = result.reply() == null ? "" : result.reply();
            for (int i = 0; i < reply.length(); i += chunkSize) {
                String delta = reply.substring(i, Math.min(i + chunkSize, reply.length()));
                emitter.send(SseEmitter.event().name("message").data(Map.of("delta", delta)));
                Thread.sleep(25);
            }
            emitter.send(SseEmitter.event().name("structured").data(Map.of(
                    "structured", result.structured() == null ? Map.of() : result.structured(),
                    "missing", result.missing() == null ? java.util.List.of() : result.missing(),
                    "ready", result.ready(),
                    "elements", result.elements() == null ? java.util.List.of() : result.elements(),
                    "quickReplies", result.quickReplies() == null ? java.util.List.of() : result.quickReplies())));
            emitter.send(SseEmitter.event().name("done").data(""));
            emitter.complete();
        } catch (Exception e) {
            log.warn("[AgentGuide] SSE 推送中断: {}", e.getMessage());
            emitter.completeWithError(e);
        }
    }
}
