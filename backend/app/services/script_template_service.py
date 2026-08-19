"""脚本模板服务（FR-6.4 自定义模板 CRUD）"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError, NotFoundError
from app.models.script_template import ScriptTemplate


def _to_dict(t: ScriptTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "script_type": t.script_type,
        "language": t.language,
        "framework": t.framework,
        "template_content": t.template_content,
        "description": t.description,
        "is_active": t.is_active,
        "created_by": t.created_by,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


def list_templates(
    db: Session,
    page: int,
    page_size: int,
    script_type: str | None = None,
    keyword: str | None = None,
) -> tuple[list[dict], int]:
    stmt = select(ScriptTemplate)
    if script_type:
        stmt = stmt.where(ScriptTemplate.script_type == script_type)
    if keyword:
        stmt = stmt.where(ScriptTemplate.name.contains(keyword))
    total = len(db.scalars(stmt).all())
    rows = db.scalars(
        stmt.order_by(ScriptTemplate.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [_to_dict(r) for r in rows], total


def get_template(db: Session, template_id: int) -> ScriptTemplate:
    t = db.get(ScriptTemplate, template_id)
    if not t:
        raise NotFoundError("模板不存在")
    return t


def create_template(db: Session, req, user_id: int) -> ScriptTemplate:
    exists = db.scalar(select(ScriptTemplate).where(ScriptTemplate.name == req.name))
    if exists:
        raise BusinessError(f"模板名称「{req.name}」已存在")
    t = ScriptTemplate(
        name=req.name,
        script_type=req.script_type,
        language=req.language,
        framework=req.framework or "",
        template_content=req.template_content,
        description=req.description,
        is_active=req.is_active,
        created_by=user_id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def update_template(db: Session, template_id: int, req) -> ScriptTemplate:
    t = get_template(db, template_id)
    if req.name is not None and req.name != t.name:
        exists = db.scalar(select(ScriptTemplate).where(ScriptTemplate.name == req.name))
        if exists:
            raise BusinessError(f"模板名称「{req.name}」已存在")
        t.name = req.name
    if req.script_type is not None:
        t.script_type = req.script_type
    if req.language is not None:
        t.language = req.language
    if req.framework is not None:
        t.framework = req.framework
    if req.template_content is not None:
        t.template_content = req.template_content
    if req.description is not None:
        t.description = req.description
    if req.is_active is not None:
        t.is_active = req.is_active
    db.commit()
    db.refresh(t)
    return t


def delete_template(db: Session, template_id: int) -> None:
    t = get_template(db, template_id)
    db.delete(t)
    db.commit()
