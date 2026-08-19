"""用例评审智能体: 检查覆盖率、完整性与规范性"""
from app.agents.base import BaseAgent

TEST_CASE_REVIEW_PROMPT = """你是一名严谨的测试用例评审专家。
请评审以下测试用例清单，检查：覆盖率是否充分、字段是否完整、步骤是否可执行、是否有重复或缺陷。

输出评审结论 JSON：
{
  "overall_score": 85,
  "issues": [
    {"case_title": "用例标题", "level": "error|warning", "issue": "问题描述", "suggestion": "修改建议"}
  ],
  "missing_coverage": ["未覆盖的测试点或场景"],
  "conclusion": "总体评审结论"
}

【测试用例】
{test_cases}

【对应测试点】
{test_points}
"""


class TestCaseReviewerAgent(BaseAgent):
    name = "test_case_reviewer"

    def run(self, test_cases: list[dict], test_points: list[dict]) -> dict:
        """评审用例，返回评审结论"""
        prompt = (
            TEST_CASE_REVIEW_PROMPT.replace("{test_cases}", str(test_cases))
            .replace("{test_points}", str(test_points))
        )
        result = self.llm.chat_json(prompt, system=self.system_prompt)
        return result if isinstance(result, dict) else {
            "overall_score": 0, "issues": [], "missing_coverage": [], "conclusion": str(result)
        }
