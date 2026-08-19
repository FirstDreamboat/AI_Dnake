"""项目相关数据模型"""
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    product_line: str = Field(..., pattern="^(intercom|smart_home|hospital)$")
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    product_line: str | None = Field(None, pattern="^(intercom|smart_home|hospital)$")
    description: str | None = None
    status: str | None = Field(None, pattern="^(active|archived)$")


class ProjectStats(BaseModel):
    document_count: int = 0
    test_case_count: int = 0
    task_count: int = 0
    script_count: int = 0
    coverage: float = 0.0


class ProjectOut(BaseModel):
    id: int
    name: str
    product_line: str
    description: str | None
    owner_id: int | None
    status: str
    created_at: datetime
    updated_at: datetime
    stats: ProjectStats | None = None

    model_config = {"from_attributes": True}
