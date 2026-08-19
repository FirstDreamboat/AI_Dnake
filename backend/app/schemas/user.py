"""用户相关数据模型"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    # 登录不做最小长度校验，统一走“用户名或密码错误”，避免短密码触发 422
    password: str = Field(..., min_length=1, max_length=64)
    # 图片验证码（系统开启验证码时为必填）
    captcha_id: str | None = None
    captcha_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=64)
    real_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    role: str = "engineer"
    # 自定义权限点列表；不传则按角色默认权限
    permissions: list[str] | None = None


class UserUpdate(BaseModel):
    real_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    role: str | None = None
    # 传入则全量覆盖该用户权限（仅成员管理场景使用）
    permissions: list[str] | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=64)


class PasswordChange(BaseModel):
    """当前用户自助修改密码（首次登录强制改密）"""
    old_password: str = Field(..., min_length=1, max_length=64)
    new_password: str = Field(..., min_length=6, max_length=64)


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserOut(BaseModel):
    id: int
    username: str
    real_name: str | None
    email: str | None
    phone: str | None
    role: str
    is_active: bool
    # 非管理员为 True 时，登录后必须修改密码
    must_change_password: bool = False
    created_at: datetime
    permissions: list[str] = []

    model_config = {"from_attributes": True}
