"""测试脚本生成与管理服务"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.script_generator import ScriptGeneratorAgent
from app.core.exceptions import BusinessError, NotFoundError
from app.models.test_case import TestCase
from app.models.test_script import TestScript


def _to_dict(script: TestScript, project_name: str | None = None) -> dict:
    """ORM 转字典（与 ScriptOut 字段一致）"""
    return {
        "id": script.id,
        "project_id": script.project_id,
        "project_name": project_name,
        "case_id": script.case_id,
        "name": script.name,
        "script_type": script.script_type,
        "language": script.language,
        "framework": script.framework,
        "content": script.content,
        "description": script.description,
        "created_by": script.created_by,
        "created_at": script.created_at,
        "updated_at": script.updated_at,
    }


def generate_scripts(
    db: Session,
    case_ids: list[int],
    script_type: str,
    custom_prompt: str | None = None,
    template_id: int | None = None,
) -> dict:
    """根据用例列表调用 LLM 生成测试脚本（不落库，返回生成结果）

    template_id: FR-6.4 可选，引用自定义模板
    """
    cases = db.scalars(select(TestCase).where(TestCase.id.in_(case_ids))).all()
    if not cases:
        raise NotFoundError("所选测试用例不存在")

    # 校验用例属于同一项目
    project_ids = {c.project_id for c in cases}
    if len(project_ids) > 1:
        raise BusinessError("所选用例必须属于同一个项目")

    case_dicts = [
        {
            "title": c.title,
            "priority": c.priority,
            "test_type": c.test_type,
            "preconditions": c.preconditions,
            "steps": c.steps or [],
            "expected_result": c.expected_result,
        }
        for c in cases
    ]
    # FR-6.4 加载自定义模板
    template = None
    if template_id:
        from app.models.script_template import ScriptTemplate

        t = db.get(ScriptTemplate, template_id)
        if not t:
            raise NotFoundError("所选模板不存在")
        if not t.is_active:
            raise BusinessError("所选模板已被停用")
        template = {
            "name": t.name,
            "framework": t.framework,
            "description": t.description,
            "template_content": t.template_content,
        }
        # 模板类型优先于请求类型
        script_type = t.script_type or script_type
    agent = ScriptGeneratorAgent()
    result = agent.run(
        case_dicts,
        script_type=script_type,
        custom_prompt=custom_prompt or "",
        template=template,
    )
    result["project_id"] = next(iter(project_ids))
    result["case_ids"] = case_ids
    result["script_type"] = script_type
    result["template_id"] = template_id
    return result


def list_scripts(
    db: Session,
    page: int,
    page_size: int,
    project_id: int | None = None,
    case_id: int | None = None,
    script_type: str | None = None,
) -> tuple[list[dict], int]:
    stmt = select(TestScript)
    if project_id:
        stmt = stmt.where(TestScript.project_id == project_id)
    if case_id:
        stmt = stmt.where(TestScript.case_id == case_id)
    if script_type:
        stmt = stmt.where(TestScript.script_type == script_type)
    total = len(db.scalars(stmt).all())
    scripts = db.scalars(
        stmt.order_by(TestScript.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    # 关联项目名称
    from app.models.project import Project

    project_ids = {s.project_id for s in scripts}
    names = {
        p.id: p.name
        for p in db.scalars(select(Project).where(Project.id.in_(project_ids))).all()
    }
    return [_to_dict(s, names.get(s.project_id)) for s in scripts], total


def get_script(db: Session, script_id: int) -> TestScript:
    script = db.get(TestScript, script_id)
    if not script:
        raise NotFoundError("脚本不存在")
    return script


def save_script(
    db: Session,
    project_id: int,
    case_id: int | None,
    name: str,
    script_type: str,
    language: str,
    framework: str | None,
    content: str,
    description: str | None,
    user_id: int,
) -> TestScript:
    script = TestScript(
        project_id=project_id,
        case_id=case_id,
        name=name,
        script_type=script_type,
        language=language,
        framework=framework,
        content=content,
        description=description,
        created_by=user_id,
    )
    db.add(script)
    db.commit()
    db.refresh(script)
    return script


def update_script(db: Session, script_id: int, req) -> TestScript:
    script = get_script(db, script_id)
    if req.name is not None:
        script.name = req.name
    if req.content is not None:
        script.content = req.content
    if req.description is not None:
        script.description = req.description
    db.commit()
    db.refresh(script)
    return script


def delete_script(db: Session, script_id: int) -> None:
    script = get_script(db, script_id)
    db.delete(script)
    db.commit()
