"""测试点相关数据模型"""
from datetime import datetime

from pydantic import BaseModel, Field


# 设计技术取值：与 agents/test_point_extractor.ALL_TECHNIQUES 保持一致，
# 用于接口层校验，避免前端传入非法值污染统计口径
_TECHNIQUE_PATTERN = (
    "^(equivalence|boundary|decision_table|state_transition|"
    "scenario|orthogonal|error_guessing|none)$"
)


class TestPointCreate(BaseModel):
    document_id: int
    project_id: int
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field("function", pattern="^(function|boundary|exception|performance|security|implicit)$")
    technique: str = Field("none", pattern=_TECHNIQUE_PATTERN)
    description: str | None = None


class TestPointUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    technique: str | None = Field(None, pattern=_TECHNIQUE_PATTERN)
    description: str | None = None


class TestPointOut(BaseModel):
    id: int
    document_id: int
    project_id: int
    name: str
    type: str
    technique: str | None
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
