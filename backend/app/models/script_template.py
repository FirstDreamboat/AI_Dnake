"""脚本模板模型：FR-6.4 用户自定义脚本生成模板"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScriptTemplate(Base):
    __tablename__ = "script_template"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # pytest / api / ui / custom
    script_type: Mapped[str] = mapped_column(String(20), default="custom", nullable=False)
    language: Mapped[str] = mapped_column(String(20), default="python", nullable=False)
    framework: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    template_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<ScriptTemplate {self.name}>"
