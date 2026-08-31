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
from app.services.test_case_service import _gen_case_no

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
        case = TestCase(
            case_no=_gen_case_no(db, project_id),
            project_id=project_id,
            title=title,
            preconditions=str(row.get("前置条件") or row.get("preconditions") or "").strip() or None,
            steps=steps,
            expected_result=str(row.get("预期结果") or row.get("expected_result") or "").strip(),
            priority=str(row.get("优先级") or row.get("priority") or "P2").strip().upper(),
            test_type=str(row.get("测试类型") or row.get("test_type") or "功能测试").strip(),
            source="manual",
            created_by=user_id,
        )
        db.add(case)
        count += 1
    db.commit()
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


# 长文本列：固定更宽列宽并开启自动换行
_WIDE_COLUMNS = {"前置条件", "测试步骤", "预期结果"}
_WIDE_COLUMN_WIDTH = 45
_MAX_NARROW_COLUMN_WIDTH = 32
_MIN_COLUMN_WIDTH = 8
_LINE_HEIGHT = 15.5  # 单行行高估算值（磅）


def _display_width(text: str) -> int:
    """按 Excel 列宽单位估算文本宽度（中文等全角字符按 2 计）"""
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def _apply_sheet_style(ws, columns: list[str]) -> None:
    """为导出的工作表应用样式：表头加粗着色、全表边框、自动换行、列宽与行高"""
    # 表头样式
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4472C4")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    data_alignment = Alignment(vertical="top", wrap_text=True)

    for row in ws.iter_rows():
        for cell in row:
            cell.border = border
            if cell.row > 1:
                cell.alignment = data_alignment

    # 列宽：长文本列固定较宽，其余按内容自适应
    wide_indexes = []
    for idx, name in enumerate(columns, start=1):
        letter = get_column_letter(idx)
        if name in _WIDE_COLUMNS:
            wide_indexes.append(idx)
            ws.column_dimensions[letter].width = _WIDE_COLUMN_WIDTH
        else:
            max_len = _MIN_COLUMN_WIDTH
            for cell in ws[letter]:
                if cell.value is not None:
                    max_len = max(max_len, _display_width(str(cell.value)))
            ws.column_dimensions[letter].width = min(max_len + 3, _MAX_NARROW_COLUMN_WIDTH)

    # 冻结表头，滚动时始终可见
    ws.freeze_panes = "A2"

    # 行高估算：长文本列按换行后行数计算，保证内容完整显示
    for row in ws.iter_rows(min_row=2):
        max_lines = 1
        for idx in wide_indexes:
            cell = row[idx - 1]
            if cell.value is None:
                continue
            lines = 0
            for line in str(cell.value).splitlines():
                # 每行按列宽估算需占用的显示行数
                lines += max(1, (_display_width(line.strip()) + _WIDE_COLUMN_WIDTH - 1) // _WIDE_COLUMN_WIDTH)
            max_lines = max(max_lines, lines)
        ws.row_dimensions[row[0].row].height = max(20, max_lines * _LINE_HEIGHT + 4)


def export_cases(db: Session, case_ids: list[int]) -> bytes:
    """导出用例为 Excel（带自动换行、列宽、边框等样式），返回字节流"""
    cases = db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
    rows = []
    for c in cases:
        steps_text = "\n".join(
            f"{s.get('step_no', i + 1)}. {s.get('action', '')}" for i, s in enumerate(c.steps or [])
        )
        rows.append(
            {
                "用例编号": c.case_no,
                "用例标题": c.title,
                "模块": c.module or "",
                "前置条件": c.preconditions or "",
                "测试步骤": steps_text,
                "预期结果": c.expected_result,
                "优先级": c.priority,
                "测试类型": c.test_type,
                "用例来源": c.source,
                "用例状态": c.status,
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
    order = ["P0", "P1", "P2", "P3", "P4"]
    for c in cases:
        grouped.setdefault(c.priority, []).append(c)

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
