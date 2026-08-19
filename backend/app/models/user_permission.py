"""用户自定义权限关联表"""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserPermission(Base):
    """用户与权限点关联（admin 角色不落库，动态拥有全部权限）"""

    __tablename__ = "user_permissions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(String(50), primary_key=True)
