"""用例生成智能体: 结合测试点与 RAG 上下文生成结构化测试用例

测试点分批生成（每批多个测试点），要求每个测试点覆盖正常/边界/异常场景。
用例为嵌套结构（含步骤数组），必须使用 json mode；为避免小模型照抄示例占位符，
prompt 不提供完整示例对象，仅给出字段说明。解析层兼容数组/字典映射/单对象多种结构。
"""
import logging

from app.agents.base import BaseAgent
from app.agents.requirement_matching import best_match

logger = logging.getLogger(__name__)

TEST_CASE_GENERATE_PROMPT = """你是一名资深的嵌入式软件测试用例设计专家，服务于楼宇对讲、智能家居、智慧病房等嵌入式产品线（被测产品可能为海外版，界面文案为英文）。

请根据以下【测试点】和【参考历史用例】（参考用例仅供风格与思路借鉴，不要照搬），设计测试用例。

要求：
1. 本批为“每个测试点 {cases_per_point} 条”的档位：每个测试点生成 {cases_per_point} 条用例（允许 ±1 条浮动，严禁超额堆量），并在正常流程、边界条件、异常输入等不同场景间尽量均衡分配
2. 本批共 {batch_size} 个测试点，整批用例总数控制在 {batch_min} ~ {batch_max} 条之间，不要遗漏任何测试点
3. 每条用例必须包含以下字段：
   - title: 用例标题（简洁描述被测场景）
   - module: 所属功能模块（简明分类，如"用户管理""账号设置""对讲呼叫"等，仅根据该用例实际测试的内容归纳，无明确归属时填"通用"；严禁凭空添加测试点之外的新模块）
   - test_point: 所属测试点名称（必须从上方【测试点】列表中原样复制该条用例对应的测试点名称，不允许改写）
   - preconditions: 前置条件
   - steps: 测试步骤数组，每步包含 step_no(序号)、action(操作)、expected(该步预期)
   - expected_result: 最终预期结果
   - priority: 用例等级，仅允许使用 {priority_levels} 中的等级{priority_clause}
   - test_type: 测试类型（功能测试/异常测试/边界测试/性能测试/安全测试等）
4. 步骤描述要具体、可执行、无歧义；每条用例只验证一个独立场景，2~6 步即可，不要一条用例堆叠多个无关操作
4.1 极其重要——预期结果必须可判定（这是用例能否被执行与判定通过的先决条件）：
   - expected_result 必须写明【具体验收对象 + 可对照的变化】：测试人员看到哪个界面元素/哪条数据、发生了什么变化，才算通过
   - 严禁只写"操作成功""功能正常""符合预期""无异常""显示正确"等万能表述——这类预期无法判定通过与不通过
   - 严禁以"等""……"等未穷举表述收尾（如"显示相关信息等"），必须写全具体项
   - 反例："功能正常"；正例："面板添加成功，首页最后位置显示该面板卡片，卡片名称与所选一致"
   - 步骤 action 必须写明具体操作对象（如"点击【完成】按钮"，而非"点击按钮"）
5. 必须输出 JSON 数组（以 [ 开头），不要输出对象字典（以 { 开头），不要输出任何解释文字
6. 极其重要：所有用例必须严格基于上方【测试点】列表设计，严禁生成与测试点无关的功能。注意：测试点中的每个功能都必须生成用例，不得遗漏；【参考历史用例】仅供写作风格借鉴，严禁照搬其中的功能模块与业务内容
7. 极其重要——语言与界面文案真实（防编造）：
   - 界面文案一律以【本批需求原文依据】与测试点中出现的【原文】为准：原文是英文就原样使用英文（按钮/toast/字段/页面，不翻译、不发明、不改拼写），原文是中文就用中文原文；严禁自创任何界面文案
   - 预期结果中：若需求原文/测试点给出了具体提示文案，则原样引用（保持原文语言）；若未给出具体提示，只写"系统提示错误信息"等描述性表达，严禁编造具体提示语内容
   - 严禁编造测试点/需求原文中未出现的数值、时间、次数、参数限制（如"2秒内""连续10次""25℃""超过3次锁定"等）；需要输入数据时使用符合原文规则或真实世界格式的样例值（真实格式的手机号、合规邮箱、正确密码、真实区间内的温度等），不得虚构业务规则
8. 预期与操作的语言要与产品界面一致：描述性文字（标题、前置条件）可用中文，但所有引用到界面上的文案必须使用产品原文
9. 极其重要——以需求原文为依据（防臆想的根本）：【本批需求原文依据】中每条测试点对应的需求原文（界面文案/toast/数值/时间/规则/流程）是该测试点用例设计的【唯一事实来源】。下文示例（如 Register/Get code/4 位验证码/30 分钟/四选三等）仅为说明规则用的举例，不代表当前文档内容——任何文档的真实按钮、toast、数值、流程，一律以本批【需求原文依据】中的原文为准：
   - 原文中出现的按钮、提示语、字段标签、流程必须原样使用；原文【未出现】的按钮名一律禁止自创（改用"点击<功能>按钮"等中文描述性表达，如原文未定义登录按钮时不得自创 Sign In/Log In/Login）；原文【未出现】的具体提示文案一律禁止编造（写"系统提示错误信息"）
   - 规则数值必须照抄原文且不可改动：位数、时长、倒计时、长度、字符组合规则、阈值/区间等一律以原文为准，不得凭常识改写或补齐（例：原文"验证码 4 位数字"不得写 6 位或 '000000'；原文"30 分钟有效"不得写 5 分钟；原文"密码 8-16 位且大写/小写/数字/符号中至少三种"不得臆测"必须含特殊字符"）
   - 需求原文标注"预留/暂不实现/待开放"的功能，不得生成正向操作用例，也不得验证其错误提示
   - 被测产品形态以原文为准：凡 App/嵌入式设备界面交互场景（手机 App、设备按键/触摸界面等），步骤严禁出现浏览器返回、刷新页面、新标签页、网页地址栏等 Web 专用行为；反之原文是网页则可用 Web 行为
   - 若测试点标注"未匹配到需求原文"，只能依据该测试点描述本身，描述未涉及的操作对象/文案/数值一律用中文中性表达，禁止编造界面文案
10. 分步流程必须与需求原文一致：需求原文中的分步流程（例：填账户→Next→Get code→Register→设密码→Done）只是举例；真实流程必须以本批【需求原文依据】为准并原样遵守：用例步骤与各步骤按钮一一对应，禁止跨步骤混用按钮、禁止把多个步骤压缩为一步、禁止为某步骤凭空增加原文没有的操作（如弹窗、二次确认）、禁止漏掉原文中的中间步骤
11. 极其重要——防同义冗余（去重）：【此前已生成用例】中列出的用例与当前批用例，若构成同义重复（被测对象、用户操作主路径与最终预期本质相同，仅措辞/标题/所属测试点不同，例如"点击 Delete Account→取消→账户未被删除"这一操作反复被不同测试点产出），当前批不得再输出该条用例；被去重剔除的条目不占用档位，整批总数可低于下限（宁缺毋滥）。但不同边界值、不同异常输入、不同业务步骤不得误判为重复（如"密码错误"≠"密码超长"≠"验证码过期"，须分别保留）
12. 本批内不同测试点之间同样适用第 11 条：若不同测试点最终都指向同一用户操作+同一验证预期，只为其代表测试点生成一条用例，不得重复生成
13. 极其重要——按【设计技术】(technique) 决定"测哪些取值/哪些组合"：测试点清单中每个测试点带有 technique 字段，标明该点应采用的设计技术。为该测试点设计用例时必须体现该技术，否则只验证了单一取值，覆盖率不足：
   - equivalence(等价类划分)：分别覆盖有效等价类与无效等价类各一条用例（合法输入与非法输入）
   - boundary(边界值分析)：至少覆盖取值区间的下界与上界两个端点（含上界值/下界值与越界值）
   - decision_table(判定表)：按条件取值组合分别出用例，覆盖不同组合对应的分支，不得只覆盖一种组合
   - state_transition(状态迁移)：覆盖"当前状态→触发事件→新状态"的正常转换，以及至少一条非法/不可达转换
   - scenario(场景法)：按基本流、备选流、异常流分别串联成端到端用例
   - orthogonal(正交表/配对)：多参数取值时按两两配对选代表组合，避免只取全合法或全非法的极端组合
   - error_guessing(错误推测)：针对空值、特殊字符、超长输入、重复提交、中断恢复等易错点出用例
   - none：常规单一功能点的正向验证即可
   约束：所有取值与组合必须以【本批需求原文依据】为唯一事实来源；在档位允许的 ±1 条浮动内优先取该技术最具代表性的取值点，不得为凑齐技术路线而编造需求未支持的场景（如需求未给出长度范围时不得输出边界值用例）

【此前已生成用例】
{already_produced}

【测试点】
{test_points}

【本批需求原文依据】
{requirement_refs}

【参考历史用例】
{rag_context}
"""

