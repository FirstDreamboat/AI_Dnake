"""测试用例管理服务"""
import json

from sqlalchemy import case as sql_case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError, NotFoundError
from app.models.generation_task import GenerationTask
from app.models.project import Project
from app.models.test_case import TestCase, TestCaseVersion
from app.models.test_point import TestPoint
from app.schemas.test_case import TestCaseCreate, TestCaseUpdate

# 产品线代码映射（PRD §7.1 用例编号规则: {产品线代码}-{模块代码}-{序号}）
PRODUCT_LINE_CODES = {
    "intercom": "LBYJ",  # 楼宇对讲
    "smart_home": "ZNJJ",  # 智能家居
    "hospital": "ZHYF",  # 智慧医院
}


def _case_no_prefix(db: Session, project_id: int) -> str:
    """用例编号前缀: {产品线代码}-{模块代码}-（PRD §7.1）"""
    project = db.get(Project, project_id)
    line_code = PRODUCT_LINE_CODES.get(project.product_line if project else None, "GEN")
    # 模块代码：当前未建模模块实体，默认 MOD；后续引入模块管理后可细化
    return f"{line_code}-MOD-"


def _gen_case_no(db: Session, project_id: int) -> str:
    """生成用例编号: {产品线代码}-{模块代码}-{序号}（PRD §7.1）

    序号取"全库同前缀已有最大序号 + 1"而非"用例总数 + 1"：
    - 用最大值：删除用例后编号不回退，避免重复；
    - 全库而非项目内：case_no 上是全局唯一索引，同产品线的不同项目若各自
      从 001 起编号会互相撞键（如 ZNJJ-MOD-001 已被其他智能家居项目占用）。
    - 序号固定 4 位零填充：超过 999 后位数混排（003 与 1000 长度不一），
      字符串排序会错乱，统一 4 位可保证排序与视觉一致（上限 9999 条/前缀）。
    """
    prefix = _case_no_prefix(db, project_id)
    rows = db.scalars(select(TestCase.case_no).where(TestCase.case_no.like(f"{prefix}%"))).all()
    max_seq = 0
    for no in rows:
        try:
            max_seq = max(max_seq, int(no.rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:04d}"


# 编号冲突重试次数：取号与插入之间存在并发窗口（两任务同时取到同一序号）
_CASE_NO_RETRIES = 3


def _insert_case(db: Session, project_id: int, **fields) -> TestCase:
    """新建用例并按编号落库；撞全局唯一键时重新取号重试"""
    for attempt in range(_CASE_NO_RETRIES):
        case = TestCase(case_no=_gen_case_no(db, project_id), project_id=project_id, **fields)
        db.add(case)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if attempt == _CASE_NO_RETRIES - 1:
                raise BusinessError("用例编号生成冲突，请重试") from None
            continue
        db.refresh(case)
        return case
    raise BusinessError("用例编号生成冲突，请重试")


def list_cases(
    db: Session, page: int, page_size: int, project_id: int | None = None,
    priority: str | None = None, status: str | None = None, source: str | None = None,
    keyword: str | None = None, module: str | None = None, task_id: int | None = None,
) -> tuple[list[TestCase], int]:
    stmt = select(TestCase)
    if project_id:
        stmt = stmt.where(TestCase.project_id == project_id)
    if priority:
        stmt = stmt.where(TestCase.priority == priority)
    if status:
        stmt = stmt.where(TestCase.status == status)
    if source:
        stmt = stmt.where(TestCase.source == source)
    if module:
        stmt = stmt.where(TestCase.module == module)
    if task_id:
        stmt = stmt.where(TestCase.task_id == task_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(TestCase.title.like(like), TestCase.case_no.like(like)))
    total = len(db.scalars(stmt).all())
    cases = db.scalars(stmt.order_by(TestCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return list(cases), total


def list_case_ids(
    db: Session, project_id: int | None = None,
    priority: str | None = None, status: str | None = None,
    source: str | None = None, keyword: str | None = None, module: str | None = None,
    task_id: int | None = None,
) -> list[tuple[int, str]]:
    """返回当前查询条件下所有用例的 (id, source)，用于前端跨页全选"""
    stmt = select(TestCase.id, TestCase.source)
    if project_id:
        stmt = stmt.where(TestCase.project_id == project_id)
    if priority:
        stmt = stmt.where(TestCase.priority == priority)
    if status:
        stmt = stmt.where(TestCase.status == status)
    if source:
        stmt = stmt.where(TestCase.source == source)
    if module:
        stmt = stmt.where(TestCase.module == module)
    if task_id:
        stmt = stmt.where(TestCase.task_id == task_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(TestCase.title.like(like), TestCase.case_no.like(like)))
    return list(db.execute(stmt).all())


def list_task_groups(db: Session, project_id: int | None = None) -> list[dict]:
    """返回项目下真实产生用例的生成任务分组，按时间升序编号"第N次生成"。

    附每批用例总数、已自查数、待复核(有自查备注)数，供用例管理页"生成批次"下拉过滤，
    也用于在批次旁提供"对该批整批自查"的进度依据。
    """
    if not project_id:
        return []
    agg_rows = db.execute(
        select(
            TestCase.task_id,
            func.count(TestCase.id).label("case_count"),
            func.sum(sql_case((TestCase.ai_checked_at.isnot(None), 1), else_=0)).label("checked_count"),
            func.sum(sql_case((TestCase.ai_remark.isnot(None), 1), else_=0)).label("flagged_count"),
        )
        .where(TestCase.project_id == project_id, TestCase.task_id.isnot(None))
        .group_by(TestCase.task_id)
    ).all()
    if not agg_rows:
        return []
    agg_map = {r.task_id: r for r in agg_rows}
    tasks = db.scalars(
        select(GenerationTask)
        .where(GenerationTask.id.in_(list(agg_map.keys())))
        .order_by(GenerationTask.created_at.asc())
    ).all()
    items: list[dict] = []
    seq = 0
    for t in tasks:
        agg = agg_map.get(t.id)
        if agg is None:
            continue
        seq += 1
        items.append(
            {
                "task_id": t.id,
                "task_no": t.task_no,
                "seq": seq,
                "status": t.status,
                "created_at": t.created_at,
                "finished_at": t.finished_at,
                "case_count": int(agg.case_count or 0),
                "checked_count": int(agg.checked_count or 0),
                "flagged_count": int(agg.flagged_count or 0),
            }
        )
    return items


def list_modules(db: Session, project_id: int | None = None) -> list[str]:
    """返回项目下已有用例的去重模块列表（用于前端模块下拉筛选/编辑）"""
    stmt = select(TestCase.module).where(TestCase.module.is_not(None)).distinct()
    if project_id:
        stmt = stmt.where(TestCase.project_id == project_id)
    stmt = stmt.order_by(TestCase.module)
    return [m for m in db.scalars(stmt).all() if m]


def get_case(db: Session, case_id: int) -> TestCase:
    case = db.get(TestCase, case_id)
    if not case:
        raise NotFoundError("用例不存在")
    return case


def create_case(db: Session, req: TestCaseCreate, user_id: int) -> TestCase:
    return _insert_case(
        db,
        req.project_id,
        test_point_id=req.test_point_id,
        title=req.title,
        module=(req.module or "").strip() or None,
        preconditions=req.preconditions,
        steps=[s.model_dump() for s in req.steps],
        expected_result=req.expected_result,
        priority=req.priority,
        test_type=req.test_type,
        source=req.source,
        created_by=user_id,
    )


def auto_complete_case(db: Session, case_id: int, user_id: int) -> tuple[TestCase, list[str]]:
    """FR-5.5 用例自动补全: 分析缺失字段并调用 LLM 补全，返回 (用例, 已补全字段列表)"""
    from app.services.llm_service import llm_service

    case = get_case(db, case_id)
    missing = []
    if not (case.preconditions or "").strip():
        missing.append("preconditions")
    if not case.steps:
        missing.append("steps")
    if not (case.expected_result or "").strip():
        missing.append("expected_result")
    if not missing:
        return case, []

    # 组装补全上下文
    context = [f"- 用例编号: {case.case_no}", f"- 用例标题: {case.title}"]
    if case.test_point_id:
        tp = db.get(TestPoint, case.test_point_id)
        if tp:
            context.append(f"- 关联测试点({tp.type}): {tp.name}（{tp.description or ''}）")
    if case.preconditions:
        context.append(f"- 已有前置条件: {case.preconditions}")
    if case.steps:
        context.append(f"- 已有步骤: {json.dumps(case.steps, ensure_ascii=False)}")
    if case.expected_result:
        context.append(f"- 已有预期结果: {case.expected_result}")

    field_desc = {
        "preconditions": "preconditions: 前置条件字符串，如\"用户已登录且拥有管理员权限\"",
        "steps": "steps: 步骤数组，格式 [{\"step_no\": 1, \"action\": \"操作步骤\", \"expected\": \"该步骤预期结果\"}]",
        "expected_result": "expected_result: 预期结果字符串，描述用例最终应达到的状态",
    }
    prompt = (
        "请补全以下测试用例中缺失的字段，使用例完整、可执行。\n\n"
        f"现有信息:\n{chr(10).join(context)}\n\n"
        f"缺失字段: {', '.join(missing)}\n\n"
        "请严格输出 JSON，只包含以下缺失字段对应的键:\n"
        + "\n".join(f"- {field_desc[k]}" for k in missing)
        + "\n\n只输出 JSON 对象，不要输出任何其他内容。"
    )
    try:
        data = llm_service.chat_json(prompt, system="你是资深测试工程师，请补全测试用例缺失字段，输出合法 JSON。", timeout=300)
    except Exception as e:
        raise BusinessError(f"AI 补全失败: {e}")

    new_data: dict = {}
    if "preconditions" in data and not (case.preconditions or "").strip():
        new_data["preconditions"] = _to_str(data.get("preconditions"))
    if "steps" in data and not case.steps:
        steps = data.get("steps") or []
        if isinstance(steps, list):
            new_data["steps"] = [
                {"step_no": i + 1, "action": str(s.get("action", "") or ""), "expected": str(s.get("expected", "") or "")}
                for i, s in enumerate(steps)
            ]
    if "expected_result" in data and not (case.expected_result or "").strip():
        new_data["expected_result"] = _to_str(data.get("expected_result")) or ""
    if not new_data:
        return case, []

    # 保存版本快照后更新
    version = TestCaseVersion(
        case_id=case.id,
        version=_next_version(db, case.id),
        content={
            "title": case.title,
            "preconditions": case.preconditions,
            "steps": case.steps,
            "expected_result": case.expected_result,
            "priority": case.priority,
            "test_type": case.test_type,
        },
        change_log="AI 自动补全",
        created_by=user_id,
    )
    for k, v in new_data.items():
        setattr(case, k, v)
    # 内容被补全，旧 AI 自查备注失效
    case.ai_remark = None
    case.ai_checked_at = None
    db.add(version)
    db.commit()
    db.refresh(case)
    return case, missing


def _next_version(db: Session, case_id: int) -> int:
    """计算下一个版本号"""
    from sqlalchemy import func

    max_version = db.scalar(select(func.max(TestCaseVersion.version)).where(TestCaseVersion.case_id == case_id))
    return (max_version or 0) + 1


def update_case(db: Session, case_id: int, req: TestCaseUpdate, user_id: int) -> TestCase:
    case = get_case(db, case_id)
    # 保存版本快照
    version = TestCaseVersion(
        case_id=case.id,
        version=_next_version(db, case.id),
        content={
            "title": case.title,
            "preconditions": case.preconditions,
            "steps": case.steps,
            "expected_result": case.expected_result,
            "priority": case.priority,
            "test_type": case.test_type,
        },
        change_log="编辑用例",
        created_by=user_id,
    )
    data = req.model_dump(exclude_unset=True)
    if "steps" in data and data["steps"] is not None:
        # model_dump() 后 steps 已是 list[dict]（Pydantic v2 默认行为），兼容 dict / TestStep 两种形态
        data["steps"] = [s if isinstance(s, dict) else s.model_dump() for s in data["steps"]]
    for k, v in data.items():
        if v is not None or k == "test_point_id":
            setattr(case, k, v)
    # 内容可能已变化，旧 AI 自查备注失效
    case.ai_remark = None
    case.ai_checked_at = None
    db.add(version)
    db.commit()
    db.refresh(case)
    return case


def review_case(db: Session, case_id: int, action: str, comment: str | None, user_id: int) -> TestCase:
    case = get_case(db, case_id)
    if action == "approve":
        case.status = "reviewed"
    elif action == "reject":
        case.status = "draft"
    db.commit()
    db.refresh(case)
    return case


def batch_action(db: Session, case_ids: list[int], action: str, user_id: int) -> int:
    cases = db.scalars(select(TestCase).where(TestCase.id.in_(case_ids))).all()
    if action == "approve":
        for c in cases:
            c.status = "reviewed"
    elif action == "delete":
        for c in cases:
            db.delete(c)
    db.commit()
    return len(cases)


def set_feedback(db: Session, case_id: int, feedback: str) -> TestCase:
    """设置 AI 生成质量人工反馈（good/bad），clear 表示清除"""
    case = get_case(db, case_id)
    case.feedback = None if feedback == "clear" else feedback
    db.commit()
    db.refresh(case)
    return case


def list_cases_by_ids(db: Session, case_ids: list[int]) -> list[TestCase]:
    """按 ID 批量查询用例（保持传入顺序）"""
    cases = {c.id: c for c in db.scalars(select(TestCase).where(TestCase.id.in_(case_ids))).all()}
    return [cases[i] for i in case_ids if i in cases]


def regenerate_cases(db: Session, case_ids: list[int], user_id: int) -> list[TestCase]:
    """FR-3.8 批量重生成：基于关联测试点/原用例上下文，重新调用 LLM 生成用例并覆盖更新。

    仅对来源为 AI 生成的用例执行；跳过无关联上下文或手工用例。
    """
    from app.core.exceptions import BusinessError
    from app.services.llm_service import llm_service

    cases = list_cases_by_ids(db, case_ids)
    if not cases:
        raise NotFoundError("未找到需要重生成的用例")

    updated = []
    for case in cases:
        if case.source != "ai":
            continue
        # 组装重生成上下文：优先用关联测试点，其次用原用例内容
        context = [f"- 用例编号: {case.case_no}", f"- 原用例标题: {case.title}"]
        if case.test_point_id:
            tp = db.get(TestPoint, case.test_point_id)
            if tp:
                context.append(f"- 测试点({tp.type}): {tp.name}（{tp.description or ''}）")
        if case.preconditions:
            context.append(f"- 原前置条件: {case.preconditions}")
        if case.steps:
            context.append(f"- 原步骤: {json.dumps(case.steps, ensure_ascii=False)}")
        if case.expected_result:
            context.append(f"- 原预期结果: {case.expected_result}")

        prompt = (
            "请基于以下信息重新生成一份更完善、可执行性更强的测试用例。\n\n"
            + "\n".join(context)
            + "\n\n请严格输出 JSON，格式如下:\n"
            '{"title": "用例标题", "module": "所属功能模块，如设备管理", "preconditions": "前置条件", '
            '"steps": [{"step_no": 1, "action": "操作步骤", "expected": "该步骤预期结果"}], '
            '"expected_result": "预期结果", "priority": "L1|L2|L3|L4", "test_type": "测试类型"}\n'
            "等级依据《测试用例等级定义规范》：L1 基本（主流程/主要入口，约 10%）、"
            "L2 重要（常用正常功能、有效等价类与有效边界值，约 20%）、"
            "L3 一般（无效等价类、特殊字符、超长、超时、性能、兼容性，约 60%）、"
            "L4 轻微（深层路径、生僻预置条件、易用性与体验性问题，约 10%）。\n"
            "只输出 JSON 对象，不要输出任何其他内容。"
        )
        try:
            data = llm_service.chat_json(
                prompt, system="你是资深测试工程师，请输出高质量测试用例，仅返回 JSON。", timeout=300
            )
        except Exception as e:
            raise BusinessError(f"用例 {case.case_no} 重生成失败: {e}")

        # 保存版本快照后覆盖
        version = TestCaseVersion(
            case_id=case.id,
            version=_next_version(db, case.id),
            content={
                "title": case.title,
                "preconditions": case.preconditions,
                "steps": case.steps,
                "expected_result": case.expected_result,
                "priority": case.priority,
                "test_type": case.test_type,
            },
            change_log="AI 批量重生成",
            created_by=user_id,
        )
        steps = data.get("steps") or []
        case.title = _to_str(data.get("title")) or case.title
        case.module = (_to_str(data.get("module")) or "").strip() or case.module
        case.preconditions = _to_str(data.get("preconditions"))
        case.steps = steps if isinstance(steps, list) else case.steps
        case.expected_result = _to_str(data.get("expected_result")) or case.expected_result
        case.priority = _to_str(data.get("priority")) or case.priority
        case.test_type = _to_str(data.get("test_type")) or case.test_type
        case.feedback = None  # 重生成后清除旧反馈
        case.ai_remark = None  # 内容已变，旧自查备注失效
        case.ai_checked_at = None
        db.add(version)
        updated.append(case)

    db.commit()
    for c in updated:
        db.refresh(c)
    return updated


def _to_str(v) -> str | None:
    """兼容 LLM 返回的多种类型：list 转 JSON 字符串，其余转 str"""
    if v is None:
        return None
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def save_generated_case(
    db: Session,
    project_id: int,
    data: dict,
    test_point_id: int | None,
    user_id: int,
    task_id: int | None = None,
    req_ref: str | None = None,
    ai_remark: str | None = None,
) -> TestCase:
    """保存 AI 生成的用例

    :param task_id: 所属生成任务 id（供按任务追溯/自查）
    :param req_ref: 生成该用例时所依据的需求原文（自查对照用）
    :param ai_remark: 规则层质量校验发现的问题备注（写入 ai_remark 供前端展示）
    """
    steps = data.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    return _insert_case(
        db,
        project_id,
        test_point_id=test_point_id,
        task_id=task_id,
        req_ref=req_ref,
        ai_remark=ai_remark,
        title=_to_str(data.get("title")) or "未命名用例",
        module=(_to_str(data.get("module")) or "").strip() or None,
        preconditions=_to_str(data.get("preconditions")),
        steps=steps,
        expected_result=_to_str(data.get("expected_result")) or "",
        priority=_to_str(data.get("priority")) or "L2",
        test_type=_to_str(data.get("test_type")) or "功能测试",
        source="ai",
        created_by=user_id,
    )
