"""项目管理服务"""
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.document import Document
from app.models.generation_task import GenerationTask
from app.models.project import Project
from app.models.test_case import TestCase, TestCaseVersion
from app.models.test_point import TestPoint
from app.models.test_script import TestScript
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
    """删除项目及其全部关联数据。

    项目关联文档/测试点/用例(含版本)/脚本/生成任务。SQLite 外键约束默认关闭、
    MySQL 默认开启，均不依赖数据库级联，必须按子表→主表顺序显式清理，
    否则删除会因外键约束/悬空引用失败。

    除按 project_id 外，同时按 document_id / test_point_id / case_id 维度清理，
    覆盖历史脏数据（如生成任务/测试点/用例的归属字段与文档项目不一致）导致的外键残留。
    """
    project = get_project(db, project_id)
    doc_ids = select(Document.id).where(Document.project_id == project_id)
    point_ids = select(TestPoint.id).where(TestPoint.project_id == project_id)
    case_ids = select(TestCase.id).where(
        or_(TestCase.project_id == project_id, TestCase.test_point_id.in_(point_ids))
    )
    # 1. 用例版本（引用用例）
    db.execute(delete(TestCaseVersion).where(TestCaseVersion.case_id.in_(case_ids)))
    # 2. 脚本（引用项目/用例）
    db.execute(delete(TestScript).where(or_(TestScript.project_id == project_id, TestScript.case_id.in_(case_ids))))
    # 3. 用例（引用项目/测试点）
    db.execute(delete(TestCase).where(or_(TestCase.project_id == project_id, TestCase.test_point_id.in_(point_ids))))
    # 4. 测试点（引用项目/文档）
    db.execute(delete(TestPoint).where(or_(TestPoint.project_id == project_id, TestPoint.document_id.in_(doc_ids))))
    # 5. 生成任务（引用项目/文档）
    db.execute(delete(GenerationTask).where(or_(GenerationTask.project_id == project_id, GenerationTask.document_id.in_(doc_ids))))
    # 6. 文档（引用项目）
    db.execute(delete(Document).where(Document.project_id == project_id))
    # 7. 用例文件（引用项目）：连同磁盘存储一并清理
    from app.models.case_file import CaseFile

    case_files = db.scalars(select(CaseFile).where(CaseFile.project_id == project_id)).all()
    for cf in case_files:
        try:
            from app.services import case_file_service as _cfs

            _cfs.resolve_stored_path(cf.stored_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.execute(delete(CaseFile).where(CaseFile.project_id == project_id))
    # 8. 项目
    db.delete(project)
    db.commit()


def get_project_stats(db: Session, project_id: int) -> ProjectStats:
    doc_count = db.scalar(select(func.count(Document.id)).where(Document.project_id == project_id)) or 0
    case_count = db.scalar(select(func.count(TestCase.id)).where(TestCase.project_id == project_id)) or 0
    task_count = db.scalar(select(func.count(GenerationTask.id)).where(GenerationTask.project_id == project_id)) or 0
    script_count = db.scalar(select(func.count(TestScript.id)).where(TestScript.project_id == project_id)) or 0
    # 覆盖率：已关联测试点的测试点覆盖情况（简化：用例数/测试点数）
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
