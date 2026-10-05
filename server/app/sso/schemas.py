from pydantic import BaseModel, Field


class SsoProfile(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    employee_no: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=128)
    dept_id: str | None = Field(default=None, max_length=32)
    dept_name: str | None = Field(default=None, max_length=128)
    dept_path: str | None = Field(default=None, max_length=512)


class ChannelSsoConfig(BaseModel):
    base_url: str
    app_key: str
    app_secret: str = Field(repr=False)
    timeout_ms: int = 3000
