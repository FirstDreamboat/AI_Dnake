"""用例修订智能体: 按评审 issues 修订被标记的用例（评审闭环的执行端）

评审智能体只发现问题（issues），本智能体负责按问题清单修订对应用例。
修订后由 workflow 替换原用例并触发一轮复评，构成"评审→修订→复评"闭环。
仅接受问题清单中列出的用例，不做全局重生成，防止修订引入大范围回归。
"""
import logging

from app.agents.base import BaseAgent
from app.agents.test_case_generator import TestCaseGeneratorAgent

logger = logging.getLogger(__name__)

CASE_REVISE_PROMPT = """你是一名资深的测试用例设计专家。以下测试用例在评审中被指出问题，请逐条修订。

修订要求：
1. 只修订【待修订用例】中列出的用例，每条都必须返回修订后的完整用例对象（字段结构与原用例一致：title/module/test_point/preconditions/steps/expected_result/priority/test_type）
2. 修订必须针对该用例被指出的问题（issue 与 suggestion），其他没有问题的部分保持原样，不要借机重写无关内容
3. 修订后的预期结果必须可判定：写明【具体验收对象 + 可对照的变化】，严禁"操作成功/功能正常/符合预期"等万能表述
4. 步骤必须具体可执行，操作对象明确；不得编造需求原文之外的按钮/提示语/数值
5. 保留原用例的 original_title 字段（值为修订前的标题），便于系统替换
6. 必须输出 JSON 数组（以 [ 开头），按输入顺序输出全部修订后的用例，不要输出解释文字
7. 若某条用例的问题属于"不应生成该用例"（如与测试点无关、纯重复），可在该对象中加 "discard": true 标记并说明放弃原因，系统将剔除该用例

【待修订用例】（每条含 issues：评审指出的问题）
{flagged_cases}

【对应测试点】
{point_names}

【需求原文依据】（修订时引用界面文案/数值的唯一事实来源）
{requirement_refs}
"""

# 单次修订的用例数上限：修订也是 LLM 调用，问题过多时截断保上下文
_MAX_REVISE_CASES = 20

# 复用生成器的输出兼容解析逻辑（数组/字典映射/单对象）
_NORMALIZER = TestCaseGeneratorAgent()


class TestCaseReviserAgent(BaseAgent):
    name = "test_case_reviser"

    def run(
        self,
        flagged_cases: list[dict],
        point_names: list[str],
        requirement_refs: str = "",
    ) -> list[dict]:
        """修订被标记用例，返回修订后的用例列表（含 original_title / 可选 discard）

        :param flagged_cases: [{"original_title":..., "issues":[...], **用例字段}]
        :param point_names: 对应测试点名称列表
        :param requirement_refs: 需求原文依据文本
        """
        if not flagged_cases:
            return []
        flagged_cases = flagged_cases[:_MAX_REVISE_CASES]
        prompt = (
            CASE_REVISE_PROMPT.replace("{flagged_cases}", str(flagged_cases))
            .replace("{point_names}", str(point_names))
            .replace("{requirement_refs}", requirement_refs or "（无）")
        )
        try:
            try:
                result = self.llm.chat_json(
                    prompt, system=self.system_prompt, temperature=0.2
                )
            except Exception:
                # 偶发 JSON 解析失败重试一次（略升温）
                result = self.llm.chat_json(
                    prompt, system=self.system_prompt, temperature=0.4
                )
        except Exception:
            logger.warning("用例修订 LLM 调用失败，保持原用例", exc_info=True)
            return []
        normalized = _NORMALIZER._normalize(result)
        out: list[dict] = []
        for c in normalized:
            if not isinstance(c, dict):
                continue
            if not (str(c.get("title") or "").strip() or str(c.get("original_title") or "").strip()):
                continue
            out.append(c)
        return out
