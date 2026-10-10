"""测试点提取智能体: 从需求中提取测试点

与需求解析一致，采用【普通生成模式 + 管道分隔文本】输出，
避免小模型 json mode 下枚举能力差、照抄示例的问题。

信息链说明（防臆想的关键）:
    需求解析(6列) → 测试点提取(4列) 之间存在信息压缩, 若只把精简后的短描述
    传给用例生成器, 生成器看不到需求原文的按钮/toast/数值/流程, 只能脑补。
    因此 run() 末尾会用 requirement_matching 将每个测试点配对到最可能的需求,
    把需求原文(no/name/description/business_flow)挂到隐藏字段 _req 上,
    随测试点一起透传给用例生成器作为"需求原文依据"。
"""
import logging

from app.agents.base import BaseAgent
from app.agents.requirement_matching import (
    best_match,
    is_reserved_req,
    ngrams,
    overlap_ratio,
    req_text,
)

logger = logging.getLogger(__name__)

TEST_POINT_EXTRACT_PROMPT = """你是一名资深的嵌入式软件测试设计专家。
请根据以下需求清单，提取出【测试点清单】。

要求：
1. 每行输出一个测试点，格式严格为（用 | 分隔，共 4 列）：
   测试点名称|测试点类型|设计技术|测试点描述
   例如：密码长度边界校验|boundary|boundary|验证密码长度取上下边界值与越界值时的处理
2. 测试点类型取值（必须使用下列英文值）: function / boundary / exception / performance / security / implicit
   - function(功能)：正常业务流程验证
   - boundary(边界)：输入边界值、临界状态、容量上限
   - exception(异常)：错误输入、非法操作、异常处理
   - performance(性能)：响应时间、并发处理、大数据量加载
   - security(安全)：权限验证、越权访问、敏感数据保护
   - implicit(隐式场景)：需求未明说但合理推导的场景，如默认状态、空数据、重复操作、中断恢复、首次/末次操作等
2.1 本次需要覆盖的测试点类型（由用户勾选决定，未列出的类型一律不得输出）：{enabled_types}
   本条优先级高于第 3 条的"宁缺毋滥"：只要某类型已被勾选，就必须按下列规则产出，不得以"需求未明说"为由省略。
{extra_type_rules}
2.2 设计技术取值（第 3 列，必须使用下列英文值）：equivalence / boundary / decision_table / state_transition / scenario / orthogonal / error_guessing / none
   - equivalence(等价类划分)：把输入域划分为有效/无效等价类，每类取代表值验证
   - boundary(边界值分析)：取边界点 最小值 / 最小值+1 / 典型值 / 最大值-1 / 最大值 验证
   - decision_table(判定表)：多条件组合的取值表，覆盖各条件组合对应的分支
   - state_transition(状态迁移)：状态→事件→新状态，覆盖正常转换路径与非法转换
   - scenario(场景法)：基本流/备选流/异常流的端到端业务场景串联
   - orthogonal(正交表/两两配对)：多参数多取值时的组合覆盖
   - error_guessing(错误推测)：基于经验推测的易错点（空值、特殊字符、超长、重复提交、中断恢复）
   - none(无需特殊技术)：不涉及取值区间/条件组合/状态变化/流程串联的单一正向验证
   选择规则：从 1) 到 7) 从上到下依次判定，命中第一条即采用该技术：
   1) 需求给出输入取值范围/长度/数量/时间/阈值（如 -10℃～+60℃、8-16 位、最多 5 个、30 分钟）→ boundary
   2) 需求由多个条件共同决定结果（如 温度与湿度共同决定露点、同时满足 A 与 B 才执行）→ decision_table
   3) 需求描述对象状态及其转换（开关通断、在线/离线、连接/断开、运行/停止、正常/故障）→ state_transition
   4) 需求需多步串联完成的业务流程（配置→连接→采集→上报、搜索→添加→绑定）→ scenario
   5) 需求是单一输入项的合法性判定（存在合法/非法两类取值，但未给出明确边界）→ equivalence
   6) 基于经验推测的易错点（空值、特殊字符、超长、重复提交、中断恢复、断电重启）→ error_guessing
   7) 以上均不适用，且该点只验证一个确定取值/单一结果 → none
   严格约束：
   - none 是兜底而非默认：凡涉及"输入是否合法""取值在什么范围""满足什么条件才执行"的一律不得选 none
   - boundary/exception 类型的测试点一律不得选 none
   - implicit 类型不得一律选 error_guessing：偏"流程或场景缺失"的选 scenario，偏"异常或边界操作"的才选 error_guessing
   - 不要为了让各技术都出现而强行拆分测试点
3. 测试点类型由需求内容与 2.1 条共同决定，禁止为了凑齐类型而强行拆分：
   - 每个功能需求默认提取 1 个 function 测试点
   - 仅当需求文档中明确写出了边界值/数值上限/长度/时间限制时，才额外提取 boundary
   - 仅当需求文档明确描述了错误提示/非法输入/失败处理时，才额外提取 exception
   - performance / security / implicit 三类严格按 2.1 条的说明提取：勾选时按规则主动推导，未勾选时一律不得输出
   - 除上述规则外宁缺毋滥，绝不为凑数添加需求无法支撑的测试点
3.1 数值拆分规则（优先级高于第 3 条）：需求中出现数值区间/上下限/阈值/精度/分辨率/
   时长/次数/长度/容量时，不得只提 1 个笼统的测试点（如"存储温度适应"），
   必须拆为下列独立测试点：
   - 下界值：取区间最小值（如 -10℃ 环境下存放）
   - 上界值：取区间最大值（如 +60℃ 环境下存放）
   - 越界-低于下界：低于最小值（如 -15℃），验证超限时的处理
   - 越界-高于上界：高于最大值（如 +70℃），验证超限时的处理
   - 精度/分辨率类指标（如 精度±0.5℃、分辨率0.1℃）单独提取 1 条精度验证测试点
   以上测试点：类型列填 boundary，技术列填 boundary
   约束：
   - 所有数值必须照抄需求原文，严禁估算或编造需求未给出的数值
   - 需求只给出单侧限制（如"不低于99.9%"）时只拆该侧，不得臆造另一侧
   - 若本次未勾选 boundary 类型，则不单独输出上述边界测试点，
     但原测试点的技术列仍须填 boundary，让生成器按边界取值设计用例
4. 极其重要——防编造：只能提取需求清单中【明确出现】的功能/操作/规则对应的测试点。需求文档没有提到的按钮、页面、模块、提示语、参数、数值、时间限制等，一律禁止出现在测试点中；严禁凭"这类产品通常会有"的常识联想补充需求外的功能（例如设备绑定、设备配网、远程控制、固件升级、场景联动等，若需求中不存在则禁止出现）
5. 极其重要——原文保留（界面文案与规则数值）：
   - 需求清单中出现的界面文案（按钮、菜单、toast、提示语、字段标签等）在测试点名称/描述中按【原文】保留（如 Next、Get code、Register、Done、Verify and Login、Please check the privacy policy and user agreement first!），界面文案为英文时不得翻译成中文，也不得自行发明文案；英文大小写、拼写均按原文，不得改写
   - 需求中出现的规则数值必须原样保留：验证码位数（如 4 位数字）、有效期时长（如 30 分钟）、倒计时秒数（如 60 秒后可重新获取）、密码长度与字符组合规则（如"8-16 位、须含大写/小写/数字/符号中至少三种"）、输入长度上限等，不得改写、不得省略、不得凭常识替换
   - 需求【未给出】按钮名/提示文案时，测试点描述只描述系统行为（如"系统给出错误提示"），禁止自创按钮名或提示语（如需求只写"再次获取验证码"时，不得编造 Resend/Resend code 按钮）
6. 极其重要——分步流程不混淆：若需求描述了分步操作流程（如 填写账户→Next→获取验证码→Register→设置密码→Done），测试点必须说明其所处的步骤与对应操作按钮，禁止把不同步骤的按钮混用（不得在第一步使用 Register、不得在设置密码步骤使用 Next、不得把多步合并成一步）
7. 极其重要——预留功能禁止正向提取：需求描述或业务流程中标注"预留""暂不实现""暂不开放""后续版本""第一期不实现""待功能开放"等字样的功能（如手机号注册、手机号格式校验、手机号/邮箱格式校验文案等），【不得】提取为正向 function/boundary/exception 测试点，不得按其可用来设计；该类需求只覆盖当前可用的替代方式（如仅邮箱注册）。若某需求整条都是预留功能（无可测内容），则可不提取测试点
8. 极其重要——同一规则只提取一次：同一条业务规则或同一操作细节被多个需求重复描述时（如国家列表 A-Z 排序、搜索无结果、验证码 4 位/有效期 30 分钟等被多处重复提及），只在首次出现处提取 1 个测试点，后续重复描述不得再生成含义重复的测试点
9. 测试点描述应完整承载关键业务细节（所属步骤、操作按钮、规则数值、提示文案原文），供后续用例设计直接引用，无需自行猜测
10. 不要输出任何其他文字（不要标题、不要解释、不要 markdown 代码块），只输出上述格式的文本行
11. 极其重要：上述示例仅用于说明输出格式，严禁照抄示例内容；需求清单中的每个需求都应至少对应 1 个测试点，不要遗漏需求，也不要为同一需求拆分出意思重复的多个测试点
12. 极其重要——并列渠道必须显式保留渠道名：当需求清单中存在多个并列的登录/注册/支付渠道（如 密码登录、验证码登录、Apple 第三方登录、Google 第三方登录、微信/支付宝等）时，为某个具体渠道设计的测试点，其名称与描述必须包含该渠道的显式标识（品牌或按钮标签原文，如 Apple、Google、Password、Verification Code），严禁用"第三方登录""快捷登录"等笼统词代替具体渠道；为 Apple 渠道需求生成的测试点名称/描述必须带 Apple，为 Google 渠道需求生成的测试点必须带 Google，各渠道的测试点不得互相合并或互相覆盖

需求清单：
{requirements}
"""

