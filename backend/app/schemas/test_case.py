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
    # L1~L4 = 《测试用例等级定义规范》等级（新）；P0~P4 保留以兼容历史数据
    priority: str = Field("L2", pattern="^(L1|L2|L3|L4|P0|P1|P2|P3|P4)$")
    test_type: str = "功能测试"
    source: str = Field("manual", pattern="^(ai|manual|ai_reviewed)$")


class TestCaseUpdate(BaseModel):
    test_point_id: int | None = None
    title: str | None = None
    preconditions: str | None = None
    steps: list[TestStep] | None = None
    expected_result: str | None = None
    priority: str | None = Field(None, pattern="^(L1|L2|L3|L4|P0|P1|P2|P3|P4)$")
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


class SelfCheckRequest(BaseModel):
    """AI 自查请求：case_ids(指定用例) 与 task_id(整批生成任务) 至少传一个"""
    case_ids: list[int] = []
    task_id: int | None = None


class DedupCleanupRequest(BaseModel):
    """重复扫描后批量清理请求：先 dry_run=True 预览，确认后 dry_run=False 执行"""
    case_ids: list[int] = []
    task_id: int | None = None
    dry_run: bool = True


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
    # AI 自查备注（生成时/手动触发的用例自查结论，无问题为空）
    ai_remark: str | None = None
    ai_checked_at: datetime | None = None
    # 重复扫描结构化标注：dup_group_no 非空表示被标为疑似重复；dup_keep_case_id 指向本组代表用例
    dup_group_no: int | None = None
    dup_keep_case_id: int | None = None
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
