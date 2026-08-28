"""Axure .rp 原型文件解析器

支持 Axure RP 8 及以下的自定义二进制格式（魔数 AC EF 09 00）：
- 文件主体由多个 gzip 压缩块组成，每个块序列化一个对象
  （Axure:Page / Axure:Master / 生成配置等）
- 对象内部为 [len:4][utf8] 字符串流（属性名/属性值/组件文本）
- 页面名称通过页面内超链接目标（xxx.html）反推，其余以"页面N"兜底
"""
import re
import zlib
from typing import Optional

# Axure 8 二进制魔数
_AXURE8_MAGIC = b"\xac\xef\x09\x00"
# zip 魔数（Axure RP 9/10 为 zip 容器）
_ZIP_MAGIC = b"PK\x03\x04"

# 组件库/属性名噪音（精确匹配时过滤）
_NOISE_WORDS = {
    "默认", "图片", "图像", "图标", "形状", "文本", "连接", "连接符",
    "标签", "按钮", "输入框", "文本框", "多行文本框", "下拉框", "复选框",
    "单选按钮", "开关", "滑块", "进度条", "表格", "树", "菜单", "面包屑",
    "分页", "弹窗", "提示", "加载", "占位符", "轮播", "选项卡", "步骤条",
    "时间轴", "栅格", "布局", "容器", "组件", "素材", "表单", "导航",
    "页头", "页脚", "侧边栏", "工具栏", "状态栏", "元部件", "标题 1",
    "标题 2", "标题 3", "标题 4", "标题 5", "标题 6", "元件库web端",
    "常规", "主要", "次要", "成功", "警告", "危险", "信息",
}

_CJK_FONTS = ("思源黑体", "微软雅黑", "苹方", "阿里巴巴", "鸿蒙", "HarmonyOS", "Source Han", "Alibaba")
_EN_FONTS = (
    "PingFang", "Helvetica", "Arial", "Roboto", "Segoe", "Noto", "DIN",
    "Montserrat", "Poppins", "Inter", "Lato", "Open Sans", "SF Pro", "System",
    "Myriad", "Calibri", "Times New Roman", "Courier", "Verdana", "Tahoma",
    "Georgia", "Trebuchet", "Futura",
)
_FONT_STYLES = {
    "light", "regular", "bold", "medium", "semibold", "thin", "black",
    "italic", "oblique", "extralight", "ultralight", "normal", "heavy",
    "narrow", "cursiva", "negreta", "condensed", "常规", "粗体", "细体",
    "中等", "特细", "特粗", "斜体",
}

# 长度字段候选：[低2字节][\x00\x00]，后跟可打印文本
_CAND_RE = re.compile(rb"[\x01-\xff][\x00-\xff]\x00\x00(?=[\x20-\x7e\x80-\xff]{2})")


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in s)


def _is_font_fragment(p: str) -> bool:
    """判断片段是否为『字体名[样式]』或纯样式名"""
    if not p or len(p) < 2:
        return False
    low = p.lower()
    if _has_cjk(p):
        return any(f in p for f in _CJK_FONTS)
    for f in _EN_FONTS:
        if f.lower() in low:
            return True
    words = low.split()
    return bool(words) and all(wd in _FONT_STYLES for wd in words)


def _is_font_noise(s: str) -> bool:
    """字体序列（'Arial Normal', 'Arial'）为噪音"""
    if not s or len(s) < 2:
        return True
    if "'" in s or "，" in s or "," in s:
        parts = [p.strip() for p in re.split(r"['\",，]+", s) if p.strip()]
        if parts and all(_is_font_fragment(p) for p in parts):
            return True
    return _is_font_fragment(s)


def _extract_strings(buf: bytes) -> list[str]:
    """在对象字节流中提取 [len:4][utf8] 字符串（去重保序）"""
    result: list[str] = []
    seen: set[str] = set()
    n = len(buf)
    for m in _CAND_RE.finditer(buf):
        i = m.start()
        ln = buf[i] | (buf[i + 1] << 8)
        if 1 <= ln <= 50000 and i + 4 + ln <= n:
            s = buf[i + 4:i + 4 + ln]
            if b"\x00" not in s and len(s) >= 2:
                try:
                    txt = s.decode("utf-8")
                    if txt not in seen:
                        seen.add(txt)
                        result.append(txt)
                except UnicodeDecodeError:
                    pass
    return result


