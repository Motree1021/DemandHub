package com.demandhub.agent.llm;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 大模型平台接入开关（一期 Mock）：
 * 运行期可通过管理接口切换，用于自测"大模型挂掉 → Agent 降级"（检查点 8）。
 * 二期对接真实大模型平台时，此开关替换为平台健康探测。
 */
@Component
public class LlmSwitch {

    private final AtomicBoolean enabled;

    public LlmSwitch(@Value("${demandhub.agent.llm.mock-enabled:true}") boolean initial) {
        this.enabled = new AtomicBoolean(initial);
    }

    public boolean available() {
        return enabled.get();
    }

    public void setAvailable(boolean value) {
        enabled.set(value);
    }
}
