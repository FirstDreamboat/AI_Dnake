"""测试点接口"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.test_case import TestCase, TestCaseVersion
from app.models.test_point import TestPoint
from app.models.test_script import TestScript
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.test_point import TestPointCreate, TestPointOut, TestPointUpdate

router = APIRouter()


@router.get("")
def list_test_points(
    document_id: int | None = Query(None),
    project_id: int | None = Query(None),
    type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(TestPoint)
    if document_id:
        stmt = stmt.where(TestPoint.document_id == document_id)
    if project_id:
        stmt = stmt.where(TestPoint.project_id == project_id)
    if type:
        stmt = stmt.where(TestPoint.type == type)
    total = len(db.scalars(stmt).all())
    points = db.scalars(stmt.order_by(TestPoint.id).offset((page - 1) * page_size).limit(page_size)).all()
    return ok(PageData(list=[TestPointOut.model_validate(p) for p in points], total=total, page=page, page_size=page_size))


@router.post("")
def create_test_point(
    req: TestPointCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    point = TestPoint(**req.model_dump())
    db.add(point)
    db.commit()
    db.refresh(point)
    return ok(TestPointOut.model_validate(point), "测试点创建成功")


@router.get("/{point_id}")
def get_test_point(
    point_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    point = db.get(TestPoint, point_id)
    if not point:
        raise NotFoundError("测试点不存在")
    return ok(TestPointOut.model_validate(point))


@router.put("/{point_id}")
def update_test_point(
    point_id: int,
    req: TestPointUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    point = db.get(TestPoint, point_id)
    if not point:
        raise NotFoundError("测试点不存在")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            setattr(point, k, v)
    db.commit()
    db.refresh(point)
    return ok(TestPointOut.model_validate(point), "测试点更新成功")


@router.delete("/{point_id}")
def delete_test_point(
    point_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    point = db.get(TestPoint, point_id)
    if not point:
        raise NotFoundError("测试点不存在")
    # 测试点被用例引用（test_case.test_point_id 外键）：先删用例版本/脚本 → 用例 → 测试点
    case_ids = select(TestCase.id).where(TestCase.test_point_id == point_id)
    db.execute(delete(TestCaseVersion).where(TestCaseVersion.case_id.in_(case_ids)))
    db.execute(delete(TestScript).where(TestScript.case_id.in_(case_ids)))
    db.execute(delete(TestCase).where(TestCase.test_point_id == point_id))
    db.delete(point)
    db.commit()
    return ok(message="测试点删除成功")
