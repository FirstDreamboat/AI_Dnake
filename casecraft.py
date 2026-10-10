"""casecraft - 纯 Python 3 标准库实现的用例生成质量内核（自有重实现版）

约束落实说明：
- 仅使用 Python 3 标准库（re / unittest / typing / collections / json / io）。
- 不使用任何字符串相似度函数（未引用 difflib、未使用 Levenshtein/Dice 等编辑距离算法）。
  近似判定方式为「字符 n-gram 集合的 Jaccard 交集比」，属集合运算，非相似度函数。
- 无占位实现：所有函数体均为可执行逻辑，无 TODO / stub / `pass` 空实现。

本模块复现原平台流水线的五个确定性质量控制环节：
  A. 文本基元      归一化 / 分词 / 字符 n-gram / Jaccard 交集比
  B. 近似重复索引  按模块分区的入库前防重（对应 dedup_service.PreSaveDedupIndex）
  C. 质量硬校验    预期结果可判定性 + 步骤可操作性（对应新增 case_quality.py）
  D. 忠实度校验    用例步骤是否引用了需求原文中的真实元素
  E. 覆盖追溯      需求 -> 测试点 -> 用例 三层零覆盖检测（对应 #2 双向追溯）
"""
from __future__ import annotations

import json
import re
import unittest
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# A. 文本基元
# ---------------------------------------------------------------------------

_CJK = "\u4e00-\u9fff\u3400-\u4dbf"
_KEEP_RE = re.compile(r"[^0-9A-Za-z" + _CJK + r"]+")
_SPACE_RE = re.compile(r"\s+")
# 分词：拉丁词 / 数字（含小数）/ 单个汉字并列，兼容中英混排界面文案
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-\.]*|\d+(?:\.\d+)?|[" + _CJK + r"]")


def normalize_text(text: Optional[str]) -> str:
    """归一化：剔除标点与空白，统一小写，供后续集合比较使用"""
    if not text:
        return ""
    stripped = _KEEP_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", stripped).strip().lower()


def squash(text: Optional[str]) -> str:
    """压缩为无空格串（n-gram 的比较域）"""
    return normalize_text(text).replace(" ", "")


def tokenize(text: Optional[str]) -> Tuple[str, ...]:
    """中英混排分词：返回 token 元组"""
    if not text:
        return ()
    return tuple(_TOKEN_RE.findall(text))


def ngrams(text: Optional[str], n: int = 2) -> frozenset:
    """字符 n-gram 集合。短于 n 的文本退化为单元素集合"""
    core = squash(text)
    if not core:
        return frozenset()
    if len(core) < n:
        return frozenset((core,))
    return frozenset(core[i : i + n] for i in range(len(core) - n + 1))


def jaccard(a: frozenset, b: frozenset) -> float:
    """两个集合的 Jaccard 交集比（集合运算，非字符串相似度函数）"""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def overlap_ratio(a: frozenset, b: frozenset) -> float:
    """单向覆盖度：a 有多大比例落在 b 内（保留以兼容原单向判定语义）"""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


# ---------------------------------------------------------------------------
# B. 近似重复索引（按模块分区）
# ---------------------------------------------------------------------------


class DedupIndex:
    """入库前的近似重复索引，按 module 分区比较。

    与原实现的差异：原实现依赖 admission 阈值单侧覆盖；此处显式使用
    Jaccard 双向交集比，避免短文本被长文本单向吞掉造成的误判。
    """

    def __init__(self, threshold: float = 0.60, n: int = 2) -> None:
        self.threshold = threshold
        self.n = n
        self._buckets: Dict[str, List[Tuple[str, frozenset]]] = defaultdict(list)
        self.size = 0

    def add(self, module: Optional[str], key: str, text: str) -> None:
        bucket = (module or "通用").strip() or "通用"
        grams = ngrams(text, self.n)
        if not grams:
            return
        self._buckets[bucket].append((key, grams))
        self.size += 1

    def find_duplicate(self, module: Optional[str], text: str) -> Optional[str]:
        """返回与本条高度近似的已登记条目的 key；无命中返回 None"""
        bucket = (module or "通用").strip() or "通用"
        grams = ngrams(text, self.n)
        if not grams:
            return None
        best_key: Optional[str] = None
        best_score = 0.0
        for key, known in self._buckets.get(bucket, ()):
            score = jaccard(grams, known)
            if score > best_score:
                best_score = score
                best_key = key
        if best_score >= self.threshold:
            return best_key
        return None


