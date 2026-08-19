"""脚本模板相关数据模型（FR-6.4 自定义模板）"""
from datetime import datetime

from pydantic import BaseModel, Field


class ScriptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    script_type: str = Field("custom", pattern="^(pytest|api|ui|custom)$")
    language: str = Field("python", max_length=20)
    framework: str | None = Field(None, max_length=50)
    template_content: str = Field(..., min_length=1)
    description: str | None = Field(None, max_length=500)
    is_active: bool = True


class ScriptTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    script_type: str | None = Field(None, pattern="^(pytest|api|ui|custom)$")
    language: str | None = Field(None, max_length=20)
    framework: str | None = Field(None, max_length=50)
    template_content: str | None = None
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = None


class ScriptTemplateOut(BaseModel):
    id: int
    name: str
    script_type: str
    language: str
    framework: str | None
    template_content: str
    description: str | None
    is_active: bool
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
