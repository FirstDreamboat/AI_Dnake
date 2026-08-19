"""项目管理服务"""
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.document import Document
from app.models.generation_task import GenerationTask
from app.models.project import Project
from app.models.test_case import TestCase
from app.schemas.project import ProjectCreate, ProjectStats, ProjectUpdate


def list_projects(
    db: Session, page: int, page_size: int, keyword: str | None = None,
    product_line: str | None = None, status: str | None = None,
) -> tuple[list[Project], int]:
    stmt = select(Project)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Project.name.like(like))
    if product_line:
        stmt = stmt.where(Project.product_line == product_line)
    if status:
        stmt = stmt.where(Project.status == status)
    total = len(db.scalars(stmt).all())
    projects = db.scalars(stmt.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return list(projects), total


def create_project(db: Session, req: ProjectCreate, owner_id: int) -> Project:
    project = Project(**req.model_dump(), owner_id=owner_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    return project


def update_project(db: Session, project_id: int, req: ProjectUpdate) -> Project:
    project = get_project(db, project_id)
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(project, k, v)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: int) -> None:
    project = get_project(db, project_id)
    db.delete(project)
    db.commit()


def get_project_stats(db: Session, project_id: int) -> ProjectStats:
    doc_count = db.scalar(select(func.count(Document.id)).where(Document.project_id == project_id)) or 0
    case_count = db.scalar(select(func.count(TestCase.id)).where(TestCase.project_id == project_id)) or 0
    task_count = db.scalar(select(func.count(GenerationTask.id)).where(GenerationTask.project_id == project_id)) or 0
    from app.models.test_script import TestScript

    script_count = db.scalar(select(func.count(TestScript.id)).where(TestScript.project_id == project_id)) or 0
    # 覆盖率：已关联测试点的测试点覆盖情况（简化：用例数/测试点数）
    from app.models.test_point import TestPoint

    point_count = db.scalar(select(func.count(TestPoint.id)).where(TestPoint.project_id == project_id)) or 0
    # 覆盖率：已有关联用例的测试点数 / 总测试点数（与任务覆盖率口径一致，封顶 100）
    covered_point_count = db.scalar(
        select(func.count(func.distinct(TestCase.test_point_id))).where(
            TestCase.project_id == project_id, TestCase.test_point_id.isnot(None)
        )
    ) or 0
    coverage = round(covered_point_count / point_count * 100, 1) if point_count else 0.0
    coverage = min(coverage, 100.0)
    return ProjectStats(
        document_count=doc_count,
        test_case_count=case_count,
        task_count=task_count,
        script_count=script_count,
        coverage=coverage,
    )
