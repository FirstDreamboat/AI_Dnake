"""用例生成任务相关数据模型"""
from datetime import datetime

from pydantic import BaseModel, Field


class GenerateOptions(BaseModel):
    include_types: list[str] = Field(
        default_factory=lambda: ["function", "boundary", "exception"]
    )
    priority_levels: list[str] = Field(default_factory=lambda: ["P0", "P1", "P2", "P3", "P4"])
    enable_rag: bool = True
    reference_count: int = Field(5, ge=1, le=20)


class GenerateTaskCreate(BaseModel):
    project_id: int
    document_ids: list[int] = Field(..., min_length=1)
    options: GenerateOptions = GenerateOptions()


class GenerateTaskOut(BaseModel):
    id: int
    task_no: str
    project_id: int
    document_id: int | None
    status: str
    progress: int
    total_case: int
    result_summary: dict | None
    error_msg: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CoverageItem(BaseModel):
    test_point_id: int
    name: str
    type: str
    covered: bool
    case_count: int


class CoverageOut(BaseModel):
    task_id: int
    total_points: int
    covered_points: int
    coverage_rate: float
    items: list[CoverageItem]
