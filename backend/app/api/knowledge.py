"""知识库接口"""
import threading

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import SessionLocal, get_db
from app.models.knowledge import KnowledgeDoc, KnowledgeDocVersion
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.knowledge import (
    KnowledgeChatRequest,
    KnowledgeChatResponse,
    KnowledgeDocOut,
    KnowledgeDocVersionOut,
    KnowledgeHit,
    KnowledgeSearchRequest,
)
from app.services import document_service
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service

router = APIRouter()

# 产品线（业务域）合法取值，与 project.product_line 保持一致
VALID_PRODUCT_LINES = {"intercom", "smart_home", "hospital"}


def _normalize_product_line(value: str | None) -> str | None:
    """产品线参数归一化：空串/非法值一律视为通用知识（None）"""
    if not value:
        return None
    return value if value in VALID_PRODUCT_LINES else None


def _async_vectorize(doc_id: int) -> None:
    """后台线程执行向量化，避免阻塞上传/批量接口"""
    try:
        with SessionLocal() as db:
            kd = db.get(KnowledgeDoc, doc_id)
            if not kd or kd.vector_status == "indexed":
                return
            if not kd.content:
                kd.vector_status = "failed"
                kd.vector_error = "文档无内容，无法向量化"
                db.commit()
                return
            kd.vector_status = "indexing"
            kd.vector_error = None
            db.commit()
            try:
                chunk_count = rag_service.index_document(kd, kd.content)
            except Exception as e:  # noqa: BLE001 - 失败原因记录到库中
                kd.vector_status = "failed"
                kd.vector_error = str(e)[:500]
                db.commit()
                return
            kd.chunk_count = chunk_count
            kd.vector_status = "indexed"
            kd.vector_error = None
            db.commit()
    except Exception:  # noqa: BLE001 - 后台任务异常不应影响主流程
        pass


