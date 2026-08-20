"""统计与报表接口"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_perm
from app.database import get_db
from app.models.document import Document
from app.models.generation_task import GenerationTask
from app.models.project import Project
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.common import ok
from app.services import project_service

router = APIRouter()

# 英文/缩写 test_type -> 中文规范名（AI 生成或导入时可能产生英文值，统计时统一展示）
_TEST_TYPE_MAP = {
    "function": "功能测试",
    "functional": "功能测试",
    "feature": "功能测试",
    "abnormal": "异常测试",
    "exception": "异常测试",
    "error": "异常测试",
    "boundary": "边界测试",
    "edge": "边界测试",
    "performance": "性能测试",
    "perf": "性能测试",
    "stress": "性能测试",
    "security": "安全测试",
    "safe": "安全测试",
    "interface": "接口测试",
    "api": "接口测试",
    "compatibility": "兼容性测试",
    "usability": "易用性测试",
    "smoke": "冒烟测试",
    "regression": "回归测试",
    "unit": "单元测试",
    "integration": "集成测试",
}


def normalize_test_type(t: str) -> str:
    """将 test_type 规范为中文名；空值归为未分类"""
    if not t or not t.strip():
        return "未分类"
    key = t.strip().lower()
    return _TEST_TYPE_MAP.get(key, t.strip())


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """平台总览统计"""
    from app.models.test_script import TestScript

    return ok(
        {
            "user_count": db.scalar(select(func.count(User.id))) or 0,
            "project_count": db.scalar(select(func.count(Project.id))) or 0,
            "case_count": db.scalar(select(func.count(TestCase.id))) or 0,
            "task_count": db.scalar(select(func.count(GenerationTask.id))) or 0,
            "doc_count": db.scalar(select(func.count(Document.id))) or 0,
            "script_count": db.scalar(select(func.count(TestScript.id))) or 0,
        }
    )


@router.get("/projects/{project_id}")
def project_stats(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """项目维度统计"""
    stats = project_service.get_project_stats(db, project_id)
    # 按来源与优先级分布
    by_source = {
        s: db.scalar(
            select(func.count(TestCase.id)).where(
                TestCase.project_id == project_id, TestCase.source == s
            )
        ) or 0
        for s in ("ai", "manual", "ai_reviewed")
    }
    by_priority = {
        p: db.scalar(
            select(func.count(TestCase.id)).where(
                TestCase.project_id == project_id, TestCase.priority == p
            )
        ) or 0
        for p in ("P0", "P1", "P2", "P3", "P4")
    }
    return ok(
        {
            **stats.model_dump(),
            "by_source": by_source,
            "by_priority": by_priority,
        }
    )


@router.get("/test-types")
def test_types(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("statistics")),
):
    """全局/项目内按测试类型分布统计（需 statistics 权限）"""
    stmt = (
        select(TestCase.test_type, func.count(TestCase.id))
        .group_by(TestCase.test_type)
        .order_by(func.count(TestCase.id).desc())
    )
    if project_id:
        stmt = stmt.where(TestCase.project_id == project_id)
    # 规范化类型后再次聚合，把同义英文值合并到中文类型
    agg: dict[str, int] = {}
    for t, c in db.execute(stmt).all():
        norm = normalize_test_type(t)
        agg[norm] = agg.get(norm, 0) + c
    rows = [{"test_type": k, "count": v} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]
    return ok({"rows": rows})


@router.get("/priorities")
def priorities(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("statistics")),
):
    """全局/项目内按优先级分布统计（需 statistics 权限）"""
    result: dict[str, int] = {p: 0 for p in ("P0", "P1", "P2", "P3", "P4")}
    stmt = select(TestCase.priority, func.count(TestCase.id)).group_by(TestCase.priority)
    if project_id:
        stmt = stmt.where(TestCase.project_id == project_id)
    for p, c in db.execute(stmt).all():
        result[p] = c
    return ok(result)


@router.get("/trend")
def trend(
    days: int = Query(30, ge=7, le=365),
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("statistics")),
):
    """近 N 天用例生成/脚本生成趋势（按天，需 statistics 权限）"""
    since = datetime.now() - timedelta(days=days - 1)
    case_stmt = (
        select(func.date(TestCase.created_at), func.count(TestCase.id))
        .where(TestCase.created_at >= since)
        .group_by(func.date(TestCase.created_at))
    )
    if project_id:
        case_stmt = case_stmt.where(TestCase.project_id == project_id)
    from app.models.test_script import TestScript

    script_stmt = (
        select(func.date(TestScript.created_at), func.count(TestScript.id))
        .where(TestScript.created_at >= since)
        .group_by(func.date(TestScript.created_at))
    )
    if project_id:
        script_stmt = script_stmt.where(TestScript.project_id == project_id)

    def _day_str(v):
        """将数据库返回的日期统一为 YYYY-MM-DD 字符串（兼容 date/datetime/str）"""
        return v.strftime("%Y-%m-%d") if isinstance(v, datetime) else str(v)

    case_map = {_day_str(d): c for d, c in db.execute(case_stmt).all()}
    script_map = {_day_str(d): c for d, c in db.execute(script_stmt).all()}
    dates, case_counts, script_counts = [], [], []
    for i in range(days):
        d = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        dates.append(d)
        case_counts.append(case_map.get(d, 0))
        script_counts.append(script_map.get(d, 0))
    return ok({"dates": dates, "case_counts": case_counts, "script_counts": script_counts})


@router.get("/efficiency")
def efficiency(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """生成效率对比（AI vs 人工，供 POC 验证）"""
    tasks = db.scalars(
        select(GenerationTask).where(GenerationTask.status == "success").order_by(GenerationTask.created_at.desc()).limit(20)
    ).all()
    total_ai_cases = sum(t.total_case for t in tasks)
    return ok(
        {
            "ai_total_cases": total_ai_cases,
            "ai_tasks": len(tasks),
            "avg_cases_per_task": round(total_ai_cases / len(tasks), 1) if tasks else 0,
            # 人工基线（POC 时替换为实测数据）
            "manual_baseline": {"avg_cases_per_day": 20, "avg_time_minutes": 180},
            "ai_avg_time_minutes": 10,
            "note": "效率对比数据来自任务统计，POC 阶段需结合实际人工编写耗时验证",
        }
    )


@router.get("/quality")
def quality(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用例质量分布（按来源）"""
    rows = []
    for source in ("ai", "manual", "ai_reviewed"):
        count = db.scalar(
            select(func.count(TestCase.id)).where(TestCase.source == source)
        ) or 0
        reviewed = db.scalar(
            select(func.count(TestCase.id)).where(
                TestCase.source == source, TestCase.status == "reviewed"
            )
        ) or 0
        rows.append(
            {
                "source": source,
                "count": count,
                "reviewed": reviewed,
                "review_rate": round(reviewed / count * 100, 1) if count else 0,
            }
        )
    return ok({"rows": rows})
