"""智能体工作流编排

流水线: 需求解析 -> 测试点提取 -> (RAG检索) -> 用例生成 -> 用例评审

MVP 采用顺序流水线实现（逻辑清晰、便于调试），
生产环境可平滑替换为 LangGraph 状态图编排（见 langgraph_workflow.py）。
"""
from dataclasses import dataclass, field
from typing import Callable

from app.agents.requirement_parser import RequirementParserAgent
from app.agents.test_case_generator import TestCaseGeneratorAgent
from app.agents.test_case_reviewer import TestCaseReviewerAgent
from app.agents.test_point_extractor import TestPointExtractorAgent
from app.services.rag_service import rag_service


@dataclass
class WorkflowResult:
    """工作流执行结果"""

    requirements: list[dict] = field(default_factory=list)
    test_points: list[dict] = field(default_factory=list)
    test_cases: list[dict] = field(default_factory=list)
    review: dict = field(default_factory=dict)


class GenerateWorkflow:
    """用例生成工作流"""

    def __init__(self, progress_cb: Callable[[int, str], None] | None = None):
        self.parser = RequirementParserAgent()
        self.extractor = TestPointExtractorAgent()
        self.generator = TestCaseGeneratorAgent()
        self.reviewer = TestCaseReviewerAgent()
        self.progress_cb = progress_cb or (lambda p, s: None)

    def _progress(self, percent: int, stage: str):
        self.progress_cb(percent, stage)

    def run(self, content: str, options: dict | None = None) -> WorkflowResult:
        """执行完整流水线

        :param content: 需求文档文本
        :param options: {"enable_rag": bool, "reference_count": int,
                        "include_types": [...], "priority_levels": [...]}
        """
        options = options or {}
        result = WorkflowResult()

        # 1. 需求解析
        self._progress(10, "requirement_parse")
        result.requirements = self.parser.run(content)

        # 2. 测试点提取
        self._progress(30, "test_point_extraction")
        result.test_points = self.extractor.run(result.requirements)
        # 按 include_types 过滤
        include_types = options.get("include_types") or []
        if include_types:
            result.test_points = [tp for tp in result.test_points if tp.get("type") in include_types]

        # 3. RAG 检索增强（用解析出的需求描述作为检索查询，相关性更高）
        rag_context = ""
        if options.get("enable_rag", True) and content:
            self._progress(45, "rag_retrieval")
            query_text = "；".join(
                f"{r.get('name')}: {r.get('description')}" for r in result.requirements[:10] if r.get("name")
            ) or content[:500]
            try:
                rag_context = rag_service.build_context(
                    query_text,
                    top_k=options.get("reference_count", 5),
                )
            except Exception:
                # RAG 检索失败不阻塞主流程：降级为不使用参考用例
                logger.warning("RAG 检索失败，本次生成不使用参考用例", exc_info=True)
                rag_context = ""

        # 4. 用例生成
        self._progress(60, "case_generation")
        result.test_cases = self.generator.run(
            result.test_points,
            rag_context,
            priority_levels=options.get("priority_levels") or [],
        )

        # 5. 用例评审
        self._progress(85, "case_review")
        try:
            result.review = self.reviewer.run(result.test_cases, result.test_points)
        except Exception:
            result.review = {"overall_score": 0, "issues": [], "missing_coverage": [], "conclusion": "评审失败"}

        self._progress(100, "complete")
        return result
