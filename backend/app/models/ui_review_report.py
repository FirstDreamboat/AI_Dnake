"""需求体检报告模型：留存历史体检结果，支持随时查看与导出"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UIReviewReport(Base):
    __tablename__ = "ui_review_report"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    # 问题清单/亮点/指标 存 JSON 字符串
    issues: Mapped[str] = mapped_column(Text, default="[]")
    highlights: Mapped[str] = mapped_column(Text, default="[]")
    metrics: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self):
        return f"<UIReviewReport {self.id} score={self.score}>"