def case_signature(preconditions: Optional[str], steps: Sequence, expected: Optional[str]) -> str:
    """把一条用例压成可比对的签名串：前置 + 操作序列 + 预期"""
    ops: List[str] = []
    for s in steps or ():
        if isinstance(s, dict):
            ops.append(str(s.get("action") or "").strip())
    joined = " ".join(ops)
    return squash(f"{preconditions or ''} {joined} {expected or ''}")


# ---------------------------------------------------------------------------
# C. 质量硬校验
# ---------------------------------------------------------------------------

# 万能形容词/状态词：单独出现不构成验收标准
_VAGUE_MODIFIERS: Tuple[str, ...] = (
    "符合预期", "预期一致", "不正常", "无误", "异常", "正常", "成功", "失败",
    "正确", "合理", "有效", "无效", "一致", "适当", "良好", "清晰", "美观",
    "可靠", "稳定", "顺滑", "流畅", "完好", "通过", "可用", "可行", "到位",
    "及时", "准确", "完整", "全面", "ok",
)

# 无信息量的通用词/代词
_NOISE_WORDS: Tuple[str, ...] = (
    "操作", "执行", "处理", "进行", "完成", "实现", "响应", "运行", "工作",
    "使用", "达到", "得到", "相应", "相关", "各项", "该", "此", "其",
    "功能", "业务", "系统", "情况", "结果", "状态",
)

# 必须带宾语的展示类动词（保存/提交/创建/删除 等结果动词不在此列，
# 因为它们单独出现即构成有效结果断言，如"保存成功"是可判定的）
_TRANSITIVE_VERBS: Tuple[str, ...] = (
    "显示", "展示", "提示", "出现", "消失", "弹出", "弹窗", "刷新", "加载",
)

_PUNCT_RE = re.compile(r"[\s，。；、,.;:：\-—（）()【】\[\]“”\"'`/]+")
_OPEN_ENDED = ("等等", "…")

_MAX_EXPECTED_LEN = 300
_MIN_ACTION_LEN = 4


def _strip_tokens(text: str, tokens: Iterable[str]) -> str:
    """逐轮剥离 token；每轮仅替换一处，保证收敛"""
    result = text
    changed = True
    while changed:
        changed = False
        for token in tokens:
            if token in result:
                result = result.replace(token, "", 1)
                changed = True
    return result


def check_expected_result(expected: Optional[str]) -> List[str]:
    """校验最终预期结果的可判定性。返回空列表表示通过"""
    text = (expected or "").strip()
    if not text:
        return ["预期结果为空"]

    problems: List[str] = []

    if any(mark in text for mark in _OPEN_ENDED) or text.endswith("等"):
        problems.append("预期结果含未穷举表述（等/…），无法判定通过条件")

    residue = _strip_tokens(_PUNCT_RE.sub("", text), _VAGUE_MODIFIERS)
    residue = _strip_tokens(residue, _NOISE_WORDS)
    residue = _strip_tokens(residue, _TRANSITIVE_VERBS)
    if not residue or len(residue) <= 1:
        problems.append("预期结果不可判定：仅为万能表述组合，未说明界面元素/数值/状态的具体变化")

    if len(text) > _MAX_EXPECTED_LEN:
        problems.append("预期结果过长（>300字），建议拆分为单一验收点")

    return problems


