"""需求文档解析服务: 支持 PDF / Word / TXT / Markdown / Excel / CSV / 平台链接"""
import csv as _csv
import html
import io
import os
import re
import tempfile
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

# Markdown 图片提取：识别 ![](path) 与 <img src="..."> 语法
_MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HTML_IMG_RE = re.compile(r"<img\b[^>]*?src=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)
_MD_IMG_LIMIT = 20  # 单篇 md 最多解析的图片数，避免视觉 API 消耗过大
_RASTER_FMTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
_IMG_MAX_SIDE = 1280  # 发送视觉模型前压缩图片最长边(px)，控制推理耗时与 token 消耗


def _save_temp_image(data: bytes, fmt: str) -> str | None:
    """将图片字节写入临时文件，返回路径；不支持的格式返回 None

    保存前用 Pillow 压缩/缩放（最长边 _IMG_MAX_SIDE px）。Qwen3-VL 对高分辨率
    大图推理很慢（实测 76KB 登录截图 49.6s），压缩到 1280px 内可降到约 5-10s，
    同时减少 token 消耗；无法用 Pillow 处理时保留原始字节。
    """
    fmt = (fmt or "png").lower()
    suffix = "." + fmt if fmt in _RASTER_FMTS else ".png"
    if fmt not in _RASTER_FMTS:
        return None
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        max_side = max(img.size)
        if max_side > _IMG_MAX_SIDE:
            ratio = _IMG_MAX_SIDE / max_side
            img = img.resize(
                (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        data = buf.getvalue()
        suffix = ".jpg"
    except Exception:  # noqa: BLE001 - 非位图/损坏图片保留原始字节
        pass
    fd, path = tempfile.mkstemp(prefix="mdimg_", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def _resolve_md_image(ref: str, base_dir: Path) -> tuple[str | None, bool]:
    """将 md 图片引用解析为本地图片路径，返回 (路径, 是否为临时文件)

    支持三种形式: base64 内嵌图(data:image/...)、网络链接(http/https)、
    本地相对路径。无法解析或非位图格式时返回 (None, False)。
    """
    ref = ref.strip()
    if ref.startswith("data:"):
        m = re.match(r"data:image/([\w.+-]*);base64,", ref, re.IGNORECASE)
        if not m:
            return None, False
        try:
            import base64

            data = base64.b64decode(re.sub(r"\s+", "", ref.split(",", 1)[1]))
        except Exception:
            return None, False
        path = _save_temp_image(data, m.group(1))
        return (path, True) if path else (None, False)
    if ref.startswith(("http://", "https://")):
        try:
            resp = httpx.get(ref, timeout=12, follow_redirects=True)
            resp.raise_for_status()
        except Exception:
            return None, False
        suffix = Path(urllib.parse.urlparse(ref).path).suffix.lower().lstrip(".")
        path = _save_temp_image(resp.content, suffix)
        return (path, True) if path else (None, False)
    local = (base_dir / ref).resolve()
    if not local.is_file():
        return None, False
    return str(local), False


def _describe_one_md_image(ref: str, base_dir: Path, llm_service) -> str:
    """解析单个 md 图片引用并调用视觉模型描述；失败返回空串（保留原引用）"""
    image_path, is_temp = _resolve_md_image(ref, base_dir)
    if not image_path:
        return ""
    try:
        # 单图预算 75s（硅基流动 Qwen3-VL-32B 实测响应 30-60s，波动较大），
        # 超时放弃该图避免拖垮整批任务
        return llm_service.describe_image(image_path, timeout=75) or ""
    except Exception:
        return ""
    finally:
        if is_temp and image_path:
            try:
                os.remove(image_path)
            except OSError:
                pass


def _extract_md_images(text: str, base_dir: Path) -> str:
    """提取 Markdown 中的图片引用，用视觉模型描述文本替换

    - 未启用视觉模型或图片无法解析时，保留原始引用不丢失
    - 同一张图多处引用只调用一次视觉模型（按引用缓存）
    - 单篇最多解析 _MD_IMG_LIMIT 张图，避免 API 消耗过大
    """
    if not text:
        return text
    from app.config import settings
    from app.services.llm_service import llm_service

    if not settings.VISION_ENABLED or not llm_service.vision_health():
        return text

    # 1. 收集全部图片引用（去重，最多 _MD_IMG_LIMIT 张）
    refs: list[str] = []
    seen: set[str] = set()

    def _collect_md(m: re.Match) -> str:
        ref = (m.group(2) or "").strip().split(" ", 1)[0].strip()
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
        return m.group(0)

    def _collect_html(m: re.Match) -> str:
        ref = m.group(1).strip()
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
        return m.group(0)

    _MD_IMG_RE.sub(_collect_md, text)
    _HTML_IMG_RE.sub(_collect_html, text)
    refs = refs[:_MD_IMG_LIMIT]

    # 2. 并行描述图片：单图超时 75s，整体最多等 85s。超时未返回的线程不等待，
    #    直接放弃该图（保留原引用），避免卡住的网络请求（DNS/连接/TLS 挂起等
    #    httpx timeout 无法中断的情况）拖垮整篇文档解析。
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cache: dict[str, str] = {}
    if refs:
        ex = ThreadPoolExecutor(max_workers=min(4, len(refs)))
        try:
            futures = {ex.submit(_describe_one_md_image, ref, base_dir, llm_service): ref for ref in refs}
            try:
                for fut in as_completed(futures, timeout=85):
                    ref = futures[fut]
                    try:
                        cache[ref] = fut.result()
                    except Exception:  # noqa: BLE001
                        cache[ref] = ""
            except TimeoutError:
                pass
            # 超时/未返回的引用兜底为空，保留原图引用不丢失
            for ref in refs:
                cache.setdefault(ref, "")
        finally:
            # 关键：wait=False + cancel_futures，不等待卡住的 worker 线程
            ex.shutdown(wait=False, cancel_futures=True)

    # 3. 用描述文本替换图片引用
    count = {"n": 0}

    def _repl(m: re.Match, ref: str, alt: str) -> str:
        if count["n"] >= _MD_IMG_LIMIT:
            return m.group(0)
        desc = cache.get(ref, "")
        if not desc:
            return m.group(0)
        count["n"] += 1
        label = f"图片{('：' + alt) if alt else ''}"
        return f"\n\n[{label}]\n{desc.strip()}\n"

    def _md_repl(m: re.Match) -> str:
        ref = (m.group(2) or "").strip().split(" ", 1)[0].strip()
        return _repl(m, ref, (m.group(1) or "").strip())

    def _html_repl(m: re.Match) -> str:
        alt = ""
        am = re.search(r"alt=[\"']([^\"']*)[\"']", m.group(0), re.IGNORECASE)
        if am:
            alt = am.group(1).strip()
        return _repl(m, m.group(1).strip(), alt)

    text = _MD_IMG_RE.sub(_md_repl, text)
    return _HTML_IMG_RE.sub(_html_repl, text)


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
        text = path.read_text(encoding="utf-8", errors="ignore")
        return _extract_md_images(text, path.parent)
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
