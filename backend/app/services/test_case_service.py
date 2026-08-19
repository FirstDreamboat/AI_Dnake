"""测试用例管理服务"""
import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError, NotFoundError
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


def _gen_case_no(db: Session, project_id: int) -> str:
    """生成用例编号: {产品线代码}-{模块代码}-{序号}（PRD §7.1）"""
    project = db.get(Project, project_id)
    line_code = PRODUCT_LINE_CODES.get(project.product_line if project else None, "GEN")
    # 模块代码：当前未建模模块实体，默认 MOD；后续引入模块管理后可细化
    module_code = "MOD"
    count = len(db.scalars(select(TestCase).where(TestCase.project_id == project_id)).all()) + 1
    return f"{line_code}-{module_code}-{count:03d}"


def list_cases(
    db: Session, page: int, page_size: int, project_id: int | None = None,
    priority: str | None = None, status: str | None = None, source: str | None = None,
    keyword: str | None = None,
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
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(TestCase.title.like(like), TestCase.case_no.like(like)))
    total = len(db.scalars(stmt).all())
    cases = db.scalars(stmt.order_by(TestCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return list(cases), total


def get_case(db: Session, case_id: int) -> TestCase:
    case = db.get(TestCase, case_id)
    if not case:
        raise NotFoundError("用例不存在")
    return case


def create_case(db: Session, req: TestCaseCreate, user_id: int) -> TestCase:
    case = TestCase(
        case_no=_gen_case_no(db, req.project_id),
        project_id=req.project_id,
        test_point_id=req.test_point_id,
        title=req.title,
        preconditions=req.preconditions,
        steps=[s.model_dump() for s in req.steps],
        expected_result=req.expected_result,
        priority=req.priority,
        test_type=req.test_type,
        source=req.source,
        created_by=user_id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


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
            '{"title": "用例标题", "preconditions": "前置条件", '
            '"steps": [{"step_no": 1, "action": "操作步骤", "expected": "该步骤预期结果"}], '
            '"expected_result": "预期结果", "priority": "P0|P1|P2|P3|P4", "test_type": "测试类型"}\n'
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
        case.preconditions = _to_str(data.get("preconditions"))
        case.steps = steps if isinstance(steps, list) else case.steps
        case.expected_result = _to_str(data.get("expected_result")) or case.expected_result
        case.priority = _to_str(data.get("priority")) or case.priority
        case.test_type = _to_str(data.get("test_type")) or case.test_type
        case.feedback = None  # 重生成后清除旧反馈
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


def save_generated_case(db: Session, project_id: int, data: dict, test_point_id: int | None, user_id: int) -> TestCase:
    """保存 AI 生成的用例"""
    steps = data.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    case = TestCase(
        case_no=_gen_case_no(db, project_id),
        project_id=project_id,
        test_point_id=test_point_id,
        title=_to_str(data.get("title")) or "未命名用例",
        preconditions=_to_str(data.get("preconditions")),
        steps=steps,
        expected_result=_to_str(data.get("expected_result")) or "",
        priority=_to_str(data.get("priority")) or "P2",
        test_type=_to_str(data.get("test_type")) or "功能测试",
        source="ai",
        created_by=user_id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case
