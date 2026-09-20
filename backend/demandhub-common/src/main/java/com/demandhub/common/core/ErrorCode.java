package com.demandhub.common.core;

import lombok.Getter;

/**
 * 统一错误码
 * 0 成功；4xx 对应 HTTP 语义；1xxx 为业务错误码段，各模块可扩展
 */
@Getter
public enum ErrorCode {

    SUCCESS(0, "success"),
    PARAM_INVALID(400, "参数校验失败"),
    UNAUTHORIZED(401, "未登录或登录已过期"),
    FORBIDDEN(403, "无权限访问"),
    NOT_FOUND(404, "资源不存在"),
    SYSTEM_ERROR(500, "系统内部错误"),

    BIZ_ERROR(1000, "业务处理失败"),
    ILLEGAL_STATE_TRANSITION(1001, "非法的状态流转"),
    DEMAND_NOT_FOUND(1002, "需求不存在"),
    CONCURRENT_CONFLICT(1003, "并发操作冲突，请刷新后重试");

    private final Integer code;
    private final String message;

    ErrorCode(Integer code, String message) {
        this.code = code;
        this.message = message;
    }
}