# 兜底重试的 temperature
RETRY_TEMPERATURE = 0.7

# 全部测试点类型（顺序即展示顺序）
ALL_TYPES = ("function", "boundary", "exception", "performance", "security", "implicit")
# 扩展类型：不会"自然"从需求里读出来，必须按勾选主动推导，
# 否则用户在页面上勾了它们也永远提取不到（历史问题：这三类产量长期为 0）
EXTRA_TYPES = ("performance", "security", "implicit")

# 各扩展类型的推导规则（仅在勾选时注入 prompt）
_EXTRA_TYPE_RULES = {
    "performance": (
        "   - performance(性能)：已勾选，必须为下列需求各提取 1 个性能测试点，不得省略："
        "涉及页面加载/列表展示/详情跳转/搜索/数据提交保存/多设备状态刷新的需求。"
        "性能测试点验证的是【表现】而非数额：及时响应、无明显卡顿或白屏、反复操作稳定、"
        "弱网与网络波动下可正常降级；需求未给出指标时用\"在合理时间内响应\"\"无卡顿\"等描述性预期，"
        "严禁编造需求未给出的数值（如\"2 秒内\"\"1000 台并发\"）。"
        "若整份文档确实没有上述场景，则为访问频次最高的主流程需求提取 1 个。"
    ),
    "security": (
        "   - security(安全)：对涉及账号登录/注册、权限与角色、敏感数据（密码、手机号、邮箱、位置）、"
        "用户输入提交的需求，各提取 1 个安全测试点，验证未登录或低权限下的越权访问、权限边界、"
        "敏感信息是否明文展示、非法输入与参数篡改。"
        "严禁编造需求外的安全机制（如\"必须具备 AES-256 加密\"）。"
    ),
    "implicit": (
        "   - implicit(隐式场景)：为每个功能需求各提取 1 个隐式测试点，覆盖需求未明说但必然存在的场景："
        "默认状态与初始值、空数据/无数据、重复操作（重复点击、重复提交）、"
        "中断恢复（操作中退出、断网、来电）、首次与末次操作、返回再进入、快速连点。"
        "允许基于需求做合理推导，但推导出的场景必须作用于需求中真实存在的功能与界面元素。"
    ),
}

