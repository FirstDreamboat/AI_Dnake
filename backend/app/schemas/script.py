"""测试脚本相关数据模型"""
from datetime import datetime

from pydantic import BaseModel, Field


class ScriptGenerateRequest(BaseModel):
    """脚本生成请求：选择用例 + 脚本类型"""

    case_ids: list[int] = Field(..., min_length=1)
    script_type: str = Field("pytest", pattern="^(pytest|api|ui|custom)$")
    # 自定义脚本类型的补充要求
    custom_prompt: str | None = Field(None, max_length=1000)
    # FR-6.4 可选：引用自定义模板
    template_id: int | None = None


class ScriptCreate(BaseModel):
    project_id: int
    case_id: int | None = None
    name: str = Field(..., min_length=1, max_length=200)
    script_type: str = Field("pytest", pattern="^(pytest|api|ui|custom)$")
    language: str = Field("python", max_length=20)
    framework: str | None = Field(None, max_length=50)
    content: str = Field(..., min_length=1)
    description: str | None = Field(None, max_length=500)


class ScriptUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = None
    description: str | None = Field(None, max_length=500)


class ScriptOut(BaseModel):
    id: int
    project_id: int
    case_id: int | None
    name: str
    script_type: str
    language: str
    framework: str | None
    content: str
    description: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