# 每批处理的测试点数量
BATCH_SIZE = 4
# 默认生成倍数：每个测试点生成的用例条数（1x=1条/点，5x=5条/点）
DEFAULT_CASES_PER_POINT = 2
# 兜底重试的 temperature
RETRY_TEMPERATURE = 0.7

# ===== 用例等级（对齐《测试用例等级定义规范》的四级制）=====
DEFAULT_PRIORITY_LEVELS = ("L1", "L2", "L3", "L4")
# 兜底等级：模型未给出或给出非法等级时使用（L2 = 重要/常规正常功能，最中性）
FALLBACK_PRIORITY = "L2"
# L1 占比上限：规范要求 1 级用例占比受控（约 10%），模型普遍偏爱高等级，超出部分降级
_MAX_L1_RATIO = 0.2

# 各等级判定依据（注入 prompt，取自《软件测试用例等级定义规范》）
_PRIORITY_SPEC_TEXT = {
    "L1": (
        "L1 基本（占比约 10%）：模块主要入口功能、系统基本功能。执行失败会导致多处重要功能无法运行，"
        "属于发生概率最高、最常用的主流程（如\"用户注册成功的主功能逻辑，能够正常注册 1 个用户\"、"
        "登录成功、首页主入口正常展示）。该等级占比应受控制，务必从严判定，严禁滥用"
    ),
    "L2": (
        "L2 重要（占比约 20%）：系统的重要功能，包括功能交互相关、典型应用场景、使用频率较高的正常功能、"
        "需求类功能，以及【有效等价类与有效边界值】（如需求规定字母数字注册时，有效的字母数字组合注册成功）"
    ),
    "L3": (
        "L3 一般（占比约 60%，数量最多）：使用频率较低的功能，包括【无效等价类】、特殊字符、字符串超长、"
        "消息超时、事务完整性，以及性能（压力/负载）、兼容性、可靠性测试（如无效用户名注册、重复提交、弱网加载）"
    ),
    "L4": (
        "L4 轻微（占比约 10%）：非主要功能验证、路径较深的操作、不易被发现的功能、较生僻的预置条件、"
        "用户体验与易用性测试，以及异常功能（如验证码显示不明显/显示不全等体验性问题）"
    ),
}

