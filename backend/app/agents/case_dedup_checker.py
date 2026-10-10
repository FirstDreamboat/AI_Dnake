"""重复扫描智能体: 判断一组候选测试用例中哪些属于【同义重复】

- 输入: 已被初筛(同模块+bigram 近似)召回的候选用例，每条以 [code=ID] 标识
- 输出: 真实重复组 JSON，每组给出应保留的代表用例与一句话原因
- 只做标注，不改动用例内容（供人工复核后清理）
"""
from app.agents.base import BaseAgent

DEDUP_SYSTEM_PROMPT = """你是一名严谨的测试用例评审专家，负责从候选用例中识别【同义重复】的用例组。

判定准则（宁缺毋滥，只标确有把握的重复）：
1. 两条用例的被测对象、用户操作主路径与最终预期【本质相同】，仅标题措辞/所属测试点不同时，判为重复。
   例如：A"点击 Delete Account → 确认 → 账户删除成功"与 B"删除账户—点 Delete Account → 弹窗确认 → 账户被删除"判为重复。
2. 下列情况【不视为重复】，必须各自保留：
   - 不同边界值（如密码长度恰好 8 位 / 恰好 16 位）
   - 不同异常输入（如密码错误、密码超长、验证码过期是三种不同场景）
   - 不同业务步骤/不同分支（登录成功 ≠ 登录失败 ≠ 取消删除）
   - 同一操作但断言对象/中间状态不同（如"点击后倒计时开始"≠"点击后弹提示"）
3. 对是否重复拿不准的用例，一律不标。
4. 每组重复只保留一个代表用例 keep：选择覆盖最完整、预期最清晰、信息量最大的一条，其余成员为冗余。
5. 输入中可能包含不属于重复的"干扰用例"，不要把它们并入任何组。

输出必须是 JSON：
{"groups": [{"codes": ["成员code列表"], "keep": "代表用例的code", "reason": "一句话说明为什么判定重复"}]}
- code 必须与输入 [code=...] 完全一致，不得改写、不得漏回、不得凭空造 code。
- 每组 codes 至少 2 个成员，且 keep 必须来自 codes。
- 没有重复时 groups 为空数组。
- 不要输出任何其他文字。"""


class CaseDedupCheckerAgent(BaseAgent):
    name = "case_dedup_checker"

    def run(self, blocks: list[str]) -> dict:
        """判断一批候选用例块，返回 {"groups": [{"codes": [...], "keep": "...", "reason": "..."}]}"""
        prompt = (
            "请判断以下候选用例中是否存在同义重复，并为每组给出应保留的代表用例。\n\n"
            + "\n\n---\n\n".join(blocks)
            + "\n\n请只输出 JSON。"
        )
        result = self.llm.chat_json(
            prompt, system=DEDUP_SYSTEM_PROMPT, temperature=0.1, timeout=600
        )
        if isinstance(result, dict):
            return result
        return {"groups": []}
