"""权限相关数据模型"""
from pydantic import BaseModel, Field


class PermissionUpdate(BaseModel):
    permissions: list[str] = Field(default_factory=list)
