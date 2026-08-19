"""需求文档接口"""
import re
import time

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.document import DocumentOut, URLParseRequest
from app.services import document_service

router = APIRouter()


@router.post("/upload")
def upload_document(
    project_id: int = Form(...),
    file: UploadFile = File(...),
    source_type: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传需求文档"""
    file_path, file_type = document_service.save_upload_file(file, settings.upload_dir / "documents")
    doc = Document(
        project_id=project_id,
        title=file.filename or "未命名文档",
        file_path=file_path,
        file_type=file_type,
        source_type=source_type or "upload",
        parse_status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return ok(DocumentOut.model_validate(doc), "文档上传成功")


@router.post("/parse-url")
def parse_url_document(
    req: URLParseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """FR-1.2 平台链接解析: 抓取 URL 内容并保存为需求文档"""
    title, text = document_service.fetch_url_content(req.url)
    safe_name = re.sub(r"[^\w.\-]", "_", title)[:60] or "url_doc"
    file_path = settings.upload_dir / "documents" / f"{int(time.time() * 1000)}_{safe_name}.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")
    doc = Document(
        project_id=req.project_id,
        title=req.title or title,
        file_path=str(file_path),
        file_type="md",
        source_type="url",
        source_url=req.url,
        parse_status="done",
        parse_result={"chars": len(text), "source_url": req.url},
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return ok(DocumentOut.model_validate(doc), "链接解析成功，已保存为需求文档")


@router.get("")
def list_documents(
    project_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Document)
    if project_id:
        stmt = stmt.where(Document.project_id == project_id)
    total = len(db.scalars(stmt).all())
    docs = db.scalars(stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return ok(PageData(list=[DocumentOut.model_validate(d) for d in docs], total=total, page=page, page_size=page_size))


@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise NotFoundError("文档不存在")
    return ok(DocumentOut.model_validate(doc))


@router.post("/{document_id}/parse")
def parse_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """触发文档解析，并可选向量化入库"""
    doc, text = document_service.parse_document(db, document_id)
    return ok({"document_id": doc.id, "chars": len(text), "parse_status": doc.parse_status}, "解析完成")


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise NotFoundError("文档不存在")
    db.delete(doc)
    db.commit()
    return ok(message="文档删除成功")
