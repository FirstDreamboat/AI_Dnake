"""测试用例质量硬校验（规则层，零 LLM 成本）

把评审报告里反复出现的"预期结果模糊""步骤不明确"从 LLM 的主观判断
下沉为确定性规则扫描：随时可跑、结果可复现、不消耗 token、规则可审计。

判定原则（宁缺毋滥，避免误伤）:
只有当预期结果里【不存在任何可与界面/数据对照的实质内容】时才判不可判定。
"登录成功""跳转到首页"这类虽简短但有明确业务结果的不拦截。

做法：先把万能形容词与标点从句子中剥离得到 residue，若 residue 全部落在
"无信息量的通用动词/需要宾语的展示动词"集合内，才判定为不可判定。
"""
import re

# 万能形容词/状态词：单独出现不构成验收标准
_VAGUE_MODIFIERS = (
    "符合预期", "预期一致", "不正常", "无误", "异常", "正常", "成功", "失败",
    "正确", "合理", "有效", "无效", "一致", "适当", "良好", "清晰", "美观",
    "可靠", "稳定", "顺滑", "流畅", "完好", "通过", "可用", "可行", "到位",
    "及时", "准确", "完整", "全面", "OK", "ok", "Ok",
)

# 无信息量的通用词/代词：剥离后不影响"是否有实质内容"的判断
_NOISE_WORDS = (
    "操作", "执行", "处理", "进行", "完成", "实现", "响应", "运行", "工作",
    "使用", "达到", "得到", "相应", "相关", "各项", "该", "此", "其",
    "功能", "业务", "系统", "情况", "结果", "状态",
)

# 必须带宾语的展示类动词：单独出现等于"什么都没说"
# 注意：不收录 保存/提交/创建/删除/更新/启用/禁用 等结果动词——
# 它们单独出现即构成有效结果断言（如"保存成功"是可判定的）。
_TRANSITIVE_VERBS = (
    "显示", "展示", "提示", "出现", "消失", "弹出", "弹窗", "刷新", "加载",
)

_PUNCT_RE = re.compile(r"[\s，。；、,.;:：\-—（）()【】\[\]“”\"'`/]+")
_OPEN_ENDED = ("等等", "…")


def _strip_tokens(text: str, tokens: tuple[str, ...]) -> str:
    """逐个剥离 token（每轮只替换一处，保证收敛且不误删重复语义）"""
    s = text
    changed = True
    while changed:
        changed = False
        for w in tokens:
            if w in s:
                s = s.replace(w, "", 1)
                changed = True
    return s


def check_expected_result(expected: str | None) -> list[str]:
    """校验最终预期结果的可判定性，返回问题列表（空列表表示通过）"""
    text = (expected or "").strip()
    if not text:
        return ["预期结果为空"]

    problems: list[str] = []

    # 规则 1：未穷举表述（"显示相关信息等"无法判定通过条件）
    if any(k in text for k in _OPEN_ENDED) or text.endswith("等"):
        problems.append("预期结果含未穷举表述（等/…），无法判定通过条件")

    # 规则 2：剥离万能形容词后是否还剩实质内容
    residue = _strip_tokens(_PUNCT_RE.sub("", text), _VAGUE_MODIFIERS)
    residue = _strip_tokens(residue, _NOISE_WORDS)
    residue = _strip_tokens(residue, _TRANSITIVE_VERBS)
    if not residue or len(residue) <= 1:
        problems.append(
            "预期结果不可判定：仅为\"万能表述\"组合，未说明界面元素/数值/状态的具体变化"
        )

    # 规则 3：篇幅异常（过长往往意味着一条用例塞了多个验收点）
    if len(text) > 300:
        problems.append("预期结果过长（>300字），建议拆分为单一验收点")

    return problems


def check_steps(steps: list | None) -> list[str]:
    """校验步骤可操作性，返回问题列表（空列表表示通过）"""
    if not steps:
        return ["测试步骤为空"]
    problems: list[str] = []
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            problems.append(f"步骤 {i} 结构非法")
            continue
        action = str(step.get("action") or "").strip()
        if not action:
            problems.append(f"步骤 {i} 操作为空")
        elif len(action) < 4:
            problems.append(f"步骤 {i} 操作描述过短，未说明具体操作对象")
    return problems


# 内部实现细节词表（自洽性 Critic）：功能用例应只描述【用户可观察到】的界面结果
# 与可对外断言的数据变化，出现这些词说明用例写成了"实现验证"，执行者无从判定。
#
# 词表严格限定为嵌入式/物联网功能用例中几乎不可能合法出现的软件内部概念。
# 刻意不收录 接口 / API / 字段 / 请求 / 响应 —— 在本项目语境下它们多指
# 硬件与通信概念（RS485 接口、Modbus 通信接口、温度字段），收录会造成大量误报。
_IMPL_LEAK_TERMS = (
    "数据库", "数据表", "表结构", "数据库字段",
    "redis", "缓存失效", "清除缓存", "刷新缓存", "缓存穿透", "缓存击穿",
    "线程池", "中间件", "存储过程", "主键", "外键",
    "grpc", "kafka", "rabbitmq", "消息队列", "orm", "事务回滚", "回滚事务",
)


