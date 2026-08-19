"""测试点提取智能体: 从需求中提取测试点

与需求解析一致，采用【普通生成模式 + 管道分隔文本】输出，
避免小模型 json mode 下枚举能力差、照抄示例的问题。
"""
from app.agents.base import BaseAgent

TEST_POINT_EXTRACT_PROMPT = """你是一名资深的嵌入式软件测试设计专家。
请根据以下需求清单，提取出完整的【测试点清单】。

要求：
1. 每行输出一个测试点，格式严格为（用 | 分隔，共 3 列）：
   测试点名称|测试点类型|测试点描述
   例如：文档上传解析正常流程|功能|验证支持PDF文档上传并正确解析
2. 测试点类型取值（必须使用下列英文值）: function / boundary / exception / performance / security / implicit
   - function(功能)：正常业务流程验证
   - boundary(边界)：输入边界值、临界状态、容量上限
   - exception(异常)：错误输入、网络异常、系统异常
   - performance(性能)：响应时间、并发处理
   - security(安全)：权限验证、数据加密
   - implicit(隐式场景)：需求未明说但合理推导的场景，如默认状态、空数据、重复操作、中断恢复、首次/末次操作、异常中断后的恢复流程等
3. 对每个功能需求，必须同时提取 1 个功能测试点(function) 和 1 个异常测试点(exception)
4. 涉及数值范围、时间、长度、容量上限的需求，必须额外提取边界测试点(boundary)
5. 涉及性能指标的需求，必须额外提取性能测试点(performance)；涉及权限/数据安全的需求，必须额外提取安全测试点(security)
6. 对状态类、流程类需求（如注册、提交、审批、导入导出、上传下载、重置等），必须额外提取隐式场景测试点(implicit)，验证默认值/空数据/重复操作/中断恢复等隐含行为
7. 极其重要：测试点总数不得少于需求数量的 2 倍，每个需求至少对应 2 个测试点，不要遗漏任何需求
8. 不要输出任何其他文字（不要标题、不要解释、不要 markdown 代码块），只输出上述格式的文本行

需求清单：
{requirements}
"""

# 兜底重试的 temperature
RETRY_TEMPERATURE = 0.7

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
        desc = parts[2] if len(parts) > 2 else ""
        points.append({"name": name, "type": ptype, "description": desc})
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

    def run(self, requirements: list[dict]) -> list[dict]:
        """根据需求清单提取测试点"""
        if not requirements:
            return []
        prompt = TEST_POINT_EXTRACT_PROMPT.replace("{requirements}", str(requirements))
        points = self._parse(prompt)
        # 数量不足兜底：提高随机度重试一次，合并去重
        if len(points) < len(requirements) * 1.5:
            points = self._merge_unique(points, self._parse(prompt, temperature=RETRY_TEMPERATURE))
        return points

    def _parse(self, prompt: str, temperature: float | None = None) -> list[dict]:
        try:
            text = self.llm.chat(prompt, system=self.system_prompt, temperature=temperature)
            return parse_test_points_text(text)
        except Exception:
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
