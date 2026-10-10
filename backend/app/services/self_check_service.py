"""AI 自查服务：将用例与其需求原文依据比对，把【存疑/不符】备注写入 ai_remark

- 只标注，不改动用例内容
- 支持按生成任务(task_id)或指定用例(case_ids)批量自查
- 历史用例未落库 req_ref 时，回退用测试点描述作为近似依据；两者都没有则跳过
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.test_case_self_checker import TestCaseSelfCheckerAgent
from app.core.exceptions import BusinessError
from app.models.test_case import TestCase
from app.models.test_point import TestPoint

logger = logging.getLogger(__name__)

_BATCH_SIZE = 6


def _format_steps(steps) -> str:
    lines = []
    for s in steps or []:
        no = s.get("step_no", len(lines) + 1)
        action = str(s.get("action") or "").strip()
        exp = str(s.get("expected") or "").strip()
        lines.append(f"{no}. {action}" + (f"（预期：{exp}）" if exp else ""))
    return "\n".join(lines)


def _build_block(case: TestCase, ctx: str | None, ctx_note: str) -> str:
    return (
        f"【case_id={case.id}】\n"
        f"用例标题: {case.title}\n"
        f"模块: {case.module or ''}\n"
        f"用例等级: {case.priority}｜测试类型: {case.test_type}\n"
        f"前置条件: {case.preconditions or ''}\n"
        f"测试步骤:\n{_format_steps(case.steps) or '（无步骤）'}\n"
        f"预期结果: {case.expected_result or ''}\n"
        f"——{ctx_note}——\n{ctx or '（无）'}"
    )


def _remark_from_issues(issues: list) -> str:
    if not issues:
        return ""
    lines = []
    seen = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        detail = str(issue.get("detail") or "").strip()
        if not detail:
            continue
        if detail in seen:
            continue
        seen.add(detail)
        type_label = str(issue.get("type") or "").strip()
        if type_label == "不符":
            marker = "【不符】"
        elif type_label == "存疑":
            marker = "【存疑】"
        else:
            marker = "【提示】"
        lines.append(f"{marker}{detail}")
    return "\n".join(lines)


def ai_self_check(
    db: Session,
    *,
    task_id: int | None = None,
    case_ids: list[int] | None = None,
) -> dict:
    """执行 AI 自查并落库，返回统计结果

    :return: {"checked": 实际执行自查条数, "flagged": 发现问题的条数, "skipped": 缺少依据跳过的条数, "failed_batches": 失败的批次}
    """
    if not task_id and not case_ids:
        raise BusinessError("请指定生成任务或选择待自查的用例")

    q = db.query(TestCase)
    if task_id:
        q = q.filter(TestCase.task_id == task_id)
    else:
        q = q.filter(TestCase.id.in_(case_ids))
    cases = q.order_by(TestCase.id.asc()).all()
    if not cases:
        raise BusinessError("未找到可自查的用例")

    # 测试点描述作近似依据（历史用例无 req_ref 时兜底）
    point_ids = {c.test_point_id for c in cases if c.test_point_id}
    tp_map = {}
    if point_ids:
        for p in db.query(TestPoint).filter(TestPoint.id.in_(point_ids)).all():
            tp_map[p.id] = p

    # 组装可自查的批次
    work: list[dict] = []
    skipped = 0
    for c in cases:
        if c.req_ref:
            ctx, note = c.req_ref, "需求原文依据（生成时记录）"
        elif c.test_point_id and c.test_point_id in tp_map and (tp_map[c.test_point_id].description or "").strip():
            ctx, note = tp_map[c.test_point_id].description, "测试点描述（近似依据，非完整需求原文）"
        else:
            skipped += 1
            continue
        work.append({"case": c, "block": _build_block(c, ctx, note)})

    if not work:
        raise BusinessError(
            f"{len(cases)} 条用例均缺少需求原文依据，无法自查。"
            "新生成的用例会记录原文依据，可重新生成后再试。"
        )

    agent = TestCaseSelfCheckerAgent()
    checked = 0
    flagged = 0
    failed_batches = 0
    now = datetime.now()
    first_error: Exception | None = None

    for start in range(0, len(work), _BATCH_SIZE):
        chunk = work[start : start + _BATCH_SIZE]
        try:
            result = agent.run([item["block"] for item in chunk]) or {}
            case_id_to_issues: dict[int, list] = {}
            for item in result.get("results") or []:
                if not isinstance(item, dict):
                    continue
                try:
                    cid = int(item.get("case_id"))
                except (TypeError, ValueError):
                    continue
                case_id_to_issues[cid] = item.get("issues") or []

            for item in chunk:
                c = item["case"]
                issues = case_id_to_issues.get(c.id, [])
                remark = _remark_from_issues(issues)
                c.ai_remark = remark or None
                c.ai_checked_at = now
                checked += 1
                if remark:
                    flagged += 1
            db.commit()
        except Exception as e:  # noqa: BLE001 - 单批失败不中断整批自查
            db.rollback()
            failed_batches += 1
            logger.warning("AI 自查批次失败: %s", e)
            if first_error is None:
                first_error = e

    if checked == 0 and failed_batches > 0:
        raise BusinessError(f"AI 自查全部失败，请稍后重试。{first_error}")

    return {
        "checked": checked,
        "flagged": flagged,
        "skipped": skipped,
        "failed_batches": failed_batches,
    }
