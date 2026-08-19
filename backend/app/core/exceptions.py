"""业务异常定义"""
from fastapi import HTTPException


class BusinessError(Exception):
    """业务异常，带 HTTP 状态码与业务码"""

    def __init__(self, message: str, code: int = 400, http_status: int = 400):
        self.message = message
        self.code = code
        self.http_status = http_status
        super().__init__(message)


class NotFoundError(BusinessError):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code=404, http_status=404)


class PermissionDeniedError(BusinessError):
    def __init__(self, message: str = "无权限访问"):
        super().__init__(message, code=403, http_status=403)


class AuthError(BusinessError):
    def __init__(self, message: str = "认证失败"):
        super().__init__(message, code=401, http_status=401)


def to_http_exception(e: BusinessError) -> HTTPException:
    return HTTPException(status_code=e.http_status, detail=e.message)
