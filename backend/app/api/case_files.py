"""用例文件接口：项目内 Excel 上传 / 在线单人编辑 / 下载 / 删除"""
import time

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import BusinessError, NotFoundError
from app.database import get_db
from app.models.case_file import CaseFile
from app.models.user import User
from app.schemas.common import ok
from app.services import case_file_service as svc

router = APIRouter()


def _out(cf: CaseFile, user: User, uploaded_by_name: str | None = None) -> dict:
    lock = svc.lock_info(cf.id, user.id)
    return {
        "id": cf.id,
        "project_id": cf.project_id,
        "filename": cf.filename,
        "file_size": cf.file_size,
        "uploaded_by": cf.uploaded_by,
        "uploaded_by_name": uploaded_by_name,
        "created_at": cf.created_at.isoformat(sep=" ") if cf.created_at else None,
        "updated_at": cf.updated_at.isoformat(sep=" ") if cf.updated_at else None,
        "lock": lock,
        "can_delete": (user.role == "admin") or (cf.uploaded_by == user.id),
    }


@router.post("/upload")
def upload_case_file(
    project_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传用例表（xlsx/csv，csv 自动转 xlsx），单文件 ≤10MB"""
    stored_path, display_name = svc.save_upload_file(file, file.filename or "")
    cf = CaseFile(
        project_id=project_id,
        filename=display_name,
        stored_path=str(stored_path.relative_to(svc.settings.upload_dir)),
        file_size=stored_path.stat().st_size,
        uploaded_by=user.id,
    )
    db.add(cf)
    db.commit()
    db.refresh(cf)
    return ok(_out(cf, user, user.username), "上传成功，可直接在线编辑")


@router.get("")
def list_case_files(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """项目下的用例文件列表（含实时锁状态）"""
    cfs = (
        db.query(CaseFile)
        .filter(CaseFile.project_id == project_id)
        .order_by(CaseFile.updated_at.desc())
        .all()
    )
    from app.models.user import User as UserModel

    name_map = {u.id: u.username for u in db.query(UserModel).all()}
    return ok([_out(cf, user, name_map.get(cf.uploaded_by)) for cf in cfs])


@router.post("/{file_id}/open")
def open_case_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """打开文件：尝试抢编辑锁，抢到=可编辑，没抢到=只读并返回持有人"""
    cf = db.get(CaseFile, file_id)
    if not cf:
        raise NotFoundError("文件不存在")
    lock = svc.try_acquire_lock(cf.id, user.id, user.username)
    uploader = db.get(User, cf.uploaded_by) if cf.uploaded_by else None
    return ok({"file": _out(cf, user, uploader.username if uploader else None), "lock": lock})


@router.post("/{file_id}/heartbeat")
def heartbeat(file_id: int, user: User = Depends(get_current_user)):
    """编辑页每 30s 心跳续锁；失联 90s 后锁自动过期释放"""
    ok_flag = svc.heartbeat_lock(file_id, user.id)
    if not ok_flag:
        raise BusinessError("编辑锁已失效，请刷新页面重新获取", http_status=409)
    return ok({"ttl": svc._LOCK_TTL})


@router.post("/{file_id}/release")
def release(file_id: int, user: User = Depends(get_current_user)):
    """退出编辑页时主动释放锁"""
    svc.release_lock(file_id, user.id)
    return ok(None, "已释放")


@router.post("/{file_id}/save")
def save_case_file(
    file_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存编辑内容（必须持有有效编辑锁；未持锁返回 409）"""
    cf = db.get(CaseFile, file_id)
    if not cf:
        raise NotFoundError("文件不存在")
    svc.check_lock_for_save(cf.id, user.id)
    data = file.file.read()
    if len(data) > svc.MAX_FILE_SIZE:
        raise BusinessError("保存内容超过 10MB 上限")
    target = svc.resolve_stored_path(cf.stored_path)
    # 先落临时文件再原子替换，避免保存中途崩溃损坏原文件
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    cf.file_size = len(data)
    from datetime import datetime

    cf.updated_at = datetime.now()  # 强制刷新时间戳（同尺寸写入时 ORM 不会触发 onupdate）
    db.commit()
    return ok({"saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}, "保存成功")


@router.get("/{file_id}/download")
def download_case_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载文件（在线编辑器加载内容也走此接口）"""
    cf = db.get(CaseFile, file_id)
    if not cf:
        raise NotFoundError("文件不存在")
    path = svc.resolve_stored_path(cf.stored_path)
    if not path.exists():
        raise NotFoundError("文件存储已丢失，请联系管理员")
    return FileResponse(path, filename=cf.filename)


@router.delete("/{file_id}")
def delete_case_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除文件：仅上传人本人或 admin；持锁编辑中不允许删"""
    cf = db.get(CaseFile, file_id)
    if not cf:
        raise NotFoundError("文件不存在")
    if user.role != "admin" and cf.uploaded_by != user.id:
        raise BusinessError("仅上传人或管理员可删除该文件", http_status=403)
    lock = svc.lock_info(cf.id, user.id)
    if lock["locked"]:
        raise BusinessError(f"文件正被 {lock['holder_name']} 编辑中，无法删除")
    path = svc.resolve_stored_path(cf.stored_path)
    if path.exists():
        path.unlink()
    db.delete(cf)
    db.commit()
    return ok(None, "删除成功")