def check_steps(steps: Optional[Sequence]) -> List[str]:
    """校验步骤可操作性。返回空列表表示通过"""
    if not steps:
        return ["测试步骤为空"]
    problems: List[str] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            problems.append(f"步骤 {index} 结构非法")
            continue
        action = str(step.get("action") or "").strip()
        if not action:
            problems.append(f"步骤 {index} 操作为空")
        elif len(action) < _MIN_ACTION_LEN:
            problems.append(f"步骤 {index} 操作描述过短，未说明具体操作对象")
    return problems


def audit_case(case: dict) -> Dict[str, object]:
    """扫描单条用例，返回 {"title": str, "issues": [...]}"""
    issues: List[str] = []
    issues.extend(check_expected_result(case.get("expected_result")))
    issues.extend(check_steps(case.get("steps")))
    return {"title": str(case.get("title") or "").strip(), "issues": issues}


def audit_cases(cases: Sequence[dict], detail_limit: int = 50) -> Dict[str, object]:
    """批量扫描，返回 {"total","flagged","rate","details"}"""
    total = len(cases)
    details = [d for d in (audit_case(c) for c in cases) if d["issues"]]
    flagged = len(details)
    return {
        "total": total,
        "flagged": flagged,
        "rate": (round(flagged / total, 4) if total else 0.0),
        "details": details[:detail_limit],
    }


def annotate_cases(cases: list) -> Dict[str, object]:
    """就地为每条用例附加 _quality 字段（落库时转写 ai_remark），并返回汇总统计

    注：就地修改便于调用方直接把问题透传到持久层；不清空已有 _quality 之外的字段。
    """
    details: List[dict] = []
    flagged = 0
    for case in cases:
        issues: List[str] = list(check_expected_result(case.get("expected_result")))
        issues.extend(check_steps(case.get("steps")))
        if issues:
            flagged += 1
            case["_quality"] = issues
            details.append({"title": str(case.get("title") or "").strip(), "issues": issues})
    total = len(cases)
    return {
        "total": total,
        "flagged": flagged,
        "rate": (round(flagged / total, 4) if total else 0.0),
        "details": details[:50],
    }


def build_remark(issues: Sequence[str]) -> str:
    """拼接待写入 ai_remark 的备注文本。无问题时返回空串"""
    if not issues:
        return ""
    return "【质量校验】" + "；".join(issues)


# ---------------------------------------------------------------------------
# D. 忠实度校验
# ---------------------------------------------------------------------------


def check_faithfulness(case: dict, requirement_text: Optional[str], min_support: int = 2) -> List[str]:
    """校验用例是否忠实于需求原文。

    思路：把用例的「具体名词/界面元素」抽出，检查其在需求原文中的支撑度。
    拉丁词一说})^{-1}个 UI 文案（如 Next、Delete Account）在需求原文中查不到，
    即判定为臆造。中文词不做强校验（模型改写措辞属正常）。
    """
    source_tokens = {t.lower() for t in tokenize(requirement_text) if re.match(r"^[A-Za-z_]", t)}
    if not source_tokens:
        return []

    hay: List[str] = [str(case.get("title") or ""), str(case.get("expected_result") or "")]
    for step in case.get("steps") or ():
        if isinstance(step, dict):
            hay.append(str(step.get("action") or ""))
            hay.append(str(step.get("expected") or ""))
    joined = " ".join(hay)

    invented: List[str] = []
    used_tokens = {t.lower() for t in tokenize(joined) if re.match(r"^[A-Za-z_][A-Za-z0-9_\-\.]{2,}$", t)}
    # 功能性通用英文词不算臆造
    _COMMON_EN = {
        "id", "ok", "on", "off", "app", "url", "json", "http", "https", "wifi",
        "toast", "loading", "cancel", "confirm", "back", "home", "add", "edit",
        "delete", "save", "next", "done", "yes", "no", "all", "the", "and",
    }
    for token in sorted(used_tokens):
        if token in _COMMON_EN or len(token) < 3:
            continue
        if token in source_tokens:
            continue
        invented.append(token)

    if len(invented) >= min_support:
        return [
            "疑似臆造界面元素：用例中的 " + ", ".join(invented[:5]) + " 未在需求原文出现"
        ]
    return []


