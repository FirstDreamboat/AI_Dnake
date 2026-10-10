"""测试脚本接口"""
from urllib.parse import quote

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


def _content_disposition(filename: str) -> str:
    """生成支持中文文件名的 Content-Disposition（RFC 5987）

    HTTP 响应头只能承载 latin-1 字符，直接拼接中文文件名会被 starlette 拒绝并抛
    UnicodeEncodeError——脚本名含中文时（如"自动化脚本-xxx"）下载必然崩溃。
    改为 filename*=UTF-8''<percent-encoded> 传输，并保留 ASCII 兜底名。
    """
    # 纯中文名整体过滤后会退化成 ".py"（下载产物变成隐藏文件），
    # 因此保留原扩展名、仅对主干做 ASCII 兜底。
    if "." in filename:
        stem, ext = filename.rsplit(".", 1)
        ascii_stem = stem.encode("ascii", "ignore").decode() or "script"
        ascii_name = f"{ascii_stem}.{ext}"
    else:
        ascii_name = filename.encode("ascii", "ignore").decode() or "script"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


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
        headers={"Content-Disposition": _content_disposition(filename)},
    )