@router.get("/docs")
def list_knowledge(
    doc_type: str | None = Query(None),
    product_line: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(KnowledgeDoc)
    if doc_type:
        stmt = stmt.where(KnowledgeDoc.doc_type == doc_type)
    if product_line:
        stmt = stmt.where(KnowledgeDoc.product_line == _normalize_product_line(product_line))
    total = len(db.scalars(stmt).all())
    docs = db.scalars(stmt.order_by(KnowledgeDoc.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return ok(PageData(list=[KnowledgeDocOut.model_validate(d) for d in docs], total=total, page=page, page_size=page_size))


@router.post("/docs/upload")
def upload_knowledge(
    doc_type: str = Form("test_case"),
    product_line: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传知识库文档（同名同类型同产品线文档自动增量更新并递增版本）"""
    product_line = _normalize_product_line(product_line)
    file_path, file_type = document_service.save_upload_file(file, settings.upload_dir / "knowledge")
    text = document_service.parse_document_file(file_path, file_type)
    title = file.filename or "未命名知识文档"
    # 同名同类型同产品线文档：增量更新，版本号 +1，旧向量数据清理后重新入库
    existing = db.scalars(
        select(KnowledgeDoc).where(
            KnowledgeDoc.title == title,
            KnowledgeDoc.doc_type == doc_type,
            KnowledgeDoc.product_line == product_line,
        )
    ).first()
    if existing:
        # FR-4.4 版本管理：更新前保存旧版本快照
        db.add(
            KnowledgeDocVersion(
                doc_id=existing.id,
                version=existing.version,
                title=existing.title,
                content=existing.content,
                file_path=existing.file_path,
                change_log=f"增量更新至 v{(existing.version or 1) + 1}",
                created_by=user.id,
            )
        )
        rag_service.delete_document(existing.id)
        existing.file_path = file_path
        existing.content = text
        existing.chunk_count = 0
        existing.vector_status = "pending"
        existing.vector_error = None
        existing.version = (existing.version or 1) + 1
        db.commit()
        db.refresh(existing)
        # 上传成功后自动后台向量化
        threading.Thread(target=_async_vectorize, args=(existing.id,), daemon=True).start()
        return ok(KnowledgeDocOut.model_validate(existing), f"知识文档已更新（v{existing.version}），正在后台向量化")

    kd = KnowledgeDoc(
        doc_type=doc_type,
        product_line=product_line,
        title=title,
        file_path=file_path,
        content=text,
        version=1,
        created_by=user.id,
    )
    db.add(kd)
    db.commit()
    db.refresh(kd)
    # 上传成功后自动后台向量化
    threading.Thread(target=_async_vectorize, args=(kd.id,), daemon=True).start()
    return ok(KnowledgeDocOut.model_validate(kd), "知识文档上传成功，正在后台向量化")


@router.get("/docs/{doc_id}")
def get_knowledge(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kd = db.get(KnowledgeDoc, doc_id)
    if not kd:
        raise NotFoundError("知识文档不存在")
    # 返回内容详情，供前端预览文档全文
    data = KnowledgeDocOut.model_validate(kd).model_dump()
    data["content"] = kd.content
    return ok(data)


@router.get("/docs/{doc_id}/versions")
def list_knowledge_versions(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """FR-4.4 版本管理：查看文档历史版本列表"""
    kd = db.get(KnowledgeDoc, doc_id)
    if not kd:
        raise NotFoundError("知识文档不存在")
    versions = db.scalars(
        select(KnowledgeDocVersion)
        .where(KnowledgeDocVersion.doc_id == doc_id)
        .order_by(KnowledgeDocVersion.version.desc())
    ).all()
    return ok(
        PageData(
            list=[KnowledgeDocVersionOut.model_validate(v) for v in versions],
            total=len(versions),
            page=1,
            page_size=len(versions),
        )
    )


@router.post("/docs/{doc_id}/vectorize")
def vectorize_doc(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """触发向量化入库（显式重试，同步返回结果）"""
    kd = db.get(KnowledgeDoc, doc_id)
    if not kd:
        raise NotFoundError("知识文档不存在")
    if not kd.content:
        raise NotFoundError("文档无内容，请先上传可解析文件")
    kd.vector_status = "indexing"
    kd.vector_error = None
    db.commit()
    try:
        chunk_count = rag_service.index_document(kd, kd.content)
        kd.chunk_count = chunk_count
        kd.vector_status = "indexed"
        kd.vector_error = None
    except Exception as e:  # noqa: BLE001 - 失败原因记录到库中
        kd.vector_status = "failed"
        kd.vector_error = str(e)[:500]
        db.commit()
        db.refresh(kd)
        return ok(KnowledgeDocOut.model_validate(kd), f"向量化失败: {e}")
    db.commit()
    db.refresh(kd)
    return ok(KnowledgeDocOut.model_validate(kd), "向量化完成")


@router.post("/docs/vectorize-all")
def vectorize_all(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量后台向量化所有未入库/失败的文档"""
    pending = db.scalars(
        select(KnowledgeDoc).where(KnowledgeDoc.vector_status.in_(["pending", "failed"]))
    ).all()
    for kd in pending:
        kd.vector_status = "indexing"
        kd.vector_error = None
    db.commit()
    for kd in pending:
        threading.Thread(target=_async_vectorize, args=(kd.id,), daemon=True).start()
    return ok(
        {"count": len(pending)},
        f"已提交 {len(pending)} 个文档后台向量化"
        if pending
        else "没有待向量化的文档",
    )


@router.post("/search")
def search_knowledge(
    req: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """检索相似历史知识（FR-4.3 支持 hybrid/vector/keyword 三种模式，可限定产品线）"""
    hits = rag_service.search(
        req.query, top_k=req.top_k, mode=req.mode, product_line=req.product_line
    )
    # 补充文档标题与展示字段
    doc_ids = [h.get("doc_id") for h in hits]
    titles: dict = {}
    if doc_ids:
        for d in db.scalars(select(KnowledgeDoc).where(KnowledgeDoc.id.in_(doc_ids))).all():
            titles[d.id] = d.title
    for h in hits:
        h["title"] = titles.get(h.get("doc_id"), "")
        h["content"] = h.get("text", "")
        h["chunk_index"] = h.get("chunk_id", "")
    return ok({"hits": hits})


@router.post("/chat")
def chat_knowledge(
    req: KnowledgeChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """知识库对话问答（RAG）：检索相关片段 -> 组装上下文 -> LLM 生成回答，附引用来源"""
    hits = rag_service.search(
        req.question, top_k=req.top_k, mode=req.mode, product_line=req.product_line
    )
    # 补充文档标题
    doc_ids = [h.get("doc_id") for h in hits]
    titles: dict = {}
    if doc_ids:
        for d in db.scalars(select(KnowledgeDoc).where(KnowledgeDoc.id.in_(doc_ids))).all():
            titles[d.id] = d.title

    sources: list[KnowledgeHit] = []
    ctx_parts: list[str] = []
    for i, h in enumerate(hits):
        title = titles.get(h.get("doc_id"), "未知文档")
        chunk_index = h.get("chunk_id", "")
        sources.append(
            KnowledgeHit(
                doc_id=h.get("doc_id"),
                title=title,
                chunk_index=chunk_index,
                content=h.get("text", ""),
                score=h.get("score", 0.0),
            )
        )
        ctx_parts.append(f"【参考知识 {i + 1}】（来源：《{title}》#{chunk_index}）\n{h.get('text', '')}")
    context = "\n\n".join(ctx_parts)

    system = (
        "你是「AI 驱动的研发质量前置平台」的知识库问答助手。请严格基于下方提供的参考知识回答用户问题，"
        "不得编造参考知识中不存在的信息；若参考知识不足以回答，请如实说明。回答使用中文，"
        "条理清晰、言简意赅，必要时分点说明。"
    )
    # 携带最近 8 条历史消息以支持多轮追问
    if req.history:
        history_text = "\n".join(
            f"{'用户' if m.role == 'user' else '助手'}: {m.content}" for m in req.history[-8:]
        )
        system += f"\n\n以下为本次对话的历史消息（供理解上下文，请勿复述）：\n{history_text}"

    if context:
        prompt = f"【参考知识】\n{context}\n\n【用户问题】\n{req.question}"
    else:
        prompt = f"知识库中未检索到相关内容。请直接回答：{req.question}"

    answer = llm_service.chat(prompt, system=system)
    return ok(KnowledgeChatResponse(answer=answer, sources=sources))


@router.delete("/docs/{doc_id}")
def delete_knowledge(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kd = db.get(KnowledgeDoc, doc_id)
    if not kd:
        raise NotFoundError("知识文档不存在")
    rag_service.delete_document(doc_id)
    db.delete(kd)
    db.commit()
    return ok(message="知识文档删除成功")
