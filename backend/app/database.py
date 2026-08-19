"""数据库连接与会话管理"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""


def _get_database_url() -> str:
    """SQLite 相对路径转为绝对路径，并确保目录存在"""
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        db_file = url.replace("sqlite:///", "")
        if db_file and not db_file.startswith("/"):
            db_path = Path(settings.upload_dir.parent) / db_file
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{db_path}"
    return url


_db_kwargs: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _db_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # 服务器数据库（MySQL 等）：连接池调优，pool_recycle 低于 wait_timeout 避免断连
    _db_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=3600)

engine = create_engine(
    _get_database_url(),
    echo=False,
    pool_pre_ping=True,
    **_db_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """创建所有数据表（开发环境用），生产建议使用 Alembic 迁移"""
    from app import models  # noqa: F401 确保模型注册

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    _backfill_default_permissions()


def _add_missing_columns() -> None:
    """轻量迁移：为已存在的表补充新增列（SQLite 不支持 ALTER ADD COLUMN IF NOT EXISTS）"""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "user" not in tables:
        return
    with engine.begin() as conn:
        user_columns = {c["name"] for c in inspector.get_columns("user")}
        if "must_change_password" not in user_columns:
            conn.execute(
                text("ALTER TABLE user ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0")
            )
        if "failed_attempts" not in user_columns:
            conn.execute(text("ALTER TABLE user ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0"))
        if "locked_until" not in user_columns:
            conn.execute(text("ALTER TABLE user ADD COLUMN locked_until DATETIME"))
        if "test_case" in tables:
            tc_columns = {c["name"] for c in inspector.get_columns("test_case")}
            if "feedback" not in tc_columns:
                conn.execute(text("ALTER TABLE test_case ADD COLUMN feedback VARCHAR(10)"))
        if "knowledge_doc" in tables:
            kd_columns = {c["name"] for c in inspector.get_columns("knowledge_doc")}
            if "product_line" not in kd_columns:
                conn.execute(text("ALTER TABLE knowledge_doc ADD COLUMN product_line VARCHAR(20)"))


def _backfill_default_permissions() -> None:
    """为已有用户回填角色默认权限（幂等，仅补充从未配置过权限的非 admin 用户）"""
    from sqlalchemy import select

    from app.core.permissions import VALID_PERMISSION_CODES, default_permissions_for
    from app.models.user import User
    from app.models.user_permission import UserPermission

    with SessionLocal() as db:
        users = db.scalars(select(User).where(User.role != "admin")).all()
        for u in users:
            if u.role == "admin":
                continue
            exists = db.scalar(
                select(UserPermission.permission_code)
                .where(UserPermission.user_id == u.id)
                .limit(1)
            )
            if exists is not None:
                continue
            for code in default_permissions_for(u.role):
                if code in VALID_PERMISSION_CODES:
                    db.add(UserPermission(user_id=u.id, permission_code=code))
        db.commit()


def get_db():
    """FastAPI 依赖：请求级数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
