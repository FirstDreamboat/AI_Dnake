"""知识库文档模型"""
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# 文档原文可能超过 MySQL TEXT 上限(65535 字节)，MySQL 下使用 LONGTEXT，其他方言回退 TEXT
LONG_TEXT = Text().with_variant(LONGTEXT(), "mysql")


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_doc"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_type: Mapped[str] = mapped_column(
        Enum("test_case", "prd", "tech_spec", "defect", "best_practice"),
        default="test_case",
        nullable=False,
    )
    # 产品线（业务域）：intercom 楼宇对讲 / smart_home 智能家居 / hospital 智慧病房/门诊；空=通用知识
    product_line: Mapped[str | None] = mapped_column(
        Enum("intercom", "smart_home", "hospital"),
        default=None,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(LONG_TEXT)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_status: Mapped[str] = mapped_column(
        Enum("pending", "indexing", "indexed", "failed"), default="pending", nullable=False
    )
    vector_error: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class KnowledgeDocVersion(Base):
    """知识文档历史版本快照（FR-4.4 版本管理）"""

    __tablename__ = "knowledge_doc_version"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_doc.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(LONG_TEXT)
    change_log: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
