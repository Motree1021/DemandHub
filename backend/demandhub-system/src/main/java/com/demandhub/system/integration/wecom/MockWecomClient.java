package com.demandhub.system.integration.wecom;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/**
 * 企微 Mock 实现：授权码约定 mock-{userId}，换取的企微 userid 为 wq_{userId}。
 */
@Component
public class MockWecomClient implements WecomClient {

    public static final String MOCK_CODE_PREFIX = "mock-";

    @Override
    public String exchangeCode(String code) {
        if (!StringUtils.hasText(code) || !code.startsWith(MOCK_CODE_PREFIX)) {
            throw new BizException(ErrorCode.AUTH_CODE_INVALID);
        }
        String userId = code.substring(MOCK_CODE_PREFIX.length());
        if (!StringUtils.hasText(userId)) {
            throw new BizException(ErrorCode.AUTH_CODE_INVALID);
        }
        return "wq_" + userId;
    }

    @Override
    public String buildOAuthUrl(String redirectUri, String state) {
        // 二期替换为 https://open.weixin.qq.com/connect/oauth2/authorize?appid=... 真实链接
        return "mock-wecom-oauth://" + (StringUtils.hasText(redirectUri) ? redirectUri : "")
                + "?state=" + (StringUtils.hasText(state) ? state : "");
    }
}
