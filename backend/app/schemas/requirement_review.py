"""需求体检报告数据模型"""
from datetime import datetime

from pydantic import BaseModel


class ReviewIssue(BaseModel):
    """单个需求质量问题"""
    type: str = ""
    description: str = ""
    requirement: str | None = None
    severity: str = "中"
    suggestion: str | None = None


class ReviewMetrics(BaseModel):
    """体检统计指标"""
    requirement_count: int = 0
    test_point_count: int = 0
    implicit_count: int = 0
    technique_distribution: dict[str, int] = {}


class ReviewReport(BaseModel):
    """需求质量体检报告"""
    id: int | None = None
    filename: str | None = None
    score: int = 0
    summary: str = ""
    metrics: ReviewMetrics = ReviewMetrics()
    issues: list[ReviewIssue] = []
    highlights: list[str] = []
    created_at: datetime | None = None
