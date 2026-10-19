from enum import Enum


class ErrorCode(Enum):
    SUCCESS = (0, "success")
    PARAM_INVALID = (400, "参数校验失败")
    UNAUTHORIZED = (401, "未登录或登录已过期")
    FORBIDDEN = (403, "无权限访问")
    NOT_FOUND = (404, "资源不存在")
    CONFLICT = (409, "数据已更新或请求标识冲突")
    SYSTEM_ERROR = (500, "系统内部错误")
    BIZ_ERROR = (1000, "业务处理失败")
    ILLEGAL_STATE_TRANSITION = (1001, "非法的状态流转")
    DEMAND_NOT_FOUND = (1002, "需求不存在")
    CONCURRENT_CONFLICT = (1003, "并发操作冲突，请刷新后重试")
    AUTH_SERVICE_UNAVAILABLE = (1102, "身份服务暂不可用，请稍后重试")
    CHANNEL_TICKET_INVALID = (1107, "登录票据无效或已过期，请从原渠道重新进入")
    CHANNEL_DISABLED = (1108, "该渠道已停用")
    CHANNEL_ACCOUNT_UNAVAILABLE = (1113, "账号不可用，请联系管理员")
    TEST_LOGIN_IDENTITY_INVALID = (1114, "姓名或企业账号未录入，请联系管理员开通")
    AUTH_LOGIN_FAILED = (1115, "账号或密码错误")
    AUTH_ACCOUNT_LOCKED = (1116, "失败次数过多，账号已锁定15分钟，请稍后再试")
    AUTH_REFRESH_INVALID = (1117, "登录已过期，请重新登录")
    AUTH_OLD_PASSWORD_WRONG = (1118, "原密码错误")
    USER_NOT_FOUND = (1119, "用户不存在")
    LOGIN_ACCOUNT_EXISTS = (1120, "登录账号已存在")
    ROLE_GRANT_NOT_FOUND = (1121, "授权记录不存在")
    ROLE_GRANT_DUPLICATED = (1122, "相同范围的授权已存在")
    CHANNEL_NOT_WHITELISTED = (1123, "非白名单用户，暂不支持访问")
    WHITELIST_ENTRY_NOT_FOUND = (1124, "白名单记录不存在")
    WHITELIST_ENTRY_DUPLICATED = (1125, "该企微ID已在白名单中")
    TYPE_SCOPE_DENIED = (1126, "无该需求类型的操作权限")
    IDENTITY_NOT_FOUND = (1127, "渠道身份不存在")
    IDENTITY_ALREADY_LINKED = (1128, "该渠道身份已被挂接，请刷新后核对")
    PHONE_EXISTS = (1129, "手机号已被使用")
    DEMAND_TYPE_INVALID = (1207, "需求类型无效")
    DEMAND_ALREADY_CLAIMED = (1208, "该需求已被他人领取")
    ACCEPTANCE_PRECONDITION = (1209, "验收前置条件未满足")
    SOLUTION_NOT_FOUND = (1202, "方案不存在")
    STATE_MACHINE_CONFIG_INVALID = (1304, "状态机配置无效")
    AI_SERVICE_UNAVAILABLE = (1401, "AI 服务暂不可用")
    AGENT_SESSION_NOT_FOUND = (1402, "会话不存在")
    AGENT_DRAFT_NOT_FOUND = (1403, "草稿不存在")
    AGENT_DRAFT_CONFIRMED = (1404, "草稿已处理")
    AI_CONTENT_REJECTED = (1405, "这段文字未能通过平台内容安全审核，请调整表述后重试")

    @property
    def code(self) -> int:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]


class BizError(Exception):
    def __init__(self, code: ErrorCode, message: str | None = None):
        self.error_code = code
        self.code = code.code
        self.message = message or code.message
        super().__init__(self.message)
