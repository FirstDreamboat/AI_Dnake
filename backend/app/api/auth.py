"""认证接口"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import AuthError
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.common import ok
from app.schemas.user import LoginRequest, PasswordChange
from app.services import auth_service, captcha_service

router = APIRouter(prefix="/auth")


@router.get("/captcha")
def get_captcha():
    """获取登录图片验证码"""
    return ok(captcha_service.generate_captcha(), "验证码已生成")


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    # 开启验证码时校验（验证码一次性，校验失败直接拒绝）
    if captcha_service.captcha_enabled():
        if not captcha_service.verify_captcha(req.captcha_id or "", req.captcha_code or ""):
            raise AuthError("验证码错误或已过期")
    user = auth_service.authenticate(db, req)
    return ok(auth_service.build_token_response(db, user), "登录成功")


@router.post("/refresh")
def refresh(refresh_token: str):
    """刷新 Token（MVP 直接重新签发）"""
    # 简化实现：生产环境应校验 refresh_token
    from app.core.security import decode_token

    payload = decode_token(refresh_token)
    new_token = create_access_token(payload["sub"])
    return ok({"access_token": new_token, "token_type": "bearer"})


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前用户信息（含权限点）"""
    return ok(auth_service.build_user_out(db, user))


@router.post("/change-password")
def change_password(
    req: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户修改自己的密码（首次登录强制改密时使用）"""
    auth_service.change_own_password(db, user, req.old_password, req.new_password)
    return ok(message="密码修改成功")


@router.post("/logout")
def logout(user: User = Depends(get_current_user)):
    """退出登录（前端清除 Token 即可，MVP 不做服务端失效）"""
    return ok(message="退出成功")
