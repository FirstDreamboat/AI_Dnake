"""认证与用户服务"""
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import AuthError, NotFoundError
from app.core.permissions import ALL_PERMISSIONS, VALID_PERMISSION_CODES, default_permissions_for
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.models.user_permission import UserPermission
from app.schemas.user import LoginRequest, UserCreate, UserOut, UserUpdate


def _reset_login_failures(db: Session, user: User) -> None:
    """登录成功，清零失败计数"""
    if user.failed_attempts or user.locked_until:
        user.failed_attempts = 0
        user.locked_until = None
        db.commit()


def _is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > datetime.now()


def _record_failure(db: Session, user: User) -> bool:
    """记录一次登录失败；达到阈值则锁定账号。返回本次是否触发锁定"""
    user.failed_attempts = (user.failed_attempts or 0) + 1
    if user.failed_attempts >= settings.LOGIN_MAX_ATTEMPTS:
        user.locked_until = datetime.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
        user.failed_attempts = 0  # 锁定后重新计数
        db.commit()
        return True
    db.commit()
    return False


def authenticate(db: Session, req: LoginRequest) -> User:
    """校验用户名密码（含账号锁定逻辑）"""
    user = db.scalar(select(User).where(User.username == req.username))
    if user and _is_locked(user):
        remain = int((user.locked_until - datetime.now()).total_seconds() // 60) + 1
        raise AuthError(f"账号已锁定，请 {remain} 分钟后再试")

    if not user or not verify_password(req.password, user.password_hash):
        if user:
            locked = _record_failure(db, user)
            if locked:
                raise AuthError(f"连续失败次数过多，账号已锁定 {settings.LOGIN_LOCK_MINUTES} 分钟")
            remaining = settings.LOGIN_MAX_ATTEMPTS - user.failed_attempts
            raise AuthError(f"用户名或密码错误，剩余 {remaining} 次尝试机会")
        raise AuthError("用户名或密码错误")
    if not user.is_active:
        raise AuthError("账号已被禁用")
    _reset_login_failures(db, user)
    return user


def get_user_permissions(db: Session, user: User) -> list[str]:
    """获取用户有效权限点列表（admin 恒为全部权限，无需落库）"""
    if user.role == "admin":
        return list(ALL_PERMISSIONS)
    rows = db.scalars(
        select(UserPermission.permission_code).where(UserPermission.user_id == user.id)
    ).all()
    return list(rows)


def set_user_permissions(db: Session, user_id: int, codes: list[str]) -> None:
    """全量覆盖用户权限点（admin 忽略，由系统决定拥有全部权限）"""
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    if user.role == "admin":
        return
    valid = [c for c in codes if c in VALID_PERMISSION_CODES]
    db.execute(delete(UserPermission).where(UserPermission.user_id == user_id))
    for code in valid:
        db.add(UserPermission(user_id=user_id, permission_code=code))
    db.commit()


def build_user_out(db: Session, user: User) -> UserOut:
    """构造带权限的用户输出对象"""
    out = UserOut.model_validate(user)
    out.permissions = get_user_permissions(db, user)
    return out


def build_token_response(db: Session, user: User) -> dict:
    """构造登录响应"""
    from app.config import settings

    token = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": build_user_out(db, user),
    }


def change_own_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    """当前用户自助修改密码；校验原密码并清除强制改密标记"""
    if not verify_password(old_password, user.password_hash):
        raise AuthError("原密码不正确")
    if verify_password(new_password, user.password_hash):
        raise AuthError("新密码不能与原密码相同")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()
    db.refresh(user)


def create_user(db: Session, req: UserCreate, operator: User) -> User:
    """创建用户（仅管理员）"""
    exists = db.scalar(select(User).where(User.username == req.username))
    if exists:
        raise AuthError("用户名已存在")
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        real_name=req.real_name,
        email=req.email,
        phone=req.phone,
        role=req.role,
        # 成员首次登录强制修改初始密码
        must_change_password=req.role != "admin",
    )
    db.add(user)
    db.flush()
    # 写入权限：显式传入则按自定义，否则按角色默认
    codes = req.permissions if req.permissions is not None else default_permissions_for(req.role)
    if user.role != "admin":
        for code in codes:
            if code in VALID_PERMISSION_CODES:
                db.add(UserPermission(user_id=user.id, permission_code=code))
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, req: UserUpdate) -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    data = req.model_dump(exclude_unset=True)
    new_permissions = data.pop("permissions", None)
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    if new_permissions is not None:
        set_user_permissions(db, user_id, new_permissions)
    return user


def reset_password(db: Session, user_id: int, new_password: str) -> None:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    user.password_hash = hash_password(new_password)
    # 被重置密码的成员，下次登录需强制修改密码
    if user.role != "admin":
        user.must_change_password = True
    db.commit()


def set_user_active(db: Session, user_id: int, is_active: bool) -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session, page: int, page_size: int, keyword: str | None = None) -> tuple[list[User], int]:
    stmt = select(User)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(User.username.like(like), User.real_name.like(like)))
    total = len(db.scalars(stmt).all())
    users = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return list(users), total


def delete_user(db: Session, user_id: int, operator: User) -> None:
    """删除用户（仅管理员）。不能删除自己，不能删除最后一个管理员；
    删除前将其名下数据的 created_by 置空，避免悬空引用。"""
    from app.core.exceptions import BusinessError

    if operator.id == user_id:
        raise BusinessError("不能删除当前登录账号")
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    if user.role == "admin":
        admin_count = len(db.scalars(select(User).where(User.role == "admin")).all())
        if admin_count <= 1:
            raise BusinessError("系统至少需要保留一个管理员账号")

    # 清理关联数据的创建者引用
    from app.models.generation_task import GenerationTask
    from app.models.knowledge import KnowledgeDoc, KnowledgeDocVersion
    from app.models.script_template import ScriptTemplate
    from app.models.test_case import TestCase, TestCaseVersion
    from app.models.test_script import TestScript

    targets = [
        GenerationTask,
        KnowledgeDoc,
        KnowledgeDocVersion,
        ScriptTemplate,
        TestCase,
        TestCaseVersion,
        TestScript,
    ]
    for model in targets:
        try:
            db.query(model).filter(model.created_by == user_id).update({"created_by": None})
        except Exception:
            db.rollback()
    # 显式删除权限记录（SQLite 外键约束默认关闭，不依赖数据库级联）
    db.execute(delete(UserPermission).where(UserPermission.user_id == user_id))
    db.delete(user)
    db.commit()
