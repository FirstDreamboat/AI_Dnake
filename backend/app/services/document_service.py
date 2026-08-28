"""需求文档解析服务: 支持 PDF / Word / TXT / Markdown / Excel / CSV / 平台链接"""
import csv as _csv
import html
import io
import re
import urllib.parse
from pathlib import Path

import httpx

from app.core.exceptions import BusinessError, NotFoundError
from app.models.document import Document
from app.models.knowledge import KnowledgeDoc
from app.services.rag_service import rag_service
from sqlalchemy.orm import Session

# 支持的文件格式（文本文档 + Excel/CSV + 原型图/设计稿图片 + Axure 原型 .rp）
# 注: .xls 旧格式需额外安装 xlrd，当前环境未安装故不支持
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".md",
    ".xlsx", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".rp",
}


def save_upload_file(file, upload_dir: Path, title: str | None = None) -> tuple[str, str]:
    """保存上传文件，返回 (存储路径, 文件类型)"""
    filename = file.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise BusinessError(f"不支持的文件格式: {ext}，仅支持 {', '.join(SUPPORTED_EXTENSIONS)}")

    # 防止路径穿越与文件名冲突
    safe_name = re.sub(r"[^\w.\-]", "_", filename)
    target = upload_dir / f"{int(__import__('time').time() * 1000)}_{safe_name}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        f.write(file.file.read())
    return str(target), ext.lstrip(".")


IMAGE_TYPES = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}


def parse_document_file(file_path: str, file_type: str) -> str:
    """解析文档为纯文本；图片/原型图优先走视觉模型，未配置时返回占位描述"""
    path = Path(file_path)
    if file_type in IMAGE_TYPES:
        from app.config import settings
        from app.services.llm_service import llm_service

        if settings.VISION_ENABLED and llm_service.vision_health():
            try:
                return llm_service.describe_image(str(path))
            except Exception as e:  # noqa: BLE001
                from app.core.exceptions import BusinessError

                raise BusinessError(f"原型图视觉解析失败: {e}") from e
        provider = settings.VISION_PROVIDER
        if provider == "ollama":
            hint = "请在 backend/.env 设置 VISION_ENABLED=true 并 pull 支持视觉的模型（如 qwen2.5vl:3b）"
        else:
            hint = "请在 backend/.env 设置 VISION_ENABLED=true 并配置 VISION_API_KEY（硅基流动云端视觉模型）"
        return (
            f"[原型图/设计稿] 文件: {path.name}\n"
            f"格式: {file_type.upper()}\n"
            f"说明: 当前未启用视觉模型（VISION_ENABLED=false）或云端 Key 未配置，暂无法自动提取图片中的需求信息。{hint}，"
            "然后重新上传/解析。"
        )
    if file_type == "rp":
        from app.services.rp_parser import extract_rp_text

        try:
            return extract_rp_text(str(path))
        except ValueError as e:
            # 非 Axure 8 二进制或解析不出内容时给出友好提示
            return (
                f"[Axure 原型文件] 文件: {path.name}\n"
                f"解析失败: {e}\n"
                "提示: .rp 为 Axure 原型工程文件，建议在 Axure 中导出为图片（或 HTML 截图）后上传，"
                "系统将调用视觉模型识别原型内容。"
            )
    if file_type == "txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if file_type == "md":
        return path.read_text(encoding="utf-8", errors="ignore")
    if file_type == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if file_type in ("docx", "doc"):
        from docx import Document as DocxDocument
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = DocxDocument(str(path))
        parts: list[str] = []
        # 按文档 body 顺序遍历段落与表格，保持内容先后关系（表格行转 "列: 值" 文本）
        for child in doc.element.body.iterchildren():
            if child.tag == qn("w:p"):
                p = Paragraph(child, doc)
                if p.text.strip():
                    parts.append(p.text.strip())
            elif child.tag == qn("w:tbl"):
                table = Table(child, doc)
                for row in table.rows:
                    cells: list[str] = []
                    prev = None
                    for c in row.cells:
                        t = c.text.strip()
                        # 合并单元格会返回重复引用，连续相同只保留一个
                        if t != prev:
                            cells.append(t)
                            prev = t
                    if cells:
                        parts.append(" | ".join(cells))
        return "\n".join(parts)
    if file_type in ("xlsx", "xls"):
        import pandas as pd

        try:
            xls = pd.ExcelFile(str(path))
        except Exception as e:
            raise BusinessError(f"Excel 解析失败（仅支持 .xlsx）: {e}") from e
        parts = []
        for sheet in xls.sheet_names:
            df = xls.parse(sheet, dtype=str)
            if df.empty:
                continue
            lines = [
                " | ".join(
                    f"{col}: {val}" for col, val in row.items() if pd.notna(val) and str(val).strip()
                )
                for _, row in df.iterrows()
            ]
            lines = [ln for ln in lines if ln]
            if lines:
                parts.append(f"### 工作表: {sheet}\n" + "\n".join(lines))
        if not parts:
            raise BusinessError("Excel 内容为空")
        return "\n\n".join(parts)
    if file_type == "csv":
        raw = path.read_bytes()
        text = ""
        for enc in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="ignore")
        rows = [r for r in _csv.reader(io.StringIO(text)) if any(cell.strip() for cell in r)]
        if not rows:
            raise BusinessError("CSV 内容为空")
        header = rows[0]
        lines = []
        for r in rows[1:]:
            row_text = " | ".join(
                f"{h}: {v}" for h, v in zip(header, r) if str(v).strip()
            )
            if row_text:
                lines.append(row_text)
        return "\n".join(lines)
    raise BusinessError(f"暂不支持解析 {file_type} 文件")


