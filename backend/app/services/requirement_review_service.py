"""需求质量体检服务：编排 解析→需求提取→测试点提取→质量评审，输出体检报告

复用现有三个智能体；体检结果落库（ui_review_report），支持随时查看与导出 PDF。
"""
import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.requirement_parser import RequirementParserAgent
from app.agents.requirement_reviewer import RequirementReviewerAgent
from app.agents.test_point_extractor import TestPointExtractorAgent
from app.models.ui_review_report import UIReviewReport
from app.services.document_service import parse_document_file

logger = logging.getLogger(__name__)


def review_requirement(file_path: str, file_type: str) -> dict:
    """对一份需求文档做质量体检，返回报告 dict（不落库）"""
    if not Path(file_path).exists():
        raise FileNotFoundError(file_path)

    text = parse_document_file(file_path, file_type)
    if not text or not text.strip():
        raise ValueError("文档解析后内容为空，无法体检")

    requirements = RequirementParserAgent().run(text)
    if not requirements:
        raise ValueError("未从文档中解析出任何需求，无法体检（请确认文档是否为有效需求/PRD）")

    test_points = TestPointExtractorAgent().run(requirements)
    report = RequirementReviewerAgent().run(requirements, test_points)
    return report


def save_report(db: Session, user_id: int, filename: str, report: dict) -> UIReviewReport:
    """体检报告落库，返回 ORM 对象"""
    rep = UIReviewReport(
        user_id=user_id,
        filename=filename[:200],
        score=int(report.get("score") or 0),
        summary=(report.get("summary") or "")[:5000],
        issues=json.dumps(report.get("issues") or [], ensure_ascii=False),
        highlights=json.dumps(report.get("highlights") or [], ensure_ascii=False),
        metrics=json.dumps(report.get("metrics") or {}, ensure_ascii=False),
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return rep


def to_dict(rep: UIReviewReport) -> dict:
    """ORM 转为报告 dict（含解析 JSON 字段）"""
    return {
        "id": rep.id,
        "filename": rep.filename,
        "score": rep.score,
        "summary": rep.summary,
        "metrics": json.loads(rep.metrics or "{}"),
        "issues": json.loads(rep.issues or "[]"),
        "highlights": json.loads(rep.highlights or "[]"),
        "created_at": rep.created_at,
    }


def list_reports(
    db: Session, user_id: int | None, page: int, page_size: int
) -> tuple[list[dict], int]:
    """查询历史体检报告列表（user_id=None 时查全部，供管理员）"""
    stmt = select(UIReviewReport)
    if user_id is not None:
        stmt = stmt.where(UIReviewReport.user_id == user_id)
    stmt = stmt.order_by(UIReviewReport.created_at.desc())
    total = len(db.scalars(stmt).all())
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    # 列表只返回摘要信息，避免传整份 issues
    return (
        [
            {
                "id": r.id,
                "filename": r.filename,
                "score": r.score,
                "summary": (r.summary or "")[:80],
                "created_at": r.created_at,
            }
            for r in items
        ],
        total,
    )


def get_report(db: Session, report_id: int) -> UIReviewReport | None:
    return db.get(UIReviewReport, report_id)