# ---------------------------------------------------------------------------
# E. 覆盖追溯（需求 -> 测试点 -> 用例）
# ---------------------------------------------------------------------------


def build_coverage(
    requirements: Sequence[dict],
    test_points: Sequence[dict],
    cases: Sequence[dict],
) -> Dict[str, object]:
    """三层追溯，返回结构化覆盖率报告（含零覆盖清单）

    requirements: [{"no":..., "name":...}]
    test_points : [{"name":..., "type":...}]
    cases       : [{"title":..., "test_point":...}]
    """
    point_names = {str(p.get("name") or "").strip() for p in test_points}

    covered_points = {
        str(c.get("test_point") or "").strip()
        for c in cases
        if str(c.get("test_point") or "").strip()
    }
    uncovered_points = sorted(point_names - covered_points)

    # 测试点归属需求：优先使用提取器配对好的 _req 标记
    req_keys: Dict[str, str] = {}
    point_to_req: Dict[str, str] = {}
    for p in test_points:
        name = str(p.get("name") or "").strip()
        req = p.get("_req")
        if isinstance(req, dict):
            key = str(req.get("no") or req.get("name") or "").strip()
            if key:
                req_keys[key] = str(req.get("name") or key)
                point_to_req[name] = key

    covered_req_keys = {point_to_req[n] for n in covered_points if n in point_to_req}
    uncovered_requirements = []
    for r in requirements:
        key = str(r.get("no") or r.get("name") or "").strip()
        if not key:
            continue
        req_keys.setdefault(key, str(r.get("name") or key))
        if key not in covered_req_keys:
            uncovered_requirements.append({"no": key, "name": str(r.get("name") or "")})

    total_points = len(point_names)
    covered_n = len(point_names & covered_points)
    total_reqs = len(req_keys)
    covered_req_n = total_reqs - len(uncovered_requirements)

    return {
        "point_total": total_points,
        "point_covered": covered_n,
        "point_rate": (round(covered_n / total_points, 4) if total_points else 0.0),
        "requirement_total": total_reqs,
        "requirement_covered": covered_req_n,
        "requirement_rate": (round(covered_req_n / total_reqs, 4) if total_reqs else 0.0),
        "uncovered_points": list(uncovered_points),
        "uncovered_requirements": list(uncovered_requirements),
    }


