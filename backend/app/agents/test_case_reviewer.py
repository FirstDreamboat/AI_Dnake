"""用例评审智能体: 检查覆盖率、完整性与规范性"""
import logging

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

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

# 单次评审的用例数上限：一次塞入上千条用例会超出 LLM 上下文，导致评审整体失败
_REVIEW_BATCH_SIZE = 40
# 聚合输出的条数上限，防止评审结果把 result_summary 撑爆
_MAX_ISSUES = 100
_MAX_MISSING = 50
# 单批提取的 issues/missing 条数上限
_PER_BATCH_ISSUES = 10


class TestCaseReviewerAgent(BaseAgent):
    name = "test_case_reviewer"

    def _review_once(self, test_cases: list[dict], point_names: list[str]) -> dict:
        prompt = (
            TEST_CASE_REVIEW_PROMPT.replace("{test_cases}", str(test_cases))
            .replace("{test_points}", str(point_names))
        )
        result = self.llm.chat_json(prompt, system=self.system_prompt)
        return result if isinstance(result, dict) else {
            "overall_score": 0, "issues": [], "missing_coverage": [], "conclusion": str(result)
        }

    def run(self, test_cases: list[dict], test_points: list[dict]) -> dict:
        """评审用例，返回评审结论

        用例量大时自动分批评审再聚合；单批失败跳过（留日志），全失败才抛出，
        由调用方（workflow）兜底为"评审失败"且不影响生成结果落库。
        """
        # 测试点压缩为名称列表：完整 dict（含描述等大字段）体积过大
        point_names: list[str] = []
        for tp in test_points or []:
            name = str((tp.get("name") if isinstance(tp, dict) else tp) or "").strip()
            if name:
                point_names.append(name)

        if len(test_cases) <= _REVIEW_BATCH_SIZE:
            return self._review_once(test_cases, point_names)

        total_batches = (len(test_cases) + _REVIEW_BATCH_SIZE - 1) // _REVIEW_BATCH_SIZE
        scores: list[float] = []
        issues: list = []
        missing: list = []
        conclusions: list[str] = []
        for i in range(0, len(test_cases), _REVIEW_BATCH_SIZE):
            batch_no = i // _REVIEW_BATCH_SIZE + 1
            try:
                r = self._review_once(test_cases[i : i + _REVIEW_BATCH_SIZE], point_names)
            except Exception:
                logger.warning("评审批次 %d/%d 失败，跳过该批", batch_no, total_batches, exc_info=True)
                continue
            if isinstance(r.get("overall_score"), (int, float)):
                scores.append(r["overall_score"])
            for it in (r.get("issues") or [])[:_PER_BATCH_ISSUES]:
                if len(issues) < _MAX_ISSUES:
                    issues.append(it)
            for it in (r.get("missing_coverage") or [])[:_PER_BATCH_ISSUES]:
                if it not in missing and len(missing) < _MAX_MISSING:
                    missing.append(it)
            if r.get("conclusion"):
                conclusions.append(str(r["conclusion"]))

        if not scores and not conclusions:
            raise RuntimeError(f"全部 {total_batches} 个评审批次均失败")

        return {
            "overall_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "issues": issues,
            "missing_coverage": missing,
            "conclusion": "；".join(conclusions[:3]) or f"评审完成（{len(scores)}/{total_batches} 批）",
        }
