"""测试用例导入导出服务（Excel / Markdown / JSON / XMind）"""
import io
import json
import uuid
import zipfile
from datetime import datetime

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.models.test_case import TestCase
from app.services.test_case_service import _insert_case

# 用例导入字段映射：Excel列名 -> 模型字段
FIELD_MAP = {
    "用例编号": "case_no",
    "用例标题": "title",
    "模块": "module",
    "前置条件": "preconditions",
    "测试步骤": "steps",
    "预期结果": "expected_result",
    "优先级": "priority",
    "测试类型": "test_type",
}


def import_cases(db: Session, file, project_id: int, user_id: int) -> int:
    """从 Excel 导入用例"""
    try:
        df = pd.read_excel(io.BytesIO(file.file.read()))
    except Exception as e:
        raise BusinessError(f"Excel 解析失败: {e}")

    count = 0
    for _, row in df.iterrows():
        title = str(row.get("用例标题") or row.get("title") or "").strip()
        if not title:
            continue
        steps_text = str(row.get("测试步骤") or row.get("steps") or "")
        steps = _parse_steps(steps_text)
        _insert_case(
            db,
            project_id,
            title=title,
            preconditions=str(row.get("前置条件") or row.get("preconditions") or "").strip() or None,
            steps=steps,
            expected_result=str(row.get("预期结果") or row.get("expected_result") or "").strip(),
            priority=_normalize_priority(row.get("优先级") or row.get("priority")),
            test_type=str(row.get("测试类型") or row.get("test_type") or "功能测试").strip(),
            source="manual",
            created_by=user_id,
        )
        count += 1
    return count


def _parse_steps(text: str) -> list[dict]:
    """将步骤文本解析为步骤数组（支持 1. xxx 或 第1步: xxx 格式）"""
    if not text:
        return []
    steps = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines, start=1):
        # 去掉序号前缀
        content = line
        import re

        content = re.sub(r"^\d+[.、)]\s*", "", content)
        content = re.sub(r"^第\d+步[:：]\s*", "", content)
        steps.append({"step_no": i, "action": content, "expected": ""})
    return steps


# ============ 标准测试用例表格样式 ============
# 列定义: (列名, 固定列宽) —— 列宽按内容与可读性预设
_EXCEL_COLUMNS = [
    ("序号", 8),
    ("用例编号", 16),
    ("测试项", 34),
    ("测试模块", 20),
    ("前置条件", 42),
    ("测试步骤", 60),
    ("预期结果", 42),
    ("优先级", 12),
    ("测试类型", 14),
    ("用例来源", 12),
    ("用例状态", 12),
    ("核查备注", 44),
]
_HEADER_FILL = "4472C4"
_HEADER_ROW_HEIGHT = 24
_LINE_HEIGHT = 15.5  # 单行行高估算值（磅）
_MIN_ROW_HEIGHT = 22

# 用例等级顺序：规范四级 L1~L4 在前，历史 P0~P4 在后（导出/分组排序共用）
_PRIORITY_ORDER = ["L1", "L2", "L3", "L4", "P0", "P1", "P2", "P3", "P4"]

# 等级配色: 等级 -> (字体色, 填充色)
_PRIORITY_COLORS = {
    # 《测试用例等级定义规范》四级
    "L1": ("9C0006", "FFC7CE"),
    "L2": ("974706", "FCE4D6"),
    "L3": ("7F6000", "FFF2CC"),
    "L4": ("404040", "EDEDED"),
    # 历史 P0~P4（存量数据继续着色）
    "P0": ("9C0006", "FFC7CE"),
    "P1": ("974706", "FCE4D6"),
    "P2": ("7F6000", "FFF2CC"),
    "P3": ("375623", "E2EFDA"),
    "P4": ("404040", "EDEDED"),
}


