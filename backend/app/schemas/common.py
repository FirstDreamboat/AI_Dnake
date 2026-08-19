"""统一 API 响应格式"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应包装: {code, message, data}"""

    code: int = 0
    message: str = "success"
    data: T | None = None


class PageData(BaseModel, Generic[T]):
    """分页数据"""

    list: list[T]
    total: int
    page: int
    page_size: int


def ok(data: Any = None, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data}
