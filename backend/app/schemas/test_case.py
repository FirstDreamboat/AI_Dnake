"""测试用例相关数据模型"""
from datetime import datetime

from pydantic import BaseModel, Field


class TestStep(BaseModel):
    step_no: int
    action: str
    expected: str | None = None


class TestCaseCreate(BaseModel):
    project_id: int
    test_point_id: int | None = None
    title: str = Field(..., min_length=1, max_length=200)
    module: str | None = None  # 所属模块，如"登录注册"
    preconditions: str | None = None
    steps: list[TestStep] = []
    expected_result: str
    priority: str = Field("P2", pattern="^(P0|P1|P2|P3|P4)$")
    test_type: str = "功能测试"
    source: str = Field("manual", pattern="^(ai|manual|ai_reviewed)$")


class TestCaseUpdate(BaseModel):
    test_point_id: int | None = None
    title: str | None = None
    preconditions: str | None = None
    steps: list[TestStep] | None = None
    expected_result: str | None = None
    priority: str | None = Field(None, pattern="^(P0|P1|P2|P3|P4)$")
    test_type: str | None = None


class ReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: str | None = None


class ExportRequest(BaseModel):
    case_ids: list[int]
    format: str = Field("excel", pattern="^(excel|markdown|json|xmind)$")


class BatchRequest(BaseModel):
    case_ids: list[int]
    action: str = Field(..., pattern="^(approve|delete)$")


class FeedbackRequest(BaseModel):
    """AI 生成质量反馈：good(质量好) | bad(质量差) | clear(清除反馈)"""
    feedback: str = Field(..., pattern="^(good|bad|clear)$")


class TestCaseOut(BaseModel):
    id: int
    case_no: str
    project_id: int
    test_point_id: int | None
    title: str
    module: str | None = None
    preconditions: str | None
    steps: list[dict]
    expected_result: str
    priority: str
    test_type: str
    source: str
    status: str
    feedback: str | None = None
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestCaseVersionOut(BaseModel):
    id: int
    case_id: int
    version: int
    content: dict
    change_log: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
