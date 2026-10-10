"""测试脚本模型：存储由测试用例自动生成的自动化测试脚本"""
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TestScript(Base):
    __tablename__ = "test_script"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("test_case.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 取值须与 schemas/script.py 的 ^(pytest|api|ui|android|ios|custom)$ 一致：
    # 早期 ORM 只定义了 4 个值，而接口层放行 android/ios，导致移动端脚本保存时
    # 被 MySQL 枚举校验拒绝（500）。补齐取值并配合 database._add_missing_columns 迁移。
    script_type: Mapped[str] = mapped_column(
        Enum("pytest", "api", "ui", "android", "ios", "custom"), default="pytest", nullable=False
    )
    language: Mapped[str] = mapped_column(String(20), default="python", nullable=False)
    framework: Mapped[str | None] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<TestScript {self.name}>"