# LLM 语义合并每次送入的测试点数量
_MERGE_CHUNK = 40

_MERGE_SYSTEM_PROMPT = (
    "你是一名资深的测试设计专家，负责精简测试点清单，剔除语义重复的测试点，"
    "以减少后续用例生成的冗余，同时保证需求覆盖不被破坏。"
)

_MERGE_PROMPT = """以下是候选测试点清单，每行格式：[编号] 测试点名称 | 测试点类型 | 测试点描述

请逐条判断：清单中是否存在【验证的是同一件事】的重复测试点——即两条或多条测试点的被测对象、用户操作、验证预期本质相同，仅措辞/归属的需求条目不同（例如：都验证"点击 Delete Account 后选 Cancel 账户不被删除"；都验证"进入 FAQ 列表点击某个问题查看详情"；都验证"勾选协议后注册成功"）。对每一组这样的重复测试点，只保留其中描述最完整、覆盖最全面的一条。

判定须知：
1. 删除重复测试点不会造成需求覆盖缺失：因为该操作细节对应的需求原文，已被保留的测试点覆盖。
2. 严禁误删真正不同的测试点：不同边界值（如密码长度上/下限）、不同异常输入、不同业务步骤（登录成功/密码错误/密码超长/验证码过期/重复点击获取验证码等）都属于不同测试点，必须保留。
3. 宁缺毋滥：对是否重复拿不准的测试点，一律保留。
4. 只处理清单内已有的内容，禁止臆测清单外功能、禁止新增测试点。
5. 极其重要——不同渠道/品牌的测试点严禁合并：包含不同登录/注册/支付渠道标识的测试点（如 Apple 第三方登录 与 Google 第三方登录、Password 登录 与 Verification Code 登录、Apple 支付 与 Google 支付等）被测对象不同，属于不同测试点，即使操作流程相似（都是"点击图标→系统授权→回调登录"）也不得判定为重复，不得删除其中任何一条，不得以"都是第三方登录"为由合并保留其中一条。

6. 极其重要——不同类型严禁合并：测试点类型（function/boundary/exception/performance/security/implicit）代表不同验证维度，类型不同的测试点即使操作描述相似（如 function 的"卡片正常展示"与 implicit 的"空数据下卡片展示"、function 的"提交订单成功"与 performance 的"提交订单响应时间"）也属于不同测试点，必须全部保留，不得删除其中任何一条。

只输出 JSON：{"kept": [被保留测试点的编号数组]}。被判定为重复的测试点编号不要出现在 kept 中。不要输出任何其他文字。

候选测试点：
{points}"""