# 测试点类型 -> 等级下限：规范明确"性能（压力、负载）、兼容性、可靠性"属 L3，
# 模型若把性能用例标成 L1/L2 则按此校正（其余类型不做强制，避免误判）
_TYPE_PRIORITY_FLOOR = {"performance": "L3"}


def _build_priority_clause(priority_levels: list[str]) -> str:
    """按勾选等级生成"分级依据"段落；非规范等级（如历史 P0~P4）返回空串不改动原提示词"""
    lines = []
    for lv in priority_levels:
        text = _PRIORITY_SPEC_TEXT.get(str(lv).strip().upper())
        if not text:
            return ""
        lines.append("   - " + text)
    if not lines:
        return ""
    return (
        "\n   - 分级依据（必须严格执行，等级不得随意抬高）：\n"
        + "\n".join(lines)
        + "\n   - 判定存疑时按更低等级判定（L3 优先于 L2，L2 优先于 L1）；"
        "边界/异常/性能/兼容性类场景严禁标为 L1；同一批用例的等级应呈 L3 最多的金字塔分布"
        "\n   - L4 不可略过：易用性、体验性（如提示是否醒目、布局是否合理）、深层路径与生僻前置条件"
        "应判定为 L4，每个功能模块宜至少产出 1 条 L4 用例"
    )


