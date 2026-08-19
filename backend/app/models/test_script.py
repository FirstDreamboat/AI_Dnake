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
    script_type: Mapped[str] = mapped_column(
        Enum("pytest", "api", "ui", "custom"), default="pytest", nullable=False
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
