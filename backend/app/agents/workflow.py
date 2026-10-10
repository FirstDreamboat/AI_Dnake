"""智能体工作流编排

流水线: 需求解析 -> 测试点提取 -> (RAG检索) -> 用例生成 -> 用例评审

MVP 采用顺序流水线实现（逻辑清晰、便于调试），
生产环境可平滑替换为 LangGraph 状态图编排（见 langgraph_workflow.py）。
"""
import logging
from dataclasses import dataclass, field
from typing import Callable

from app.agents.requirement_matching import is_reserved_req
from app.agents.requirement_parser import RequirementParserAgent
from app.agents.test_case_generator import TestCaseGeneratorAgent
from app.agents.test_case_reviewer import TestCaseReviewerAgent
from app.agents.test_point_extractor import TestPointExtractorAgent
from app.services.case_quality import annotate_cases, build_coverage
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """工作流执行结果"""

    requirements: list[dict] = field(default_factory=list)
    test_points: list[dict] = field(default_factory=list)
    test_cases: list[dict] = field(default_factory=list)
    review: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)


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

        # 2. 测试点提取（勾选类型透传给提取器：性能/安全/隐式需按勾选主动推导，
        #    否则只靠需求文档自然决定，这三类永远提取不到）
        self._progress(30, "test_point_extraction")
        include_types = options.get("include_types") or []
        result.test_points = self.extractor.run(result.requirements, include_types=include_types)
        # 兜底过滤：模型仍可能输出未勾选类型
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
            cases_per_point=options.get("case_multiplier") or 2,
            requirements=result.requirements,  # 需求原文依据：防生成器靠脑补臆想
        )

        # 4.5 质量硬校验（规则层，零 LLM 成本）：把"预期结果模糊/步骤不可操作"
        #     从评测报告中的自然语言描述，下沉为可复现、可机读的结构化问题清单。
        #     结果写入 result.quality：flagged/rate 进任务汇总，逐条 _quality 随用例落库为 ai_remark。
        self._progress(72, "quality_audit")
        result.quality = annotate_cases(result.test_cases)

        # 4.6 覆盖追溯：统计范围严格限定为"本次产出的用例"。
        #     原覆盖率接口按全项目口径计算，历史用例会把新测试点"洗白"成已覆盖，
        #     导致指标长期虚高、真正漏测不可见。预留/暂不实现需求不计入漏测。
        active_reqs = [r for r in result.requirements if not is_reserved_req(r)]
        result.coverage = build_coverage(active_reqs, result.test_points, result.test_cases)

        # 5. 用例评审（先剔除测试点上隐藏的需求原文 _req 字段，避免整段原文灌入评审上下文）
        self._progress(85, "case_review")
        review_points = [
            {k: v for k, v in tp.items() if not str(k).startswith("_")} for tp in result.test_points
        ]
        try:
            result.review = self.reviewer.run(result.test_cases, review_points)
        except Exception:
            # 评审失败不阻塞主流程，但必须留痕：否则 result_summary 只有"评审失败"无从排查
            logger.warning("用例评审失败，任务继续（不影响生成结果落库）", exc_info=True)
            result.review = {"overall_score": 0, "issues": [], "missing_coverage": [], "conclusion": "评审失败"}

        self._progress(100, "complete")
        return result
