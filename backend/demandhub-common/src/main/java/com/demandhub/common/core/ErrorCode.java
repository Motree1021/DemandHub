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
    CONCURRENT_CONFLICT(1003, "并发操作冲突，请刷新后重试"),

    AUTH_CODE_INVALID(1101, "授权码无效或已过期"),
    AUTH_SERVICE_UNAVAILABLE(1102, "身份服务暂不可用，请稍后重试"),
    REFRESH_TOKEN_INVALID(1103, "刷新令牌无效或已过期"),
    USER_NOT_FOUND(1104, "用户不存在"),
    ROLE_GRANT_DUPLICATED(1105, "相同授权已存在"),
    ROLE_GRANT_NOT_FOUND(1106, "授权记录不存在"),
    CHANNEL_TICKET_INVALID(1107, "登录票据无效或已过期，请从原渠道重新进入"),
    CHANNEL_DISABLED(1108, "该渠道已停用"),
    LOGIN_FAILED(1109, "账号或密码错误"),
    LOGIN_LOCKED(1110, "登录失败次数过多，账号已锁定，请稍后再试"),
    PASSWORD_RULE_VIOLATION(1111, "密码需至少 8 位且包含字母和数字"),
    MERGE_TARGET_INVALID(1112, "合并目标用户无效"),
    CHANNEL_ACCOUNT_UNAVAILABLE(1113, "账号不可用，请联系管理员"),

    DRAFT_NOT_FOUND(1201, "草稿不存在"),
    SOLUTION_NOT_FOUND(1202, "方案不存在"),
    ATTACHMENT_NOT_FOUND(1203, "附件不存在"),
    COMMENT_NOT_FOUND(1204, "评论不存在"),
    RELATION_NOT_FOUND(1205, "关联不存在"),
    EFFORT_NOT_FOUND(1206, "工时记录不存在"),
    DEMAND_TYPE_INVALID(1207, "需求类型无效"),
    DEMAND_ALREADY_CLAIMED(1208, "该需求已被他人领取"),
    ACCEPTANCE_PRECONDITION(1209, "提交验收前置条件未满足"),
    FILE_TOO_LARGE(1210, "文件大小超出限制"),
    ATTACHMENT_LIMIT(1211, "附件数量超出限制"),

    NOTIFICATION_NOT_FOUND(1301, "通知不存在"),
    TEMPLATE_NOT_FOUND(1302, "通知模板不存在"),
    DICT_ITEM_NOT_FOUND(1303, "字典项不存在"),
    STATE_MACHINE_CONFIG_INVALID(1304, "状态机配置不合法"),
    DEMAND_TYPE_NOT_FOUND(1305, "需求类型不存在"),
    SLA_CONFIG_NOT_FOUND(1306, "SLA 配置不存在"),

    AI_SERVICE_UNAVAILABLE(1401, "AI 服务暂不可用"),
    AGENT_SESSION_NOT_FOUND(1402, "会话不存在"),
    AGENT_DRAFT_NOT_FOUND(1403, "草稿不存在"),
    AGENT_DRAFT_CONFIRMED(1404, "草稿已处理，请勿重复操作"),
    PROMPT_TEMPLATE_NOT_FOUND(1405, "Prompt 模板不存在");

    private final Integer code;
    private final String message;

    ErrorCode(Integer code, String message) {
        this.code = code;
        this.message = message;
    }
}
