"""测试点模型"""
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TestPoint(Base):
    __tablename__ = "test_point"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(
        Enum("function", "boundary", "exception", "performance", "security", "implicit"),
        default="function",
        nullable=False,
    )
    technique: Mapped[str | None] = mapped_column(
        Enum(
            "equivalence", "boundary", "decision_table", "state_transition",
            "scenario", "orthogonal", "error_guessing", "none",
        ),
        default="none",
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<TestPoint {self.name}>"
