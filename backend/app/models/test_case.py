"""测试用例模型"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, func
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
    # 《测试用例等级定义规范》四级制：L1 基本/L2 重要/L3 一般/L4 轻微。
    # 历史 P0~P4 一并保留：存量用例仍可能是 P 等级，去掉会导致 ORM 校验失败/脏数据。
    priority: Mapped[str] = mapped_column(
        Enum("L1", "L2", "L3", "L4", "P0", "P1", "P2", "P3", "P4"),
        default="L2",
        nullable=False,
    )
    test_type: Mapped[str] = mapped_column(String(50), default="功能测试", nullable=False)
    source: Mapped[str] = mapped_column(Enum("ai", "manual", "ai_reviewed"), default="ai", nullable=False)
    status: Mapped[str] = mapped_column(Enum("draft", "reviewed", "approved"), default="draft", nullable=False)
    # AI 生成质量人工反馈：good(好用) | bad(不好用) | NULL(未反馈)
    feedback: Mapped[str | None] = mapped_column(String(10))
    # 生成该用例的生成任务 id（用于按任务回溯/自查）
    task_id: Mapped[int | None] = mapped_column(ForeignKey("generation_task.id"))
    # 生成该用例时所依据的需求原文（自查/重生成时对照原文用）
    req_ref: Mapped[str | None] = mapped_column(Text)
    # AI 自查备注：自查发现问题时写入【存疑】/【不符】说明；无问题保持 NULL
    ai_remark: Mapped[str | None] = mapped_column(Text)
    # 最近一次 AI 自查时间
    ai_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    # 重复扫描标注的结构化字段（供按组保留代表/批量清理）：
    # dup_group_no: 被标为疑似重复所属组号；NULL 表示非冗余（含每组保留的代表用例）
    dup_group_no: Mapped[int | None] = mapped_column(Integer)
    # dup_keep_case_id: 本冗余用例所属重复组内建议保留的代表用例 id
    dup_keep_case_id: Mapped[int | None] = mapped_column(Integer)
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
