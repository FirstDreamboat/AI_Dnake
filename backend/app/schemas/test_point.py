"""测试点相关数据模型"""
from datetime import datetime

from pydantic import BaseModel, Field


class TestPointCreate(BaseModel):
    document_id: int
    project_id: int
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field("function", pattern="^(function|boundary|exception|performance|security|implicit)$")
    description: str | None = None


class TestPointUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    description: str | None = None


class TestPointOut(BaseModel):
    id: int
    document_id: int
    project_id: int
    name: str
    type: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