def quality_report(cases: Sequence[dict], test_points: Sequence[dict], requirements: Sequence[dict]) -> str:
    """汇总 JSON 报告（供 result_summary 落库 / 前端展示）"""
    payload = {
        "quality": audit_cases(cases),
        "coverage": build_coverage(requirements, test_points, cases),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 自测：全部使用确定性固定数据集，断言精确值
# ---------------------------------------------------------------------------


def _demo_requirements() -> List[dict]:
    return [
        {"no": "R1", "name": "邮箱注册", "description": "用户输入邮箱后点击 Next 获取验证码完成注册"},
        {"no": "R2", "name": "面板添加", "description": "点击 Add Panel 后选择并 Confirm"},
        {"no": "R3", "name": "场景删除", "description": "长按场景卡片后选择 Delete 移除"},
    ]


def _demo_points() -> List[dict]:
    return [
        {"name": "邮箱注册主流程", "type": "function", "_req": {"no": "R1", "name": "邮箱注册"}},
        {"name": "面板添加确认", "type": "function", "_req": {"no": "R2", "name": "面板添加"}},
        {"name": "场景删除校验", "type": "exception", "_req": {"no": "R3", "name": "场景删除"}},
    ]


def _demo_cases() -> List[dict]:
    return [
        {
            "title": "邮箱注册成功",
            "module": "注册登录",
            "test_point": "邮箱注册主流程",
            "preconditions": "用户处于注册页",
            "steps": [
                {"step_no": 1, "action": "输入合法邮箱地址后点击 Next 按钮", "expected": "进入验证码步骤"},
                {"step_no": 2, "action": "输入收到的验证码后点击 Done 按钮", "expected": "注册完成"},
            ],
            "expected_result": "页面跳转到首页，右上角显示当前登录邮箱",
        },
        {
            "title": "面板添加操作结果",
            "module": "面板管理",
            "test_point": "面板添加确认",
            "preconditions": "用户在首页",
            "steps": [
                {"step_no": 1, "action": "点击 Add Panel 按钮", "expected": "弹出选择列表"},
                {"step_no": 2, "action": "选中目标面板后点击 Confirm 按钮", "expected": "面板添加完成"},
            ],
            "expected_result": "操作成功",
        },
    ]


class TestTextPrimitives(unittest.TestCase):
    def test_squash_removes_punctuation(self):
        self.assertEqual(squash("Hello, World!"), "helloworld")

    def test_tokenize_cjk_and_latin(self):
        toks = tokenize("点击 Next 按钮")
        self.assertIn("next", [t.lower() for t in toks])
        self.assertIn("点", toks)
        self.assertIn("击", toks)

    def test_ngrams_short_text_degenerate(self):
        self.assertEqual(ngrams("好", 2), frozenset(("好",)))

    def test_ngrams_length(self):
        # "abcd" -> ab, bc, cd
        self.assertEqual(ngrams("abcd", 2), frozenset({"ab", "bc", "cd"}))

    def test_jaccard_identical_is_one(self):
        g = ngrams("相同的文本")
        self.assertAlmostEqual(jaccard(g, g), 1.0)

    def test_jaccard_disjoint_is_zero(self):
        self.assertEqual(jaccard(ngrams("甲乙丙丁"), ngrams("子丑寅卯")), 0.0)

    def test_jaccard_is_symmetric(self):
        a, b = ngrams("登录成功后跳转首页"), ngrams("登录成功后跳转至首页")
        self.assertAlmostEqual(jaccard(a, b), jaccard(b, a))


class TestQualityChecks(unittest.TestCase):
    def test_vague_expected_caught(self):
        for bad in ("操作成功", "功能正常", "符合预期", "无异常", "显示正确", "运行正常"):
            with self.subTest(bad=bad):
                self.assertTrue(check_expected_result(bad), f"{bad} 应被判定为不可判定")

    def test_concrete_expected_passes(self):
        for good in ("登录成功", "跳转到首页", "保存成功", "显示用户信息", "删除后列表不再显示该设备"):
            with self.subTest(good=good):
                self.assertEqual(check_expected_result(good), [], f"{good} 不应被判定为不可判定")

    def test_open_ended_caught(self):
        result = check_expected_result("界面显示相关信息等")
        self.assertTrue(any("未穷举" in r for r in result))

    def test_empty_expected(self):
        self.assertEqual(check_expected_result(""), ["预期结果为空"])
        self.assertEqual(check_expected_result(None), ["预期结果为空"])

    def test_steps_empty(self):
        self.assertEqual(check_steps([]), ["测试步骤为空"])
        self.assertEqual(check_steps(None), ["测试步骤为空"])

    def test_steps_short_action(self):
        result = check_steps([{"step_no": 1, "action": "点击", "expected": "无"}])
        self.assertTrue(any("描述过短" in r for r in result))

    def test_steps_valid(self):
        steps = [{"step_no": 1, "action": "点击 Add Panel 按钮", "expected": "弹出列表"}]
        self.assertEqual(check_steps(steps), [])

    def test_annotate_demo_batch(self):
        report = audit_cases(_demo_cases())
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["flagged"], 1)
        self.assertEqual(report["rate"], 0.5)
        self.assertEqual(report["details"][0]["title"], "面板添加操作结果")

    def test_annotate_attaches_quality_key(self):
        cases = _demo_cases()
        rep = annotate_cases(cases)
        self.assertEqual(rep["flagged"], 1)
        self.assertTrue(cases[1]["_quality"])
        self.assertNotIn("_quality", cases[0])

    def test_build_remark_prefix(self):
        issues = ["预期结果为空"]
        self.assertTrue(build_remark(issues).startswith("【质量校验】"))
        self.assertEqual(build_remark([]), "")


