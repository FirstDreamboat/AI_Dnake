"""用例文件（项目内 Excel 在线编辑）模型"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CaseFile(Base):
    """项目下的用例表格文件：上传后可在线查看与单人锁定编辑"""

    __tablename__ = "case_file"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    # 展示名（用户上传时的文件名，含扩展名）
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # 存储路径（相对 upload_dir），实际统一为 .xlsx
    stored_path: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self):
        return f"<CaseFile {self.id} {self.filename}>"
