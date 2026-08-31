"""测试用例模型"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TestCase(Base):
    __tablename__ = "test_case"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    test_point_id: Mapped[int | None] = mapped_column(ForeignKey("test_point.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    module: Mapped[str | None] = mapped_column(String(50))  # 所属模块，如"登录注册"
    preconditions: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Enum("P0", "P1", "P2", "P3", "P4"), default="P2", nullable=False)
    test_type: Mapped[str] = mapped_column(String(50), default="功能测试", nullable=False)
    source: Mapped[str] = mapped_column(Enum("ai", "manual", "ai_reviewed"), default="ai", nullable=False)
    status: Mapped[str] = mapped_column(Enum("draft", "reviewed", "approved"), default="draft", nullable=False)
    # AI 生成质量人工反馈：good(好用) | bad(不好用) | NULL(未反馈)
    feedback: Mapped[str | None] = mapped_column(String(10))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<TestCase {self.case_no}>"


class TestCaseVersion(Base):
    __tablename__ = "test_case_version"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("test_case.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_log: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
