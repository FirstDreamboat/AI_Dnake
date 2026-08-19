"""脚本模板接口（FR-6.4 自定义模板）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_perm
from app.database import get_db
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.script_template import (
    ScriptTemplateCreate,
    ScriptTemplateOut,
    ScriptTemplateUpdate,
)
from app.services import script_template_service

router = APIRouter()


@router.get("")
def list_templates(
    script_type: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """模板列表（登录用户可读）"""
    rows, total = script_template_service.list_templates(db, page, page_size, script_type, keyword)
    return ok(PageData(list=rows, total=total, page=page, page_size=page_size))


@router.get("/all")
def list_all_templates(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """全部启用模板（用于生成对话框下拉）"""
    rows, _ = script_template_service.list_templates(db, 1, 200)
    return ok([r for r in rows if r["is_active"]])


@router.post("")
def create_template(
    req: ScriptTemplateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("script_template")),
):
    """创建模板（需 script_template 权限）"""
    t = script_template_service.create_template(db, req, user.id)
    return ok(ScriptTemplateOut.model_validate(t), "模板创建成功")


@router.put("/{template_id}")
def update_template(
    template_id: int,
    req: ScriptTemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("script_template")),
):
    """更新模板（需 script_template 权限）"""
    t = script_template_service.update_template(db, template_id, req)
    return ok(ScriptTemplateOut.model_validate(t), "模板更新成功")


@router.delete("/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("script_template")),
):
    """删除模板（需 script_template 权限）"""
    script_template_service.delete_template(db, template_id)
    return ok(None, "模板删除成功")
