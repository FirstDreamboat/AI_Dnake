"""AI 自查智能体: 将生成的用例与其需求原文逐一比对，标注存疑/不符之处（只标注、不改动用例）"""
from app.agents.base import BaseAgent

SELF_CHECK_SYSTEM_PROMPT = """你是一名严谨的测试用例质检专家。
你的任务：把【AI 生成的测试用例】和它对应的【需求原文依据】逐条比对，找出可能与需求不一致或依据不足的地方，输出给测试人员复核。

判定准则（宁缺毋滥，只标确有依据的问题）：
1. 原文明确写明的行为/文案/数值/流程，与用例中的表述矛盾时，标"不符"。
   例如：原文为英文页面按钮 "Save"，用例写成 "确认"；原文提示 "Invalid email address"，用例写成 "邮箱格式错误"；原文超时为 30 分钟，用例写 15 分钟；原文要求必须先勾选协议，用例未体现等。
2. 原文完全没提到的操作前提、功能点、提示语、行为（属于用例凭空假设/脑补）时，标"存疑"，并在说明中点出"原文未提及，需人工确认"。
3. 步骤与其预期结果是否自洽、是否可执行（对象/操作/断言是否清晰），明显不可执行或预期缺失时可标"存疑"。
4. 不要因风格、措辞润色、覆盖场景多寡、标题简繁而标注。
5. 每条问题一句说清：错在哪、依据原文哪句话，必要时给出期望修正方向（供人工确认，不要直接改用例）。

输出必须是 JSON：
{
  "results": [
    {
      "case_id": 用例编号原样返回,
      "issues": [
        {"type": "不符|存疑", "detail": "问题说明（引用原文依据）"}
      ]
    }
  ]
}
- case_id 必须与输入中给出的完全一致，不能改、不能漏。
- 每条输入的用例都必须出现在 results 中；没有问题的用例 issues 为空数组。
- 单条用例最多报 4 个问题，取最重要的。
"""


class TestCaseSelfCheckerAgent(BaseAgent):
    name = "test_case_self_checker"

    def run(self, case_blocks: list[str]) -> dict:
        """自查一批用例上下文文本，返回 {results: [...]}"""
        prompt = (
            "请对以下测试用例逐条进行自查。每条开头是【case_id=...】，结束时回传相同 case_id。\n\n"
            + "\n\n---\n\n".join(case_blocks)
            + "\n\n请开始自查并只输出 JSON。"
        )
        result = self.llm.chat_json(
            prompt, system=SELF_CHECK_SYSTEM_PROMPT, temperature=0.2, timeout=600
        )
        if isinstance(result, dict):
            return result
        return {"results": []}
