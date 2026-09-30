from functools import lru_cache
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


def parse_database_url(value: str, driver: str = "mysql+asyncmy") -> URL:
    raw = value.removeprefix("jdbc:")
    # 从最后一个 @ 分离认证段，支持平台未编码的 @ 与 /，百分号只解码一次。
    if "://" not in raw:
        raise ValueError("数据库 URL 格式无效")
    scheme, rest = raw.split("://", 1)
    if scheme not in {"mysql", "mysql+asyncmy", "mysql+pymysql"} or "@" not in rest:
        raise ValueError("数据库 URL 必须包含 MySQL 用户认证")
    credentials, location = rest.rsplit("@", 1)
    if ":" not in credentials:
        raise ValueError("数据库 URL 缺少用户名或密码")
    user, password = credentials.split(":", 1)
    parsed = urlsplit("mysql://" + location)
    database = unquote(parsed.path.removeprefix("/"))
    if not user or not password or not parsed.hostname or not database or "/" in database:
        raise ValueError("数据库 URL 缺少用户名、密码、主机或数据库名")
    return URL.create(driver, username=unquote(user), password=unquote(password),
                      host=parsed.hostname, port=parsed.port or 3306, database=database,
                      query={"charset": "utf8mb4"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    app_env: Literal["dev", "test", "prod"] = "prod"
    demandhub_database_url: str = Field(repr=False)
    jwt_secret: str = Field(min_length=32, repr=False)
    jwt_access_ttl_hours: int = Field(default=8, ge=1, le=24)
    auth_dev_login: bool = False
    admin_wecom_userids: str = ""
    api_root_path: str = "/demandhub-api"
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    channel_ls_base_url: str = ""
    channel_ls_app_key: str = ""
    channel_ls_app_secret: str = Field(default="", repr=False)
    channel_ls_timeout_ms: int = Field(default=3000, ge=1)
    llm_api_key: str = Field(default="", repr=False)
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_chat_model: str = "ep-20260930122836-rv2gw"
    llm_thinking: Literal["disabled", "enabled", "auto"] | None = None
    llm_read_timeout_s: float = Field(default=60, gt=0)
    llm_embedding_model: str = ""
    llm_failure_threshold: int = Field(default=3, ge=1)
    llm_failure_cooldown_s: float = Field(default=60, gt=0)

    @model_validator(mode="after")
    def validate_environment(self):
        parse_database_url(self.demandhub_database_url)
        if self.api_root_path != "/demandhub-api":
            raise ValueError("公开路径必须为 /demandhub-api")
        if self.app_env == "prod":
            if self.auth_dev_login:
                raise ValueError("生产环境禁止 dev-login")
            if not all((self.channel_ls_base_url, self.channel_ls_app_key, self.channel_ls_app_secret)):
                raise ValueError("生产环境缺少创金零售 SSO 配置")
        return self

    @property
    def database_url(self) -> URL:
        return parse_database_url(self.demandhub_database_url)

    @property
    def sync_database_url(self) -> URL:
        return parse_database_url(self.demandhub_database_url, "mysql+pymysql")

    @property
    def admin_ids(self) -> set[str]:
        return {v.strip() for v in self.admin_wecom_userids.split(",") if v.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
