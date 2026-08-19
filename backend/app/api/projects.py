"""项目管理接口"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import project_service

router = APIRouter()


@router.get("")
def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
    product_line: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    projects, total = project_service.list_projects(db, page, page_size, keyword, product_line, status)
    # 附加统计信息
    data = []
    for p in projects:
        out = ProjectOut.model_validate(p)
        out.stats = project_service.get_project_stats(db, p.id)
        data.append(out)
    return ok(PageData(list=data, total=total, page=page, page_size=page_size))


@router.post("")
def create_project(
    req: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_service.create_project(db, req, user.id)
    return ok(project, "项目创建成功")


@router.get("/{project_id}")
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_service.get_project(db, project_id)
    out = ProjectOut.model_validate(project)
    out.stats = project_service.get_project_stats(db, project_id)
    return ok(out)


@router.put("/{project_id}")
def update_project(
    project_id: int,
    req: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_service.update_project(db, project_id, req)
    return ok(project, "项目更新成功")


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    manager: User = Depends(require_role("admin", "manager")),
):
    project_service.delete_project(db, project_id)
    return ok(message="项目删除成功")


@router.put("/{project_id}/archive")
def archive_project(
    project_id: int,
    db: Session = Depends(get_db),
    manager: User = Depends(require_role("admin", "manager")),
):
    project = project_service.update_project(
        db, project_id, ProjectUpdate(status="archived")
    )
    return ok(project, "项目已归档")
