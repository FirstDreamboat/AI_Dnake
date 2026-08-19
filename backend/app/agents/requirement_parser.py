"""需求解析智能体: 将需求文档解析为结构化需求清单

长文档按块分批解析（避免截断丢失信息），按需求编号/名称去重汇总。

关键设计：qwen2.5 系列小模型在 json mode（format=json）下存在"照抄示例占位符"、
"输出对象字典而非数组"两类问题，导致提取结果严重失真。因此这里采用
【普通生成模式 + 管道分隔文本】输出，模型枚举能力更强（已实测 9/9 完整枚举），
再由代码解析为结构化 JSON。若模型偶尔仍输出 JSON，同样兼容解析。
"""
import re

from app.agents.base import BaseAgent

REQUIREMENT_PARSE_PROMPT = """你是一名资深的嵌入式软件测试需求分析师。
请阅读以下需求文档内容，提取出结构化的【功能需求清单】。

要求：
1. 每行输出一条需求，格式严格为（用 | 分隔，共 6 列）：
   序号|需求名称|需求描述|优先级|类别|业务流程
   例如：1|文档上传解析|支持 PDF/Word/TXT/Markdown 文档上传并解析|P0|功能|登录系统>进入需求管理>上传文档>系统解析>查看解析结果
2. 优先级取值: P0（核心）/ P1（重要）/ P2（一般）
3. 类别取值: 功能 / 性能 / 安全 / 兼容性
4. 极其重要：文档中每个功能模块的每个需求项（如 FR-1.1、FR-2.2 等编号的需求）都必须对应输出一行，不要遗漏，不要合并，宁多勿漏
5. 需求名称用简洁的动宾短语概括，需求描述说明具体功能/指标/规则
6. 业务流程：用 > 连接该需求的关键业务步骤（3~8 步），描述其业务流转过程；纯性能/安全类需求可填 -
7. 不要输出任何其他文字（不要标题、不要解释、不要 markdown 代码块），只输出上述格式的文本行

需求文档内容：
{content}
"""

# 单块最大字符数（控制单次 prompt 长度，兼顾 CPU 推理速度）
CHUNK_SIZE = 2500
# 最多解析的块数（超大文档限流，防止任务无限拉长）
MAX_CHUNKS = 8
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


def _chunk_text(content: str, size: int = CHUNK_SIZE, max_chunks: int = MAX_CHUNKS) -> list[str]:
    """将长文本按字符切分为若干块"""
    content = content.strip()
    if not content:
        return []
    chunks = [content[i : i + size] for i in range(0, len(content), size)]
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
            all_requirements = self._merge_unique(all_requirements, reqs)
        return all_requirements

    def _parse_chunk(self, prompt: str, temperature: float | None = None) -> list[dict]:
        try:
            # 普通生成模式（非 json mode），管道分隔文本枚举能力更强
            text = self.llm.chat(prompt, system=self.system_prompt, temperature=temperature)
            return parse_requirements_text(text)
        except Exception:
            return []

    @staticmethod
    def _merge_unique(a: list[dict], b: list[dict]) -> list[dict]:
        """按需求编号/名称合并去重"""
        merged = list(a)
        seen = {str(r.get("no") or r.get("name") or "").strip() for r in merged}
        for r in b:
            key = str(r.get("no") or r.get("name") or "").strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(r)
        return merged
