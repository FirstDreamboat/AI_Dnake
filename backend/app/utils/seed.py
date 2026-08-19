"""种子数据初始化"""
from sqlalchemy import select

from app.core.security import hash_password
from app.database import SessionLocal
from app.models.sys_config import SysConfig
from app.models.user import User

DEFAULT_ADMIN = {"username": "admin", "password": "admin123", "real_name": "系统管理员", "role": "admin"}

DEFAULT_CONFIGS = [
    ("llm_model", "qwen2.5:3b", "用例生成主模型"),
    ("embedding_model", "bge-m3", "向量检索模型"),
    ("rag_top_k", "5", "RAG 检索条数"),
    ("generation_timeout", "300", "生成任务超时秒数"),
]


def create_admin_user() -> None:
    """创建默认管理员账号"""
    db = SessionLocal()
    try:
        exists = db.scalar(select(User).where(User.username == DEFAULT_ADMIN["username"]))
        if not exists:
            db.add(
                User(
                    username=DEFAULT_ADMIN["username"],
                    password_hash=hash_password(DEFAULT_ADMIN["password"]),
                    real_name=DEFAULT_ADMIN["real_name"],
                    role=DEFAULT_ADMIN["role"],
                )
            )
            db.commit()
    finally:
        db.close()


def init_sys_configs() -> None:
    """初始化系统配置项"""
    db = SessionLocal()
    try:
        for key, value, desc in DEFAULT_CONFIGS:
            exists = db.scalar(select(SysConfig).where(SysConfig.config_key == key))
            if not exists:
                db.add(SysConfig(config_key=key, config_value=value, description=desc))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin_user()
    init_sys_configs()
    print("种子数据初始化完成: admin/admin123")
