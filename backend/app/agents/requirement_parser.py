"""需求解析智能体: 将需求文档解析为结构化需求清单

长文档按块分批解析（避免截断丢失信息），按需求编号/名称去重汇总。

关键设计：qwen2.5 系列小模型在 json mode（format=json）下存在"照抄示例占位符"、
"输出对象字典而非数组"两类问题，导致提取结果严重失真。因此这里采用
【普通生成模式 + 管道分隔文本】输出，模型枚举能力更强（已实测 9/9 完整枚举），
再由代码解析为结构化 JSON。若模型偶尔仍输出 JSON，同样兼容解析。
"""
import logging
import re

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class RequirementParseError(RuntimeError):
    """需求解析失败（LLM 调用失败或持续无有效输出），向上抛出使任务显式失败"""

REQUIREMENT_PARSE_PROMPT = """你是一名资深的嵌入式软件测试需求分析师。
请阅读以下需求文档内容，提取出结构化的【功能需求清单】。

要求：
1. 每行输出一条需求，格式严格为（用 | 分隔，共 6 列）：
   序号|需求名称|需求描述|优先级|类别|业务流程
   例如：1|设备配网|用户通过手机APP扫描设备二维码并输入WiFi密码完成配网|P0|功能|打开APP>添加设备>扫描二维码>输入WiFi密码>等待配网成功
2. 优先级取值: P0（核心）/ P1（重要）/ P2（一般）
3. 类别取值: 功能 / 性能 / 安全 / 兼容性
4. 极其重要：文档中每个功能模块的每个需求项（如 FR-1.1、FR-2.2 等编号的需求）都必须对应输出一行，不要遗漏，不要合并，宁多勿漏
5. 需求名称用简洁的动宾短语概括，需求描述说明具体功能/指标/规则
6. 业务流程：用 > 连接该需求的关键业务步骤（3~8 步），描述其业务流转过程；纯性能/安全类需求可填 -
7. 不要输出任何其他文字（不要标题、不要解释、不要 markdown 代码块），只输出上述格式的文本行
8. 极其重要：上述示例仅用于说明输出格式，严禁照抄示例内容；所有需求必须严格基于需求文档，严禁输出与文档内容无关的功能。注意：需求文档中出现的所有业务功能（包括登录注册、第三方登录等）都属于待解析需求，必须输出，不得遗漏
9. 极其重要——原文保留：被测产品可能是海外版，需求文档中的界面文案（按钮、菜单、字段标签、toast、提示语等）若为英文或其他外文，必须在需求描述与业务流程中【原样保留原文】（如 点击 "Register" 按钮、提示 "The code has been sent"、字段名 "Email"），不要翻译成中文、不要改写、不要省略，以便后续测试设计引用真实界面文案；需求文档以中文书写时正常使用中文
10. 极其重要——并列登录/接入方式必须逐条拆分、禁止合并：需求文档中若列出多个并列的登录方式、注册方式或第三方接入渠道（如 账号密码登录、手机验证码登录、苹果账户登录、谷歌账户登录、微信/支付宝/信用卡支付 等），【每一种方式都必须单独输出为一行需求】，需求名称须带上该方式名（如 "谷歌账户登录"），严禁合并成一条 "第三方登录" 之类的笼统需求；同类方式即使操作流程相似、按钮名称相近，只要渠道/账户体系不同就是不同需求，不得把后出现的渠道判为前面渠道的重复内容而丢弃

需求文档内容：
{content}
"""

# 单块最大字符数（控制单次 prompt 长度，兼顾 CPU 推理速度）
CHUNK_SIZE = 2500
# 最多解析的块数（支持到约 10 万字符的大型 PRD；仍保留上限防止任务无限拉长）
MAX_CHUNKS = 40
# 单块输出低于该数量时，提高随机度重试一次兜底
MIN_EXPECTED_PER_CHUNK = 3
# 兜底重试的 temperature
RETRY_TEMPERATURE = 0.7

# 类别别名 -> 标准类别
_CATEGORY_MAP = {
    "功能": "功能", "功能性": "功能", "function": "功能",
    "性能": "性能", "performance": "性能",
    "安全": "安全", "security": "安全",
    "兼容性": "兼容性", "兼容": "兼容性", "compatibility": "兼容性",
}


# 需求编号模式：FR-1.1 / PRD2.1 / 1.1 / 1、/ 1) / 第1条 等（避免误匹配纯数字、日期）
_REQ_NO_RE = re.compile(
    r"^(?:"
    r"FR[-_.]?\d+(?:[-_.]\d+)*"
    r"|PRD[-_.]?\d+(?:[-_.]\d+)*"
    r"|\d+(?:\.\d+){1,3}"
    r"|\d+[、.)．]"
    r"|第[0-9一二三四五六七八九十百千]+[条章节]"
    r")\s*",
    re.IGNORECASE,
)