# 全部设计技术（顺序即展示顺序）；none 表示无需特殊设计技术
ALL_TECHNIQUES = (
    "equivalence", "boundary", "decision_table", "state_transition",
    "scenario", "orthogonal", "error_guessing", "none",
)

# 中文/英文设计技术 -> 标准值
_TECHNIQUE_MAP = {
    "equivalence": "equivalence", "等价类": "equivalence", "等价类划分": "equivalence",
    "boundary": "boundary", "边界": "boundary", "边界值": "boundary", "边界值分析": "boundary",
    "decision_table": "decision_table", "判定表": "decision_table", "决策表": "decision_table",
    "state_transition": "state_transition", "状态迁移": "state_transition", "状态转换": "state_transition",
    "scenario": "scenario", "场景法": "scenario", "业务流程": "scenario",
    "orthogonal": "orthogonal", "正交": "orthogonal", "正交表": "orthogonal",
    "pairwise": "orthogonal", "两两配对": "orthogonal", "配对": "orthogonal",
    "error_guessing": "error_guessing", "错误推测": "error_guessing", "经验推测": "error_guessing",
    "none": "none", "无": "none", "常规": "none", "": "none",
}


def _resolve_technique(raw) -> str:
    """归一化设计技术取值；未知值回落为 none（不影响后续 uses）"""
    return _TECHNIQUE_MAP.get(str(raw or "").strip().lower(), "none")


# 中文/英文类型 -> 标准类型
_TYPE_MAP = {
    "function": "function", "功能": "function", "功能测试": "function",
    "boundary": "boundary", "边界": "boundary", "边界测试": "boundary", "边界值": "boundary",
    "exception": "exception", "异常": "exception", "异常测试": "exception",
    "performance": "performance", "性能": "performance", "性能测试": "performance",
    "security": "security", "安全": "security", "安全测试": "security",
    "implicit": "implicit", "隐式": "implicit", "隐式场景": "implicit", "隐式测试": "implicit",
}


