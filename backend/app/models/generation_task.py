"""用例生成任务模型"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GenerationTask(Base):
    __tablename__ = "generation_task"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "success", "failed", "cancelled"),
        default="pending",
        nullable=False,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_case: Mapped[int] = mapped_column(Integer, default=0)
    result_summary: Mapped[dict | None] = mapped_column(JSON)
    error_msg: Mapped[str | None] = mapped_column(Text)
    options: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<GenerationTask {self.task_no}>"