def _block_type(raw: bytes) -> Optional[str]:
    """解析 gzip 块内的对象类型名（offset 32 处 [len:4][type]）"""
    if len(raw) < 36:
        return None
    ln = (raw[35] << 24) | (raw[34] << 16) | (raw[33] << 8) | raw[32]
    if 0 < ln < 200 and 36 + ln <= len(raw):
        try:
            t = raw[36:36 + ln].decode("utf-8")
            if t.startswith("Axure:"):
                return t
        except Exception:
            pass
    return None


def _is_noise(s: str) -> bool:
    """组件库噪音 / 字体噪音 / 路径链接等无需求价值文本"""
    if _is_font_noise(s):
        return True
    s2 = s.strip()
    if len(s2) < 2:
        return True
    if s2 in _NOISE_WORDS:
        return True
    if s2.endswith(".html") or s2.startswith(("http://", "https://", "file:")):
        return True
    # 磁盘路径（含反斜杠）或纯数字串
    if "\\" in s2 or ":" in s2:
        return True
    if re.fullmatch(r"[\d\s.,%+-]+", s2):
        return True
    return False


def extract_rp_text(file_path: str) -> str:
    """解析 .rp 文件为 Markdown 文本

    返回页面结构（页面名 + 组件文本）。解析不到任何文本时抛出 ValueError。
    """
    with open(file_path, "rb") as f:
        data = f.read()

    if data[:4] == _ZIP_MAGIC:
        return (
            "# Axure 原型解析结果\n\n"
            "该 .rp 文件为 Axure RP 9/10 的 zip 容器格式，当前版本暂未支持该格式的深度解析。\n"
            "建议在 Axure 中导出为图片（或 HTML 截图）后上传，系统将调用视觉模型识别原型内容。"
        )
    if data[:4] != _AXURE8_MAGIC:
        raise ValueError("无法识别的 .rp 文件格式（非 Axure 工程文件）")

    # 定位 gzip 块
    gzs = [m.start() for m in re.finditer(b"\x1f\x8b\x08", data)]
    pages: list[tuple[Optional[str], list[str]]] = []
    masters: list[list[str]] = []

    for gi, start in enumerate(gzs):
        end = gzs[gi + 1] if gi + 1 < len(gzs) else len(data)
        try:
            dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
            raw = dec.decompress(data[start:end])
        except Exception:
            continue
        btype = _block_type(raw)
        if btype == "Axure:Page":
            kind = "page"
        elif btype == "Axure:Master":
            kind = "master"
        elif btype is None and b"Axure:Page" in raw:
            kind = "page"
        elif btype is None and b"Axure:Master" in raw:
            kind = "master"
        else:
            continue

        strings = _extract_strings(raw)
        pname: Optional[str] = None
        good: list[str] = []
        for s in strings:
            # 页面名：块内超链接目标 xxx.html
            m = re.fullmatch(r"([\w\u4e00-\u9fff（）()【】\[\]\- ]+)\.html", s.strip())
            if m and pname is None:
                pname = m.group(1).strip()
                continue
            if _is_noise(s):
                continue
            s2 = s.strip()
            if _has_cjk(s2):
                good.append(s2)

        if kind == "page":
            pages.append((pname, good))
        else:
            masters.append(good)

    if not pages:
        raise ValueError("未能从 .rp 文件中解析出任何页面")

    lines: list[str] = [
        "# Axure 原型解析结果",
        "",
        f"> 文件解析完成：共 {len(pages)} 个页面、{len(masters)} 个母版。",
        "",
    ]
    for idx, (pname, texts) in enumerate(pages):
        uniq = list(dict.fromkeys(texts))
        title = pname or f"页面{idx + 1}"
        lines.append(f"## {idx + 1}. {title}")
        if not uniq:
            lines.append("- （该页面以图片为主，无可提取的文本）")
        for t in uniq[:100]:
            lines.append(f"- {t}")
        lines.append("")

    if masters:
        lines.append("## 母版 (Master)")
        for idx, ms in enumerate(masters):
            uniq = list(dict.fromkeys(ms))
            lines.append(f"### 母版{idx + 1}")
            for t in uniq[:60]:
                lines.append(f"- {t}")
            lines.append("")

    return "\n".join(lines).strip()