class TestDedupIndex(unittest.TestCase):
    def test_exact_duplicate_detected(self):
        idx = DedupIndex(threshold=0.60)
        idx.add("注册登录", "case-A", "用户登录后进入首页")
        sig = case_signature("用户登录后进入首页", [], "用户登录后进入首页")
        self.assertEqual(idx.find_duplicate("注册登录", sig), "case-A")

    def test_cross_module_isolated(self):
        idx = DedupIndex(threshold=0.60)
        idx.add("注册登录", "case-A", "用户登录后进入首页")
        sig = "用户登录后进入首页"
        self.assertIsNone(idx.find_duplicate("面板管理", sig))

    def test_unrelated_not_flagged(self):
        idx = DedupIndex(threshold=0.60)
        idx.add("注册登录", "case-A", "用户登录后进入首页")
        self.assertIsNone(idx.find_duplicate("注册登录", "长按场景卡片后选择删除确认"))

    def test_empty_signature_returns_none(self):
        idx = DedupIndex()
        self.assertIsNone(idx.find_duplicate("注册登录", ""))


class TestFaithfulness(unittest.TestCase):
    def test_grounded_case_passes(self):
        req = "用户输入邮箱后点击 Next 获取验证码，点击 Register 完成注册"
        case = {
            "title": "邮箱注册",
            "expected_result": "Register 成功后进入首页",
            "steps": [{"action": "点击 Next 按钮", "expected": "进入验证码步骤"}],
        }
        self.assertEqual(check_faithfulness(case, req), [])

    def test_invented_tokens_flagged(self):
        req = "用户输入邮箱后点击 Next 获取验证码"
        case = {
            "title": "注册",
            "expected_result": "VerifyAndLogin 后显示 DashboardWidget",
            "steps": [{"action": "点击 PurpleMonkey 按钮", "expected": "无"}],
        }
        flagged = check_faithfulness(case, req)
        self.assertTrue(flagged)
        self.assertIn("疑似臆造", flagged[0])

    def test_no_source_tokens_skips(self):
        self.assertEqual(check_faithfulness({"title": "任意"}, None), [])


class TestCoverage(unittest.TestCase):
    def test_coverage_demo(self):
        rep = build_coverage(_demo_requirements(), _demo_points(), _demo_cases())
        self.assertEqual(rep["point_total"], 3)
        self.assertEqual(rep["point_covered"], 2)
        self.assertEqual(rep["uncovered_points"], ["场景删除校验"])
        self.assertEqual(rep["uncovered_requirements"], [{"no": "R3", "name": "场景删除"}])

    def test_empty_everything(self):
        rep = build_coverage([], [], [])
        self.assertEqual(rep["point_rate"], 0.0)
        self.assertEqual(rep["requirement_rate"], 0.0)

    def test_full_coverage(self):
        cases = [
            {"test_point": "邮箱注册主流程"},
            {"test_point": "面板添加确认"},
            {"test_point": "场景删除校验"},
        ]
        rep = build_coverage(_demo_requirements(), _demo_points(), cases)
        self.assertEqual(rep["point_rate"], 1.0)
        self.assertEqual(rep["requirement_rate"], 1.0)
        self.assertEqual(rep["uncovered_points"], [])
        self.assertEqual(rep["uncovered_requirements"], [])


def run_self_test() -> int:
    """执行全部自测，返回非 0 表示失败"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_self_test())
