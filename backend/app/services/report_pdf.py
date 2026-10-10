"""需求体检报告 PDF 生成（reportlab）

纯 Python 生成，无外部系统依赖；中文用系统微软雅黑字体。
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_FONT_REGISTERED = False
_FONT = "Helvetica"  # 兜底


def _ensure_font() -> None:
    global _FONT_REGISTERED, _FONT
    if _FONT_REGISTERED:
        return
    # Windows 优先微软雅黑/黑体；Linux 容器（fonts-noto-cjk）用 Noto Sans CJK
    for path in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    ):
        try:
            pdfmetrics.registerFont(TTFont("MSYH", path))
            _FONT = "MSYH"
            break
        except Exception:  # noqa: BLE001
            continue
    _FONT_REGISTERED = True


def generate_report_pdf(report: dict) -> bytes:
    """根据体检报告 dict 生成 PDF 字节流"""
    _ensure_font()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    navy = colors.HexColor("#1E2761")
    accent = colors.HexColor("#409EFF")
    muted = colors.HexColor("#64748B")
    red = colors.HexColor("#F56C6C")
    h1 = ParagraphStyle("h1", fontName=_FONT, fontSize=22, textColor=navy, spaceAfter=6)
    h2 = ParagraphStyle("h2", fontName=_FONT, fontSize=14, textColor=navy, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("body", fontName=_FONT, fontSize=11, leading=18, textColor=colors.HexColor("#1E293B"))
    issue_style = ParagraphStyle("issue", fontName=_FONT, fontSize=10.5, leading=16, leftIndent=10)

    def esc(s) -> str:
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    elems: list = []
    elems.append(Paragraph("需求质量体检报告", h1))
    score = int(report.get("score") or 0)
    score_color = red if score < 60 else "#E6A23C" if score < 85 else "#67C23A"
    elems.append(Paragraph(
        f'<font name="{_FONT}" size="28" color="{score_color}"><b>{score}</b></font>'
        f'<font name="{_FONT}" size="14" color="#64748B"> / 100</font>',
        body,
    ))
    elems.append(Spacer(1, 4 * mm))
    elems.append(Paragraph(f"<b>文件：</b>{esc(report.get('filename'))}", body))
    ca = report.get("created_at")
    elems.append(Paragraph(f"<b>体检时间：</b>{esc(ca.strftime('%Y-%m-%d %H:%M') if ca else '-')}", body))
    elems.append(Spacer(1, 6 * mm))

    elems.append(Paragraph("总体评价", h2))
    elems.append(Paragraph(esc(report.get("summary")) or "-", body))
    elems.append(Spacer(1, 4 * mm))

    m = report.get("metrics") or {}
    elems.append(Paragraph("统计指标", h2))
    elems.append(Paragraph(
        f"需求 {m.get('requirement_count', 0)} 条  |  测试点 {m.get('test_point_count', 0)} 个  "
        f"|  隐式场景 {m.get('implicit_count', 0)} 个",
        body,
    ))
    elems.append(Spacer(1, 4 * mm))

    issues = report.get("issues") or []
    elems.append(Paragraph(f"问题清单（{len(issues)} 项）", h2))
    for i, it in enumerate(issues, 1):
        sev = it.get("severity", "")
        elems.append(Paragraph(
            f'<b>{i}. [{esc(it.get("type"))}] [{esc(sev)}]</b>  {esc(it.get("description"))}',
            issue_style,
        ))
        if it.get("requirement"):
            elems.append(Paragraph(f"关联需求：{esc(it.get('requirement'))}", ParagraphStyle("r", parent=issue_style, textColor=muted, fontSize=9.5)))
        if it.get("suggestion"):
            elems.append(Paragraph(f"建议：{esc(it.get('suggestion'))}", ParagraphStyle("r", parent=issue_style, textColor=accent, fontSize=9.5)))
        elems.append(Spacer(1, 2 * mm))

    elems.append(Spacer(1, 4 * mm))
    hl = report.get("highlights") or []
    elems.append(Paragraph("亮点", h2))
    for h in hl:
        elems.append(Paragraph(f"• {esc(h)}", body))

    doc.build(elems)
    return buf.getvalue()