def _chunk_text(content: str, size: int = CHUNK_SIZE, max_chunks: int = MAX_CHUNKS) -> list[str]:
    """将长文本按需求编号对齐切分为若干块，优先保证单条需求完整；
    无编号时回退字符滑窗切分。"""
    content = content.strip()
    if not content:
        return []
    lines = content.splitlines()
    boundary = {i for i, ln in enumerate(lines) if _REQ_NO_RE.match(ln.strip())}
    if not boundary:
        chunks = [content[i : i + size] for i in range(0, len(content), size)]
        return chunks[:max_chunks]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for i, ln in enumerate(lines):
        # 遇到新需求编号：若当前块已有内容则结算
        if i in boundary and buf:
            chunks.append("\n".join(buf))
            buf, buf_len = [], 0
        # 超长行单独成块（避免死循环累积）
        if len(ln) > size:
            if buf:
                chunks.append("\n".join(buf))
                buf, buf_len = [], 0
            chunks.append(ln)
            continue
        if buf_len + len(ln) + 1 > size:
            chunks.append("\n".join(buf))
            buf, buf_len = [], 0
        buf.append(ln)
        buf_len += len(ln) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks[:max_chunks]


def parse_requirements_text(text: str) -> list[dict]:
    """解析管道分隔文本为需求列表，同时兼容 JSON 输出"""
    text = (text or "").strip()
    if not text:
        return []
    # 兼容模型输出 JSON 的情况
    json_items = _try_parse_json(text)
    if json_items is not None:
        for it in json_items:
            it.setdefault("business_flow", "")
            it.setdefault("category", "功能")
            it.setdefault("priority", "P2")
        return json_items
    reqs: list[dict] = []
    idx = 0
    for line in text.splitlines():
        line = line.strip().lstrip("-*1234567890. ")
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        idx += 1
        no = parts[0] or f"REQ-{idx:03d}"
        name = parts[1]
        desc = parts[2] if len(parts) > 2 else ""
        priority = parts[3] if len(parts) > 3 and parts[3].upper().startswith("P") else "P2"
        category = _CATEGORY_MAP.get(parts[4], "功能") if len(parts) > 4 else "功能"
        # FR-1.4 业务流程（第 6 列，用 > 连接步骤）
        flow = parts[5].strip() if len(parts) > 5 else ""
        if flow in ("-", "—", "无", "None", "none"):
            flow = ""
        reqs.append({
            "no": no, "name": name, "description": desc,
            "priority": priority, "category": category,
            "business_flow": flow,
        })
    return reqs


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
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("requirements"), list):
            return [r for r in data["requirements"] if isinstance(r, dict)]
        items = [v for v in data.values() if isinstance(v, dict)]
        if items and any(v.get("no") or v.get("name") for v in items):
            return items
        if data.get("no") or data.get("name"):
            return [data]
    return None


class RequirementParserAgent(BaseAgent):
    name = "requirement_parser"

    def run(self, content: str) -> list[dict]:
        """解析需求文档，返回需求清单（分块解析后去重汇总）"""
        if not content or not content.strip():
            return []
        chunks = _chunk_text(content)
        all_requirements: list[dict] = []
        for chunk in chunks:
            prompt = REQUIREMENT_PARSE_PROMPT.replace("{content}", chunk)
            reqs = self._parse_chunk(prompt)
            # 数量不足兜底：提高随机度再解析一次，合并去重
            if len(reqs) < MIN_EXPECTED_PER_CHUNK:
                reqs = self._merge_unique(reqs, self._parse_chunk(prompt, temperature=RETRY_TEMPERATURE))
            if not reqs:
                raise RequirementParseError(
                    "需求解析失败：模型连续两次未返回有效结果，请检查 LLM 服务（Ollama/DeepSeek）是否可用"
                )
            all_requirements = self._merge_unique(all_requirements, reqs)
        # 模型每块输出都从 1 编号，跨块 no 会重复；合并完成后统一重新编号，保证全局唯一
        for i, r in enumerate(all_requirements, start=1):
            r["no"] = f"REQ-{i:03d}"
        return all_requirements

    def _parse_chunk(self, prompt: str, temperature: float | None = None) -> list[dict]:
        try:
            # 普通生成模式（非 json mode），管道分隔文本枚举能力更强
            text = self.llm.chat(prompt, system=self.system_prompt, temperature=temperature)
            return parse_requirements_text(text)
        except Exception as e:
            logger.error("[requirement_parser] LLM 调用失败: %s", e)
            return []

    @staticmethod
    def _merge_unique(a: list[dict], b: list[dict]) -> list[dict]:
        """按需求名称合并去重

        注意：绝不能按 no 去重——分块解析时模型对每块都从 1 重新编号，
        no 跨块必然冲突，导致块2+ 的需求被误判为"重复"而整体丢弃
        （曾导致"苹果/谷歌第三方登录""手机验证码登录"等需求全部缺失）。
        需求名称才是跨块稳定的唯一标识。
        """
        merged = list(a)
        seen = {str(r.get("name") or "").strip() for r in merged if (r.get("name") or "").strip()}
        for r in b:
            key = str(r.get("name") or "").strip()
            if key:
                if key in seen:
                    continue
                seen.add(key)
            merged.append(r)
        return merged
