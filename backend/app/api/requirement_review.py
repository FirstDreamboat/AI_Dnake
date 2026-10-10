"""需求质量体检接口

把"测试用例生成平台"的能力重新出口为"需求质量体检工具"——上传 PRD 即出体检报告，
面向产品/研发在提测前发现需求缺陷。报告落库，支持随时查看与下载 PDF。
"""
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import BusinessError, NotFoundError
from app.database import get_db
from app.models.user import User
from app.schemas.common import PageData, ok
from app.services import document_service, requirement_review_service
from app.services.report_pdf import generate_report_pdf

router = APIRouter()

_SUPPORTED = {"md", "txt", "docx", "doc", "pdf", "png", "jpg", "jpeg", "webp", "gif"}


@router.post("/analyze")
def analyze_requirement(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传需求文档，AI 做质量体检并落库返回报告"""
    if not file.filename:
        raise BusinessError("请上传文件")
    ext = Path(file.filename).suffix.lower().lstrip(".")
    if ext not in _SUPPORTED:
        raise BusinessError(f"暂不支持 {ext} 文件，请上传 md/txt/docx/pdf 或图片")

    saved_path, file_type = document_service.save_upload_file(
        file, settings.upload_dir, title=file.filename
    )
    try:
        report = requirement_review_service.review_requirement(saved_path, file_type)
        rep = requirement_review_service.save_report(db, user.id, file.filename, report)
        report["id"] = rep.id
        report["filename"] = rep.filename
        report["created_at"] = rep.created_at
    except ValueError as e:
        raise BusinessError(str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise BusinessError(f"需求体检失败: {e}") from e
    finally:
        try:
            Path(saved_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    return ok(report, "需求体检完成")


@router.get("/reports")
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """历史体检报告列表（管理员看全部，其他角色只看自己的）"""
    target_uid = None if user.role == "admin" else user.id
    items, total = requirement_review_service.list_reports(db, target_uid, page, page_size)
    return ok(PageData(list=items, total=total, page=page, page_size=page_size))


@router.get("/reports/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看某份体检报告详情"""
    rep = requirement_review_service.get_report(db, report_id)
    if not rep or (user.role != "admin" and rep.user_id != user.id):
        raise NotFoundError("报告不存在")
    return ok(requirement_review_service.to_dict(rep))


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载某份体检报告为 PDF"""
    rep = requirement_review_service.get_report(db, report_id)
    if not rep or (user.role != "admin" and rep.user_id != user.id):
        raise NotFoundError("报告不存在")
    report = requirement_review_service.to_dict(rep)
    pdf = generate_report_pdf(report)
    fname = (rep.filename or "report").rsplit(".", 1)[0] + "_体检报告.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )
