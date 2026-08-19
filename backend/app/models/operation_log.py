"""操作日志模型：记录平台关键写操作"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OperationLog(Base):
    __tablename__ = "operation_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column()
    username: Mapped[str | None] = mapped_column(String(50))
    module: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<OperationLog {self.method} {self.path}>"
