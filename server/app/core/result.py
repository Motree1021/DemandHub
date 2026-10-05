from datetime import date, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


def encode(value: Any) -> Any:
    return jsonable_encoder(value, custom_encoder={
        datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        date: lambda v: v.isoformat(),
    })


def ok(data: Any = None) -> dict:
    return {"code": 0, "message": "success", "data": encode(data)}


def fail(code: int, message: str) -> dict:
    return {"code": code, "message": message, "data": None}


class Result(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None
