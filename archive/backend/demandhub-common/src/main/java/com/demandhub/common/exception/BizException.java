package com.demandhub.common.exception;

import com.demandhub.common.core.ErrorCode;
import lombok.Getter;

/**
 * 业务异常：抛出后由全局异常处理器转为标准错误 JSON
 */
@Getter
public class BizException extends RuntimeException {

    private final Integer code;

    public BizException(ErrorCode errorCode) {
        super(errorCode.getMessage());
        this.code = errorCode.getCode();
    }

    public BizException(ErrorCode errorCode, String message) {
        super(message);
        this.code = errorCode.getCode();
    }

    public BizException(String message) {
        super(message);
        this.code = ErrorCode.BIZ_ERROR.getCode();
    }
}