def parse_test_points_text(text: str) -> list[dict]:
    """解析管道分隔文本为测试点列表，同时兼容 JSON 输出"""
    text = (text or "").strip()
    if not text:
        return []
    json_items = _try_parse_json(text)
    if json_items is not None:
        return json_items
    points: list[dict] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-*1234567890. ")
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        name = parts[0]
        ptype = _TYPE_MAP.get(parts[1].strip().lower(), "function")
        # 4 列=新格式(名称|类型|设计技术|描述)；3 列=旧格式(名称|类型|描述)。
        # 兼容旧格式是为了不破坏历史数据与模型偶发的省略输出，避免整行解析失败丢点。
        if len(parts) >= 4:
            technique = _resolve_technique(parts[2])
            desc = "|".join(parts[3:])
        else:
            technique = "none"
            desc = parts[2] if len(parts) > 2 else ""
        points.append({"name": name, "type": ptype, "technique": technique, "description": desc})
    return points


def _try_parse_json(text: str):
    """若输出是 JSON 数组/对象，则解析；否则返回 None"""
    import json

    content = text.strip()
    if not content.startswith(("[", "{")):
        return None
    try:
        data = json.loads(content)
    except Exception:
        return None
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("test_points"), list):
            return [p for p in data["test_points"] if isinstance(p, dict)]
        items = [v for v in data.values() if isinstance(v, dict)]
        if items and any(v.get("name") or v.get("type") for v in items):
            return items
        if data.get("name") or data.get("type"):
            return [data]
    return None


