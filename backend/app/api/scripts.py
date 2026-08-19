"""测试脚本接口"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.script import (
    ScriptCreate,
    ScriptGenerateRequest,
    ScriptOut,
    ScriptUpdate,
)
from app.services import script_service

router = APIRouter()


@router.post("/generate")
def generate_scripts(
    req: ScriptGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """根据选中的测试用例生成自动化脚本（调用 LLM，耗时可能较长）"""
    result = script_service.generate_scripts(
        db, req.case_ids, req.script_type, req.custom_prompt, req.template_id
    )
    return ok(result, "脚本生成成功")


@router.post("")
def save_script(
    req: ScriptCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存生成的脚本"""
    script = script_service.save_script(
        db,
        req.project_id,
        req.case_id,
        req.name,
        req.script_type,
        req.language,
        req.framework,
        req.content,
        req.description,
        user.id,
    )
    return ok(ScriptOut.model_validate(script), "脚本保存成功")


@router.get("")
def list_scripts(
    project_id: int | None = Query(None),
    case_id: int | None = Query(None),
    script_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scripts, total = script_service.list_scripts(
        db, page, page_size, project_id, case_id, script_type
    )
    return ok(PageData(list=scripts, total=total, page=page, page_size=page_size))


@router.get("/{script_id}")
def get_script(
    script_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    script = script_service.get_script(db, script_id)
    return ok(ScriptOut.model_validate(script))


@router.put("/{script_id}")
def update_script(
    script_id: int,
    req: ScriptUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    script = script_service.update_script(db, script_id, req)
    return ok(ScriptOut.model_validate(script), "脚本更新成功")


@router.delete("/{script_id}")
def delete_script(
    script_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    script_service.delete_script(db, script_id)
    return ok(None, "脚本删除成功")


@router.get("/{script_id}/download")
def download_script(
    script_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载脚本为 .py 文件"""
    script = script_service.get_script(db, script_id)
    filename = script.name.replace(" ", "_") + ".py"
    return PlainTextResponse(
        script.content,
        media_type="text/x-python; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