def _cap_l1_ratio(cases: list[dict]) -> None:
    """L1 占比兜底：规范要求 L1 占比受控（约 10%），超出上限的部分按出现顺序降为 L2"""
    if not cases:
        return
    l1 = [c for c in cases if str(c.get("priority") or "").strip().upper() == "L1"]
    limit = max(1, int(len(cases) * _MAX_L1_RATIO))
    for c in l1[limit:]:
        c["priority"] = "L2"

# 需求原文单条描述/流程注入 prompt 时的最大长度（防止 prompt 无限膨胀）
_MAX_REF_TEXT = 350

# 注入"此前已生成用例"清单的最大条数（防 prompt 无限膨胀，取最近生成的即可有效防止邻批重复）
_MAX_ALREADY = 150


def _summarize_generated(cases: list[dict]) -> list[str]:
    """把一批已生成用例压缩成紧凑摘要，注入后续批次用于防同义冗余。

    格式: [模块] 标题｜操作: 第一步动作 → 第二步动作
    """
    lines: list[str] = []
    for c in cases:
        title = str(c.get("title") or "").strip()
        if not title:
            continue
        module = str(c.get("module") or "").strip() or "通用"
        acts = [
            str(s.get("action") or "").strip()
            for s in (c.get("steps") or [])
            if isinstance(s, dict) and s.get("action")
        ][:2]
        if not acts:
            continue
        acts_txt = " → ".join(a[:26] for a in acts)
        lines.append(f"[{module}] {title[:40]}｜操作: {acts_txt}")
    return lines


def _build_requirement_refs(batch: list[dict], requirements: list[dict]) -> str:
    """为一批测试点生成【本批需求原文依据】块

    每个测试点优先使用提取器配对好的 _req（隐藏字段），否则现场用 n-gram
    在需求清单中重新配对。同一需求被多个测试点命中时只注入一次，避免 prompt 膨胀。
    """
    lines: list[str] = []
    seen_keys: set[str] = set()
    for p in batch:
        name = str(p.get("name") or "").strip() or "（未命名测试点）"
        tp_text = "{} {}".format(p.get("name") or "", p.get("description") or "").strip()
        req = p.get("_req")
        score = float(p.get("_req_score") or 0.0)
        if not isinstance(req, dict) or not req:
            req, score = best_match(tp_text, requirements)
        if not req or score < 0.15:
            lines.append(
                f"- 测试点「{name}」: 未匹配到对应需求原文，仅依据测试点描述；"
                "描述未涉及的操作对象/提示语/数值一律不得编造（用中文中性表达）"
            )
            continue
        key = str(req.get("no") or req.get("name") or "").strip() or str(id(req))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        no = str(req.get("no") or "").strip()
        req_name = str(req.get("name") or "").strip()
        desc = str(req.get("description") or "").strip()[:_MAX_REF_TEXT]
        flow = str(req.get("business_flow") or "").strip()[:_MAX_REF_TEXT]
        lines.append(
            f"- 测试点「{name}」对应需求 {no} {req_name}\n"
            f"  需求描述: {desc or '（无）'}\n"
            f"  业务流程: {flow or '（无）'}"
        )
    return "\n".join(lines) if lines else "（本批无需求原文依据，严格按测试点描述设计，描述未涉及的细节严禁编造）"