def _normalize_priority(value) -> str:
    """等级归一化：规范四级 L1~L4 优先，历史 P0~P4 兼容，未知/空值兜底 L2"""
    prio = str(value or "").strip().upper()
    return prio if prio in _PRIORITY_ORDER else "L2"


def _display_width(text: str) -> int:
    """按 Excel 列宽单位估算文本宽度（中文等全角字符按 2 计）"""
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def _calc_display_lines(text, width: int) -> int:
    """按指定列宽估算文本自动换行后的显示行数"""
    text = str(text or "")
    if not text:
        return 1
    usable = max(1, width - 2)
    lines = 0
    for line in text.splitlines():
        lines += max(1, (_display_width(line) + usable - 1) // usable)
    return max(1, lines)


def _apply_sheet_style(ws, columns: list[str]) -> None:
    """标准测试用例表格样式：表头加粗着色、全表边框、自动换行、固定列宽、按内容自适应行高、优先级着色、冻结表头"""
    # 1) 表头：蓝底白字加粗居中，固定行高
    ws.row_dimensions[1].height = _HEADER_ROW_HEIGHT
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = PatternFill("solid", fgColor=_HEADER_FILL)
        cell.alignment = header_alignment

    # 2) 数据区：细边框 + 自动换行垂直居中
    thin = Side(style="thin", color="B4C6E7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    data_alignment = Alignment(vertical="center", wrap_text=True)
    col_index = {name: i for i, name in enumerate(columns, start=1)}
    prio_col = col_index.get("优先级")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = data_alignment
            # 优先级列按 P0~P4 着色
            if prio_col and cell.column == prio_col:
                prio = str(cell.value or "").strip().upper()
                if prio in _PRIORITY_COLORS:
                    font_color, fill_color = _PRIORITY_COLORS[prio]
                    cell.font = Font(bold=True, color=font_color)
                    cell.fill = PatternFill("solid", fgColor=fill_color)

    # 3) 列宽：按标准列定义固定
    width_map = {name: width for name, width in _EXCEL_COLUMNS}
    for idx, name in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width_map.get(name, 16)

    # 4) 行高：遍历所有列取最大换行行数，保证任何列内容都不被截断
    for row in ws.iter_rows(min_row=2):
        max_lines = 1
        for cell in row:
            if cell.value is None:
                continue
            width = width_map.get(columns[cell.column - 1], 16)
            max_lines = max(max_lines, _calc_display_lines(cell.value, width))
        ws.row_dimensions[row[0].row].height = max(_MIN_ROW_HEIGHT, max_lines * _LINE_HEIGHT + 4)

    # 5) 冻结表头（滚动可见）+ 自动筛选
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def export_cases(db: Session, case_ids: list[int]) -> bytes:
    """导出用例为标准测试用例表格 Excel（自动换行、自适应行高、固定列宽、优先级着色、冻结表头）"""
    cases = db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
    rows = []
    for i, c in enumerate(cases, start=1):
        # 测试步骤：1. xxx（预期：yyy）每条占一行
        step_lines = []
        for s in c.steps or []:
            no = s.get("step_no", len(step_lines) + 1)
            action = str(s.get("action", "")).strip()
            exp = str(s.get("expected") or "").strip()
            step_lines.append(f"{no}. {action}" + (f"（预期：{exp}）" if exp else ""))
        rows.append(
            {
                "序号": i,
                "用例编号": c.case_no,
                "测试项": c.title,
                "测试模块": c.module or "",
                "前置条件": c.preconditions or "",
                "测试步骤": "\n".join(step_lines),
                "预期结果": c.expected_result,
                "优先级": c.priority,
                "测试类型": c.test_type,
                "用例来源": c.source,
                "用例状态": c.status,
                "核查备注": c.ai_remark or "",
            }
        )
    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="测试用例")
        _apply_sheet_style(writer.sheets["测试用例"], columns=list(df.columns))
    return buffer.getvalue()


def _collect_cases(db: Session, case_ids: list[int]):
    """按 id 顺序取用例"""
    cases = {c.id: c for c in db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()}
    return [cases[i] for i in case_ids if i in cases]


def export_cases_markdown(db: Session, case_ids: list[int]) -> str:
    """导出用例为 Markdown，返回文本"""
    cases = _collect_cases(db, case_ids)
    lines = ["# 测试用例", ""]
    for idx, c in enumerate(cases, start=1):
        lines.append(f"## {idx}. {c.case_no} · {c.title}")
        lines.append("")
        lines.append(f"- 模块：{c.module or '（未分类）'}　- 优先级：{c.priority}　- 测试类型：{c.test_type}　- 来源：{c.source}")
        lines.append("")
        lines.append("**前置条件**")
        lines.append("")
        lines.append(c.preconditions or "（无）")
        lines.append("")
        lines.append("**测试步骤**")
        lines.append("")
        for s in c.steps or []:
            step_no = s.get("step_no", "")
            action = s.get("action", "")
            expected = s.get("expected") or ""
            lines.append(f"{step_no}. {action}" + (f"　_（预期：{expected}）_" if expected else ""))
        lines.append("")
        lines.append(f"**预期结果**：{c.expected_result}")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def export_cases_json(db: Session, case_ids: list[int]) -> str:
    """导出用例为 JSON，返回格式化 JSON 字符串"""
    cases = _collect_cases(db, case_ids)
    data = [
        {
            "id": c.id,
            "case_no": c.case_no,
            "title": c.title,
            "module": c.module,
            "preconditions": c.preconditions,
            "steps": c.steps or [],
            "expected_result": c.expected_result,
            "priority": c.priority,
            "test_type": c.test_type,
            "source": c.source,
            "status": c.status,
        }
        for c in cases
    ]
    return json.dumps({"total": len(data), "cases": data}, ensure_ascii=False, indent=2)


def export_cases_xmind(db: Session, case_ids: list[int]) -> bytes:
    """导出用例为 XMind 思维导图（XMind 8 兼容格式），返回字节流

    结构：中心主题「测试用例」→ 按优先级分组 → 每条用例 → 前置/步骤/预期
    """
    cases = _collect_cases(db, case_ids)
    grouped: dict[str, list] = {}
    for c in cases:
        grouped.setdefault(_normalize_priority(c.priority), []).append(c)
    # 只输出实际存在的等级，避免新增等级（L1~L4）被固定枚举丢弃
    order = [p for p in _PRIORITY_ORDER if p in grouped]

    def _topic(title: str, children: list | None = None) -> dict:
        topic = {"id": str(uuid.uuid4()).replace("-", ""), "title": title}
        if children:
            topic["children"] = {"attached": children}
        return topic

    def _case_topic(c) -> dict:
        kids = [
            _topic(f"模块：{c.module or '未分类'}"),
            _topic(f"前置条件：{c.preconditions or '无'}"),
            _topic(f"优先级：{c.priority}｜类型：{c.test_type}"),
        ]
        step_children = []
        for s in c.steps or []:
            step_children.append(
                _topic(f"步骤{s.get('step_no', '')}：{s.get('action', '')}")
            )
        if step_children:
            kids.append(_topic("测试步骤", step_children))
        kids.append(_topic(f"预期结果：{c.expected_result}"))
        return _topic(f"{c.case_no} {c.title}", kids)

    prio_topics = []
    for p in order:
        if p in grouped:
            prio_topics.append(_topic(f"{p}（{len(grouped[p])} 条）", [_case_topic(c) for c in grouped[p]]))
    root = _topic("测试用例", prio_topics)

    content = [
        {
            "id": str(uuid.uuid4()).replace("-", ""),
            "class": "sheet",
            "title": "测试用例",
            "rootTopic": root,
        }
    ]
    metadata = {
        "creator": {"name": "XMind", "version": "8.0"},
        "timestamp": int(datetime.now().timestamp() * 1000),
    }
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}}}

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return buffer.getvalue()
