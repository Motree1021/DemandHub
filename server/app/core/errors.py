from enum import Enum


class ErrorCode(Enum):
    SUCCESS = (0, "success")
    PARAM_INVALID = (400, "参数校验失败")
    UNAUTHORIZED = (401, "未登录或登录已过期")
    FORBIDDEN = (403, "无权限访问")
    NOT_FOUND = (404, "资源不存在")
    CONFLICT = (409, "数据已更新或请求标识冲突")
    SYSTEM_ERROR = (500, "系统内部错误")
    ILLEGAL_STATE_TRANSITION = (1001, "非法的状态流转")
    DEMAND_NOT_FOUND = (1002, "需求不存在")
    AUTH_SERVICE_UNAVAILABLE = (1102, "身份服务暂不可用，请稍后重试")
    CHANNEL_TICKET_INVALID = (1107, "登录票据无效或已过期，请从原渠道重新进入")
    CHANNEL_DISABLED = (1108, "该渠道已停用")
    CHANNEL_ACCOUNT_UNAVAILABLE = (1113, "账号不可用，请联系管理员")
    TEST_LOGIN_IDENTITY_INVALID = (1114, "姓名或企业账号未录入，请联系管理员开通")
    DEMAND_TYPE_INVALID = (1207, "需求类型无效")
    AI_SERVICE_UNAVAILABLE = (1401, "AI 服务暂不可用")
    AGENT_SESSION_NOT_FOUND = (1402, "会话不存在")

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