class TestCaseGeneratorAgent(BaseAgent):
    name = "test_case_generator"

    def run(
        self,
        test_points: list[dict],
        rag_context: str = "",
        priority_levels: list[str] | None = None,
        cases_per_point: int = DEFAULT_CASES_PER_POINT,
        requirements: list[dict] | None = None,
    ) -> list[dict]:
        """根据测试点生成测试用例，返回用例字典列表（分批生成后汇总去重）

        cases_per_point: 生成倍数（1~5），每个测试点期望生成的用例条数。
        requirements: 需求清单(6列原文)，用于给每批测试点生成"需求原文依据"，
            让用例设计严格锚定原文的按钮/toast/数值/流程，而不是靠脑补。
        """
        if not test_points:
            return []
        requirements = requirements or []
        priority_levels = priority_levels or list(DEFAULT_PRIORITY_LEVELS)
        priority_set = {p.strip().upper() for p in priority_levels}
        priority_clause = _build_priority_clause(priority_levels)
        target = max(1, int(cases_per_point))
        all_cases: list[dict] = []
        seen: set[str] = set()
        # 已生成用例摘要（滚动注入后续批次，供模型识别并回避同义冗余）
        produced_summaries: list[str] = []
        for i in range(0, len(test_points), BATCH_SIZE):
            batch = test_points[i : i + BATCH_SIZE]
            batch_size = len(batch)
            # 每个测试点允许 target±1 条：整批下限/上限据此计算
            batch_min = batch_size * max(1, target - 1)
            batch_max = batch_size * (target + 1)
            # 序列化给模型的测试点剥离隐藏字段(_req/_req_score)，避免整段需求原文重复入 prompt；
            # 原文依据单独由 _build_requirement_refs 注入，原始 batch 仍保留隐藏字段供其取用
            display_batch = [
                {k: v for k, v in tp.items() if not str(k).startswith("_")} for tp in batch
            ]
            prompt = (
                TEST_CASE_GENERATE_PROMPT.replace("{test_points}", str(display_batch))
                .replace("{requirement_refs}", _build_requirement_refs(batch, requirements))
                .replace("{already_produced}", "\n".join(produced_summaries[-_MAX_ALREADY:]) or "（本批为第一批生成，暂无已生成用例）")
                .replace("{batch_size}", str(batch_size))
                .replace("{cases_per_point}", str(target))
                .replace("{batch_min}", str(batch_min))
                .replace("{batch_max}", str(batch_max))
                .replace("{priority_levels}", "/".join(priority_levels))
                .replace("{priority_clause}", priority_clause)
                .replace("{rag_context}", rag_context or "（无）")
            )
            cases = self._parse(prompt)
            # 批次内数量严重不足兜底：提高随机度重试一次，合并去重。
            # 注意：因"防同义冗余"少产的批次不重试（宁缺毋滥，避免把重复用例加回），
            # 仅当平均每个测试点都产不出 1 条用例时才重试补数量。
            if len(cases) < batch_size:
                cases = self._merge_unique(cases, self._parse(prompt, temperature=RETRY_TEMPERATURE))
            for case in cases:
                # 过滤不在允许范围内的等级（模型偶发输出等级体系外的值）
                priority = str(case.get("priority") or "").strip().upper()
                if priority and priority not in priority_set:
                    case["priority"] = FALLBACK_PRIORITY
                key = str(case.get("title") or "").strip()
                if key:
                    if key in seen:
                        continue
                    seen.add(key)
                all_cases.append(case)
            # 滚动记录本批已产出用例摘要，供后续批次回避同义冗余
            produced_summaries.extend(_summarize_generated(cases))
        # 兜底裁剪：模型不遵守档位时，每个测试点最多保留 target+1 条，保证总量可预期
        capped = self._cap_excess(all_cases, cap_per_point=target + 1)
        # 等级规范兜底：性能类不得低于 L3、L1 占比受控
        self._normalize_priorities(capped, test_points)
        return capped

    @staticmethod
    def _normalize_priorities(cases: list[dict], test_points: list[dict]) -> None:
        """按《测试用例等级定义规范》校正等级（prompt 之外的代码层护栏）

        - 性能类测试点产出的用例不得低于 L3（规范把性能/压力/负载归入 L3）
        - L1 占比受控（规范约 10%），超出上限的降为 L2
        仅对规范等级（L1~L4）生效，历史 P0~P4 数据不受影响。
        """
        point_type = {
            str(tp.get("name") or "").strip(): str(tp.get("type") or "") for tp in test_points
        }
        for c in cases:
            floor = _TYPE_PRIORITY_FLOOR.get(point_type.get(str(c.get("test_point") or "").strip(), ""))
            if floor and str(c.get("priority") or "").strip().upper() in ("L1", "L2"):
                c["priority"] = floor
        _cap_l1_ratio(cases)

    @staticmethod
    def _cap_excess(cases: list[dict], cap_per_point: int) -> list[dict]:
        """按用例所属测试点分组，超出 cap 的用例直接丢弃（控制"生成太多"）"""
        counts: dict[str, int] = {}
        kept: list[dict] = []
        for c in cases:
            key = str(c.get("test_point") or "").strip()
            if counts.get(key, 0) >= cap_per_point:
                continue
            counts[key] = counts.get(key, 0) + 1
            kept.append(c)
        return kept

    def _parse(self, prompt: str, temperature: float | None = None) -> list[dict]:
        try:
            result = self.llm.chat_json(prompt, system=self.system_prompt, temperature=temperature)
            return self._normalize(result)
        except Exception as e:
            logger.error("[test_case_generator] LLM 调用失败: %s", e)
            return []

    @staticmethod
    def _merge_unique(a: list[dict], b: list[dict]) -> list[dict]:
        """按用例标题去重合并"""
        merged = list(a)
        seen = {str(c.get("title") or "").strip() for c in merged}
        for c in b:
            key = str(c.get("title") or "").strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(c)
        return merged

    @staticmethod
    def _clean_case(c: dict) -> dict:
        """规范化单条用例字段：preconditions 等字符串字段兼容 list 输出"""
        import json

        def to_str(v):
            if v is None:
                return None
            if isinstance(v, (list, tuple, dict)):
                return json.dumps(v, ensure_ascii=False)
            return str(v)

        cleaned = dict(c)
        for key in ("preconditions", "expected_result", "title", "priority", "test_type", "module", "test_point"):
            if key in cleaned:
                cleaned[key] = to_str(cleaned[key])
        return cleaned

    def _normalize(self, result) -> list[dict]:
        """兼容模型返回的多种 JSON 结构，并规范化字段类型"""
        if isinstance(result, list):
            return [self._clean_case(c) for c in result if isinstance(c, dict)]
        if isinstance(result, dict):
            if isinstance(result.get("test_cases"), list):
                return [self._clean_case(c) for c in result["test_cases"] if isinstance(c, dict)]
            # 兼容模型输出单个对象的情况
            if result.get("title"):
                return [self._clean_case(result)]
            # 兼容 {标题: {用例}} / {用例1: {用例}} 字典映射结构（小模型 json mode 常见输出）
            items = [v for v in result.values() if isinstance(v, dict)]
            if items and any(v.get("title") or v.get("expected_result") for v in items):
                return [self._clean_case(v) for v in items]
        return []
