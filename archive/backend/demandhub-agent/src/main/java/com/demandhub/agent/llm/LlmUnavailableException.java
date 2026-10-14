package com.demandhub.agent.llm;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;

/**
 * 大模型不可用异常（降级策略：Agent 入口返回友好提示，主流程不受影响）
 */
public class LlmUnavailableException extends BizException {

    public LlmUnavailableException() {
        super(ErrorCode.AI_SERVICE_UNAVAILABLE, "AI 服务暂不可用，请稍后再试");
    }
}