def check_impl_leak(case: dict) -> list[str]:
    """自洽性校验：用例是否混入了内部实现而非用户可观察的行为"""
    parts = [
        str(case.get("title") or ""),
        str(case.get("preconditions") or ""),
        str(case.get("expected_result") or ""),
    ]
    for s in case.get("steps") or []:
        if isinstance(s, dict):
            parts.append(str(s.get("action") or ""))
            parts.append(str(s.get("expected") or ""))
    text = "\n".join(parts).lower()

    hits = [t for t in _IMPL_LEAK_TERMS if t in text]
    if hits:
        return [
            f"用例描述了内部实现而非用户可观察的结果（出现：{'、'.join(hits)}），"
            f"应改写为界面可见的变化或可对外断言的数据"
        ]
    return []


def audit_case(case: dict) -> dict:
    """对单条用例做质量扫描

    :return: {"title":..., "issues":[...]}，issues 为空表示通过
    """
    issues: list[str] = []
    issues.extend(check_expected_result(case.get("expected_result")))
    issues.extend(check_steps(case.get("steps")))
    issues.extend(check_impl_leak(case))
    return {"title": str(case.get("title") or "").strip(), "issues": issues}


def audit_cases(cases: list[dict]) -> dict:
    """批量质量扫描，返回汇总统计与问题明细

    :return: {"total": int, "flagged": int, "rate": float, "details": [...]}
    """
    total = len(cases)
    details = [d for d in (audit_case(c) for c in cases) if d["issues"]]
    flagged = len(details)
    return {
        "total": total,
        "flagged": flagged,
        "rate": round(flagged / total, 4) if total else 0.0,
        "details": details[:50],  # 仅保留前 50 条明细，避免 result_summary 膨胀
    }


def build_coverage(requirements: list[dict], test_points: list[dict], cases: list[dict]) -> dict:
    """需求 → 测试点 → 用例 三层追溯，返回覆盖率与零覆盖清单

    说明：原先的覆盖率接口按"整个项目"统计——项目内只要有任何历史用例挂到该
    测试点就算已覆盖，导致覆盖率长期虚高至接近 100%，失去发现漏测的能力。
    此处严格按【本次任务产出的用例】统计。
    """
    from collections import Counter

    counts = Counter(str(c.get("test_point") or "").strip() for c in cases)

    covered_points: list[str] = []
    uncovered_points: list[str] = []
    for tp in test_points:
        name = str(tp.get("name") or "").strip()
        if counts.get(name, 0) > 0:
            covered_points.append(name)
        else:
            uncovered_points.append(name)

    # 测试点 -> 需求编号（取提取器阶段配对好的 _req）
    point_to_req: dict[str, str] = {}
    for tp in test_points:
        name = str(tp.get("name") or "").strip()
        req = tp.get("_req")
        if isinstance(req, dict) and name:
            key = str(req.get("no") or req.get("name") or "").strip()
            if key:
                point_to_req[name] = key

    req_total: set[str] = set()
    for r in requirements:
        key = str(r.get("no") or r.get("name") or "").strip()
        if key:
            req_total.add(key)
    req_covered = {point_to_req[n] for n in covered_points if n in point_to_req}
    uncovered_reqs = sorted(req_total - req_covered)

    point_total = len(test_points)
    req_total_n = len(req_total)
    return {
        "point_total": point_total,
        "point_covered": len(covered_points),
        "point_rate": round(len(covered_points) / point_total, 4) if point_total else 0.0,
        "requirement_total": req_total_n,
        "requirement_covered": len(req_covered),
        "requirement_rate": round(len(req_covered) / req_total_n, 4) if req_total_n else 0.0,
        "uncovered_points": uncovered_points[:50],
        "uncovered_requirements": uncovered_reqs[:50],
    }


def annotate_cases(cases: list[dict]) -> dict:
    """逐条扫描，并把问题就地写回用例的 _quality 字段，同时返回汇总统计

    就地写回是为了让问题随用例一路透传到落库环节（转写 ai_remark），
    避免二次遍历造成统计与实际备注不一致。
    """
    total = len(cases)
    details: list[dict] = []
    for c in cases:
        issues = (
            check_expected_result(c.get("expected_result"))
            + check_steps(c.get("steps"))
            + check_impl_leak(c)
        )
        if issues:
            c["_quality"] = issues
            details.append({"title": str(c.get("title") or "").strip(), "issues": issues})
    flagged = len(details)
    return {
        "total": total,
        "flagged": flagged,
        "rate": round(flagged / total, 4) if total else 0.0,
        "details": details[:50],  # 仅保留前 50 条明细，避免 result_summary 膨胀
    }


def build_remark(issues: list[str]) -> str:
    """把问题列表拼成写入用例 ai_remark 的备注文本"""
    if not issues:
        return ""
    return "【质量校验】" + "；".join(issues)