class TestPointExtractorAgent(BaseAgent):
    name = "test_point_extractor"

    def run(self, requirements: list[dict], include_types: list[str] | None = None) -> list[dict]:
        """根据需求清单提取测试点

        include_types: 用户在生成页勾选的测试点类型；未传（空）时按全部类型处理。
        数量策略（防编造/防膨胀）：
        - 最低要求：每个需求至少 1 个测试点，不足则提高随机度重试一次兜底
        - 硬上限：需求数 × (2 + 勾选的扩展类型数)，防止模型发散超限
        质量兜底（prompt 规则之外的代码层护栏）：
        - 相似去重：跨 Case/跨需求的含义重复测试点只保留首个（同类型内比较）
        - 预留守卫：命中"预留/暂不实现"需求且内容高度重叠的测试点直接剔除
        - 需求配对：每个测试点挂 _req(需求原文)，透传给用例生成器做原文依据
        """
        if not requirements:
            return []
        enabled_types = self._resolve_types(include_types)
        prompt = self._build_prompt(requirements, enabled_types)
        points = self._parse(prompt)
        # 覆盖不足兜底：每个需求至少 1 个点
        if len(points) < len(requirements):
            points = self._merge_unique(points, self._parse(prompt, temperature=RETRY_TEMPERATURE))
        # 代码层护栏 1：含义高度重复的测试点只保留首次出现
        points = self._dedup_similar(points)
        # 代码层护栏 1.5：LLM 语义合并（识别"不同措辞、同一操作"的近义重复测试点）
        points = self._llm_semantic_merge(points)
        # 代码层护栏 2：预留/暂不实现功能不得提取为正向可测内容
        points = self._drop_reserved_points(points, requirements)
        # 代码层护栏 3：测试点 ↔ 需求原文配对（透传给生成器，防用例设计脑补）
        covered_no: set = set()
        for p in points:
            tp_text = "{} {}".format(p.get("name") or "", p.get("description") or "")
            req, score = best_match(tp_text, requirements)
            if req and score >= 0.18:
                p["_req"] = req
                p["_req_score"] = round(score, 3)
                covered_no.add(str(req.get("no")))

        # 代码层护栏 4：确保每个非预留需求至少覆盖 1 个测试点
        # 背景：需求解析已把并列渠道（Apple/Google/密码/验证码等）拆为独立需求，
        # 但 LLM 面对多条流程相近的渠道需求仍可能合并输出、只留首个渠道的测试点，
        # 导致后续渠道（如 Google）没有任何测试点与用例。此处在代码层强制补齐，
        # 保证各渠道不因模型合并而漏测。
        # 补点类型：默认 function；用户未勾选 function（只想要性能/安全/隐式）时用勾选的第一个类型，
        # 避免补出未勾选类型的点、白占上限
        fill_type = "function" if "function" in enabled_types else enabled_types[0]
        added: list[dict] = []
        existing_names = {str(p.get("name") or "").strip() for p in points}
        for r in requirements:
            no = str(r.get("no") or "")
            if no in covered_no or is_reserved_req(r):
                continue
            base = str(r.get("name") or "").strip()
            if not base:
                continue
            name = base
            idx = 2
            while name in existing_names:
                name = "%s-%d" % (base, idx)
                idx += 1
            detail = str(r.get("flow") or "").strip() or str(r.get("description") or "").strip()
            added.append({
                "name": name,
                "type": fill_type,
                "description": "验证%s：%s，操作完成且结果与需求一致" % (base, detail),
                "_req": r,
                "_req_score": 1.0,
            })
            existing_names.add(name)
        if added:
            points = added + points
        # 按勾选类型过滤：模型与补点环节都可能引入未勾选类型，保证"勾了才生成"的语义
        points = [p for p in points if p.get("type") in enabled_types]
        # 硬上限截断：基础为 需求数 × 2；勾选了扩展类型（性能/安全/隐式）时按类型数放宽，
        # 否则 2 倍上限会把这些刚提取出来的测试点直接截掉，表现为"勾了不生效"
        extra_n = len([t for t in EXTRA_TYPES if t in enabled_types])
        cap = len(requirements) * (2 + extra_n)
        if len(points) > cap:
            points = points[:cap]
        # 统一归一化设计技术：覆盖不足时的补点不带 technique，
        # 在此兜底保证下游与落库拿到的都是合法值或 none
        for p in points:
            p["technique"] = _resolve_technique(p.get("technique"))
        return points

    @staticmethod
    def _resolve_types(include_types: list[str] | None) -> list[str]:
        """归一化勾选的测试点类型；未勾选（空列表）时视为全部类型可用"""
        if not include_types:
            return list(ALL_TYPES)
        picked: list[str] = []
        for t in include_types:
            key = _TYPE_MAP.get(str(t).strip().lower())
            if key and key not in picked:
                picked.append(key)
        return picked or list(ALL_TYPES)

    @staticmethod
    def _build_prompt(requirements: list[dict], enabled_types: list[str]) -> str:
        """按勾选类型组装提取 prompt（扩展类型规则仅在勾选时注入）"""
        extra_rules = "\n".join(
            _EXTRA_TYPE_RULES[t] for t in EXTRA_TYPES if t in enabled_types
        )
        if not extra_rules:
            extra_rules = "   - 本次未勾选性能/安全/隐式类型，这三类一律不得输出。"
        return (
            TEST_POINT_EXTRACT_PROMPT
            .replace("{enabled_types}", " / ".join(enabled_types))
            .replace("{extra_type_rules}", extra_rules)
            .replace("{requirements}", str(requirements))
        )

    def _parse(self, prompt: str, temperature: float | None = None) -> list[dict]:
        try:
            text = self.llm.chat(prompt, system=self.system_prompt, temperature=temperature)
            return parse_test_points_text(text)
        except Exception as e:
            logger.error("[test_point_extractor] LLM 调用失败: %s", e)
            return []

    @staticmethod
    def _merge_unique(a: list[dict], b: list[dict]) -> list[dict]:
        """按测试点名称去重合并"""
        merged = list(a)
        seen = {str(p.get("name") or "").strip() for p in merged}
        for p in b:
            key = str(p.get("name") or "").strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(p)
        return merged

    @staticmethod
    def _dedup_similar(points: list[dict]) -> list[dict]:
        """跨 Case/跨需求含义高度重复的测试点只保留首次出现（代码层兜底）

        判定：两条测试点的文本双向 n-gram 覆盖度都较高（双向相似），
        或一条文本完全包含另一条且长度接近，视为含义重复。
        类型不同的两条测试点不参与比较：类型即验证维度，
        否则 implicit/performance/security 点会被措辞相近的 function 点吞掉。
        """
        kept: list[dict] = []
        seen_texts: list[tuple[str, str]] = []  # (type, text)
        for p in points:
            text = "{} {}".format(p.get("name") or "", p.get("description") or "").strip()
            if not text:
                kept.append(p)
                continue
            ptype = str(p.get("type") or "")
            ga = ngrams(text)
            duplicate = False
            for prev_type, prev in seen_texts:
                if ptype and prev_type and ptype != prev_type:
                    continue
                gb = ngrams(prev)
                if not ga or not gb:
                    continue
                inter = len(ga & gb)
                ab = inter / len(ga)
                ba = inter / len(gb)
                # 双向高度同义（互相覆盖大），或一方基本被另一方覆盖（完全同义的不同措辞）
                if min(ab, ba) >= 0.75 or (max(ab, ba) >= 0.95 and max(len(text), len(prev)) >= 10):
                    duplicate = True
                    break
            if duplicate:
                continue
            seen_texts.append((ptype, text))
            kept.append(p)
        return kept

    def _llm_semantic_merge(self, points: list[dict]) -> list[dict]:
        """LLM 语义合并：跨需求/同义改写的重复测试点只保留表述最完整的一条。

        基于 n-gram 的字面去重无法识别"不同措辞、同一操作"的重复（如 FAQ 场景
        的多条等价描述），此处将测试点分块交给 LLM 判断保留编号。
        - 仅当模型明确删除了至少一条时才采用其结论，避免误删有效测试点
        - 若调用失败或结果不可信（删除过多/为空），安全回退为原清单
        """
        if len(points) < 2:
            return points
        merged: list[dict] = []
        for start in range(0, len(points), _MERGE_CHUNK):
            chunk = points[start : start + _MERGE_CHUNK]
            lines = [
                f"[{start + i}] {p.get('name', '')} | {p.get('type', '')} | "
                f"{p.get('technique', '')} | {p.get('description', '')}"
                for i, p in enumerate(chunk)
            ]
            try:
                resp = self.llm.chat_json(
                    _MERGE_PROMPT.replace("{points}", "\n".join(lines)),
                    system=_MERGE_SYSTEM_PROMPT,
                    temperature=0.1,
                ) or {}
            except Exception as e:  # noqa: BLE001 - 语义合并失败不应中断提取
                logger.warning("[test_point_extractor] 语义合并调用失败，保留原测试点: %s", e)
                merged.extend(chunk)
                continue
            kept_ids = set()
            for k in resp.get("kept") or []:
                try:
                    kept_ids.add(int(k))
                except (TypeError, ValueError):
                    continue
            removed = len(chunk) - len({k for k in kept_ids if start <= k < start + len(chunk)})
            # 结果不可信（全删/删超半数/没删任何一条）时回退原始块
            if removed <= 0 or removed > max(1, int(len(chunk) * 0.5)):
                merged.extend(chunk)
                continue
            merged.extend(p for i, p in enumerate(chunk) if (start + i) in kept_ids)
        return merged

    @staticmethod
    def _drop_reserved_points(points: list[dict], requirements: list[dict]) -> list[dict]:
        """预留功能下游守卫：命中"预留/暂不实现"需求且确实在描述该预留功能的测试点剔除

        说明: 提取 prompt 已禁止正向提取预留功能, 此处兜底剔除模型仍可能输出的
        "手机号注册成功""手机号格式校验"等正向/校验类测试点。判定采用双信号:
        - 信号1: 与预留需求【名称】共享 >= 2 个 bigram，如点含"手机号注册"短语
          命中预留需求名"手机号注册" → 直接剔除（功能短语级命中，可信度高）
        - 信号2: 与预留需求【全文】共享 >= 3 个 bigram 且整体覆盖度 >= 0.12
        与预留需求重叠度低的测试点(如"邮箱注册成功")不受影响。
        """
        reserved_reqs = [r for r in requirements if is_reserved_req(r)]
        if not reserved_reqs:
            return points
        kept: list[dict] = []
        for p in points:
            text = "{} {}".format(p.get("name") or "", p.get("description") or "").strip()
            ga = ngrams(text)
            if len(ga) < 3:
                kept.append(p)
                continue
            drop = False
            for r in reserved_reqs:
                name_shared = len(ga & ngrams("{} {}".format(r.get("no") or "", r.get("name") or "")))
                rt = req_text(r)
                text_shared = len(ga & ngrams(rt))
                if name_shared >= 2:
                    drop = True
                    break
                if text_shared >= 3 and overlap_ratio(text, rt) >= 0.12:
                    drop = True
                    break
            if not drop:
                kept.append(p)
        return kept
