"""用例生成任务相关数据模型"""
from datetime import datetime

from pydantic import BaseModel, Field


class GenerateOptions(BaseModel):
    include_types: list[str] = Field(
        default_factory=lambda: ["function", "boundary", "exception"]
    )
    # 用例等级：默认对齐《测试用例等级定义规范》的 L1~L4 四级（历史数据中的 P0~P4 仍可传入）
    priority_levels: list[str] = Field(default_factory=lambda: ["L1", "L2", "L3", "L4"])
    enable_rag: bool = True
    reference_count: int = Field(5, ge=1, le=20)
    case_multiplier: int = Field(
        2, ge=1, le=5, description="生成倍数：每个测试点生成的用例条数基准（1x=1条/点…5x=5条/点）"
    )
    replace_existing: bool = Field(
        False, description="覆盖重建：生成前清空所选文档名下原有测试点与用例，防止旧数据/幻象点残留累积"
    )
    auto_dedup: bool = Field(
        True,
        description="生成完成后自动对本批用例执行一次重复扫描标注（打【疑似重复·组N】，只标不删），失败不影响生成结果",
    )
    dedup_on_generate: bool = Field(
        True,
        description="入库前防重：新用例写库前与库内已有用例做操作路径近似比对，高度相似的候选不再写入（保守阈值，避免误杀）",
    )


class GenerateTaskCreate(BaseModel):
    project_id: int
    document_ids: list[int] = Field(..., min_length=1)
    options: GenerateOptions = GenerateOptions()


class GeneratePreviewIn(BaseModel):
    """生成前用例量预估请求"""

    project_id: int
    document_ids: list[int] = Field(..., min_length=1)


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
