"""用例生成智能体: 结合测试点与 RAG 上下文生成结构化测试用例

测试点分批生成（每批多个测试点），要求每个测试点覆盖正常/边界/异常场景。
用例为嵌套结构（含步骤数组），必须使用 json mode；为避免小模型照抄示例占位符，
prompt 不提供完整示例对象，仅给出字段说明。解析层兼容数组/字典映射/单对象多种结构。
"""
from app.agents.base import BaseAgent

TEST_CASE_GENERATE_PROMPT = """你是一名资深的嵌入式软件测试用例设计专家，服务于楼宇对讲、智能家居、智慧病房等嵌入式产品线。

请根据以下【测试点】和【参考历史用例】（参考用例仅供风格与思路借鉴，不要照搬），设计测试用例。

要求：
1. 每个测试点至少生成 2 条用例，复杂测试点可生成 3-4 条（覆盖正常流程、边界条件、异常输入等不同场景）
2. 本批共 {batch_size} 个测试点，用例总数不得少于 {min_cases} 条，不要遗漏任何测试点
3. 每条用例必须包含以下字段：
   - title: 用例标题（简洁描述被测场景）
   - module: 所属功能模块（简明分类，如"设备管理""呼叫对讲""场景联动"等，无明确归属时填"通用"）
   - test_point: 所属测试点名称（必须从上方【测试点】列表中原样复制该条用例对应的测试点名称，不允许改写）
   - preconditions: 前置条件
   - steps: 测试步骤数组，每步包含 step_no(序号)、action(操作)、expected(该步预期)
   - expected_result: 最终预期结果
   - priority: 优先级，仅允许使用 {priority_levels} 中的等级
   - test_type: 测试类型（功能测试/异常测试/边界测试/性能测试/安全测试等）
4. 步骤描述要具体、可执行、无歧义
5. 必须输出 JSON 数组（以 [ 开头），不要输出对象字典（以 { 开头），不要输出任何解释文字
6. 极其重要：所有用例必须严格基于上方【测试点】列表设计，严禁生成与测试点无关的功能，尤其严禁生成"需求管理""文档上传解析""登录注册""用户管理""权限管理"等平台自身功能；【参考历史用例】仅供写作风格借鉴，严禁照搬其中的功能模块与业务内容

【测试点】
{test_points}

【参考历史用例】
{rag_context}
"""

# 每批处理的测试点数量
BATCH_SIZE = 4
# 每个测试点至少生成的用例数
MIN_CASES_PER_POINT = 2
# 兜底重试的 temperature
RETRY_TEMPERATURE = 0.7


class TestCaseGeneratorAgent(BaseAgent):
    name = "test_case_generator"

    def run(
        self,
        test_points: list[dict],
        rag_context: str = "",
        priority_levels: list[str] | None = None,
    ) -> list[dict]:
        """根据测试点生成测试用例，返回用例字典列表（分批生成后汇总去重）"""
        if not test_points:
            return []
        priority_levels = priority_levels or ["P0", "P1", "P2", "P3", "P4"]
        priority_set = {p.strip().upper() for p in priority_levels}
        all_cases: list[dict] = []
        seen: set[str] = set()
        for i in range(0, len(test_points), BATCH_SIZE):
            batch = test_points[i : i + BATCH_SIZE]
            batch_size = len(batch)
            prompt = (
                TEST_CASE_GENERATE_PROMPT.replace("{test_points}", str(batch))
                .replace("{batch_size}", str(batch_size))
                .replace("{min_cases}", str(batch_size * MIN_CASES_PER_POINT))
                .replace("{priority_levels}", "/".join(priority_levels))
                .replace("{rag_context}", rag_context or "（无）")
            )
            cases = self._parse(prompt)
            # 批次内数量不足兜底：提高随机度重试一次，合并去重
            if len(cases) < batch_size * MIN_CASES_PER_POINT:
                cases = self._merge_unique(cases, self._parse(prompt, temperature=RETRY_TEMPERATURE))
            for case in cases:
                # 过滤不在允许范围内的优先级（模型偶发输出 P5 等）
                priority = str(case.get("priority") or "").strip().upper()
                if priority and priority not in priority_set:
                    case["priority"] = "P2"
                key = str(case.get("title") or "").strip()
                if key:
                    if key in seen:
                        continue
                    seen.add(key)
                all_cases.append(case)
        return all_cases

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
