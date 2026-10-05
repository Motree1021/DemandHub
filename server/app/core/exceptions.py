import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import BizError
from app.core.result import fail

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def business_error(request: Request, exc: BizError):
        return JSONResponse(fail(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        return JSONResponse(fail(400, ".".join(map(str, first["loc"])) + " " + first["msg"]))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        message = "未登录或登录已过期" if exc.status_code == 401 else str(exc.detail)
        return JSONResponse(fail(exc.status_code, message), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def system_error(request: Request, exc: Exception):
        # 不回显异常内容，避免上游报文和连接凭据外泄。
        logger.error("系统内部错误: %s", type(exc).__name__)
        return JSONResponse(fail(500, "系统内部错误"))