def parse_document(db: Session, document_id: int) -> tuple[Document, str]:
    """解析需求文档，更新解析状态，返回 (文档, 解析文本)"""
    doc = db.get(Document, document_id)
    if not doc:
        raise NotFoundError("文档不存在")
    doc.parse_status = "parsing"
    db.commit()
    try:
        text = parse_document_file(doc.file_path, doc.file_type)
        doc.parse_status = "done"
        doc.parse_result = {"chars": len(text), "parsed_at": str(doc.updated_at)}
        db.commit()
        db.refresh(doc)
        return doc, text
    except Exception as e:
        doc.parse_status = "failed"
        doc.parse_result = {"error": str(e)}
        db.commit()
        raise BusinessError(f"文档解析失败: {e}")


def index_to_knowledge(
    db: Session, title: str, content: str, doc_type: str = "prd", user_id: int | None = None
) -> KnowledgeDoc:
    """将文档文本加入知识库并向量化"""
    kd = KnowledgeDoc(
        doc_type=doc_type,
        title=title,
        file_path="",
        content=content,
        created_by=user_id,
    )
    db.add(kd)
    db.commit()
    db.refresh(kd)
    try:
        chunk_count = rag_service.index_document(kd, content)
        kd.chunk_count = chunk_count
        kd.vector_status = "indexed"
    except Exception as e:
        kd.vector_status = "failed"
        kd.content = f"向量化失败: {e}"
    db.commit()
    db.refresh(kd)
    return kd


# ---------- FR-1.2 平台链接解析 ----------

def _html_to_text(html_text: str) -> str:
    """将 HTML 转为纯文本"""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|td|br)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _extract_title(html_text: str, url: str) -> str:
    """从 HTML 中提取页面标题"""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_text)
    if m:
        title = html.unescape(m.group(1)).strip()
        if title:
            return title[:200]
    m = re.search(r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html_text)
    if m:
        title = html.unescape(m.group(1)).strip()
        if title:
            return title[:200]
    parsed = urllib.parse.urlparse(url)
    name = parsed.path.strip("/").split("/")[-1]
    if name:
        return name[:200]
    return parsed.netloc or "链接文档"


def fetch_url_content(url: str, timeout: int = 30) -> tuple[str, str]:
    """抓取平台链接内容，返回 (标题, 纯文本)

    支持通用网页链接；飞书/语雀等平台的公开分享链接亦可抓取。
    需要登录的平台（TAPD/Confluence 等）会抛出 BusinessError 提示。
    """
    if not url.startswith(("http://", "https://")):
        raise BusinessError("链接必须以 http:// 或 https:// 开头")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise BusinessError(f"链接抓取失败: {e}")
    content_type = resp.headers.get("content-type", "")
    if "html" in content_type.lower():
        text = _html_to_text(resp.text)
        title = _extract_title(resp.text, url)
    else:
        text = resp.text
        title = url.split("/")[-1][:200] or url
    if not text.strip():
        raise BusinessError("未能从链接中提取到内容（平台可能要求登录或有限制）")
    return title.strip() or "链接文档", text.strip()
