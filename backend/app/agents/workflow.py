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
from app.agents.test_case_generator import TestCaseGeneratorAgent, _build_requirement_refs
from app.agents.test_case_reviser import TestCaseReviserAgent
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
        self.reviser = TestCaseReviserAgent()
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

        # 3. RAG 检索增强：改为"按批检索"——生成器每处理一批测试点时，
        #    用该批测试点的名称+描述做查询，参考用例与本批内容直接相关，
        #    相关性远高于过去"整份文档拼一个查询、所有批次共用同一份参考"。
        #    全文档级查询仍保留一份，作为按批检索为空/失败时的回退。
        rag_context = ""
        rag_retriever = None
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

            def _rag_for_batch(batch: list[dict]) -> str:
                query = "；".join(
                    f"{tp.get('name')}: {str(tp.get('description') or '')[:120]}"
                    for tp in batch if tp.get("name")
                ).strip()
                if not query:
                    return ""
                return rag_service.build_context(
                    query, top_k=options.get("reference_count", 5)
                )

            rag_retriever = _rag_for_batch

        # 4. 用例生成
        self._progress(60, "case_generation")
        result.test_cases = self.generator.run(
            result.test_points,
            rag_context,
            priority_levels=options.get("priority_levels") or [],
            cases_per_point=options.get("case_multiplier") or 2,
            requirements=result.requirements,  # 需求原文依据：防生成器靠脑补臆想
            rag_retriever=rag_retriever,
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

        # 5.5 评审闭环（限 1 轮）：过去评审结果是"死数据"——发现问题但没人改。
        #     现在按 error 级 issues 修订对应用例 → 替换 → 复评一次，
        #     评审报告随之更新为修订后的结论，原始报告存入 first_review 留痕。
        self._revise_on_review(result, review_points, options)

        self._progress(100, "complete")
        return result

    # 修订的用例数上限：只改 error 级且截断，防上下文爆炸与大规模回归
    _MAX_REVISED_CASES = 20

    def _revise_on_review(self, result: WorkflowResult, review_points: list[dict], options: dict) -> None:
        """按评审 issues 修订用例并复评一次（失败静默降级，保持原用例与原评审）"""
        issues = result.review.get("issues") or []
        if not issues:
            return

        # 标题 -> (用例, [issues])：评审的 case_title 与用例 title 对齐（模糊匹配兜底）
        by_title: dict[str, dict] = {}
        for c in result.test_cases:
            t = str(c.get("title") or "").strip()
            if t:
                by_title[t] = c

        def _find_case(title: str) -> dict | None:
            t = str(title or "").strip()
            if not t:
                return None
            if t in by_title:
                return by_title[t]
            # 模糊兜底：互为包含即认为指向同一用例
            for k, c in by_title.items():
                if t in k or k in t:
                    return c
            return None

        flagged: dict[int, dict] = {}  # id(case) -> 组装好的待修订条目
        for it in issues:
            if str(it.get("level") or "").lower() != "error":
                continue  # warning 只提示不改动，控制改动面
            case = _find_case(it.get("case_title"))
            if case is None:
                continue
            entry = flagged.setdefault(
                id(case),
                {"original_title": case.get("title"), "issues": [], "_case": case},
            )
            entry["issues"].append(
                {"issue": it.get("issue"), "suggestion": it.get("suggestion")}
            )
        if not flagged:
            result.review["revision"] = "评审发现的问题均为 warning 级或未命中用例，未触发修订"
            return
        if len(flagged) > self._MAX_REVISED_CASES:
            result.review["revision"] = (
                f"error 级问题命中 {len(flagged)} 条用例，本轮仅修订最严重的前 {self._MAX_REVISED_CASES} 条，"
                "其余请参考评审报告人工修订"
            )
            flagged_items = list(flagged.values())[: self._MAX_REVISED_CASES]
        else:
            flagged_items = list(flagged.values())

        self._progress(92, "case_revision")
        requirement_refs = _build_requirement_refs(
            [tp for tp in result.test_points if tp.get("_req")], result.requirements
        )
        point_names = [str(tp.get("name") or "") for tp in review_points if tp.get("name")]
        try:
            revised = self.reviser.run(
                [
                    {"original_title": e["original_title"], "issues": e["issues"],
                     **{k: v for k, v in e["_case"].items() if k != "title"}}
                    for e in flagged_items
                ],
                point_names,
                requirement_refs,
            )
        except Exception:
            logger.warning("用例修订失败，保持原用例与原评审", exc_info=True)
            result.review["revision"] = "修订调用失败，保持原用例"
            return
        if not revised:
            result.review["revision"] = "修订未产出结果，保持原用例"
            return

        # 替换：按 original_title 对齐旧用例；discard=true 剔除；修订用例重走等级护栏
        replaced = 0
        removed_ids = {id(e["_case"]) for e in flagged_items}
        new_cases: list[dict] = []
        for c in revised:
            orig_title = str(c.pop("original_title", "") or "").strip()
            old = by_title.get(orig_title)
            if old is not None:
                removed_ids.add(id(old))
            if c.get("discard"):
                continue
            new_cases.append(c)
            replaced += 1
        kept = [c for c in result.test_cases if id(c) not in removed_ids]
        result.test_cases = kept + new_cases
        # 修订用例同样过等级规范（性能≥L3、L1 占比受控）
        self.generator._normalize_priorities(new_cases, result.test_points)
        # 用例集合有增删，覆盖率同步重算（原口径：预留需求不计入漏测）
        active_reqs2 = [r for r in result.requirements if not is_reserved_req(r)]
        result.coverage = build_coverage(active_reqs2, result.test_points, result.test_cases)

        # 复评一次（失败保持首轮评审，但用例已修订）
        first_review = dict(result.review)
        try:
            result.review = self.reviewer.run(result.test_cases, review_points)
            result.review["first_review"] = first_review
            result.review["revised"] = True
            result.review["revision"] = f"已按评审问题修订 {replaced} 条用例并复评"
        except Exception:
            logger.warning("复评失败，保留首轮评审报告", exc_info=True)
            first_review["revised"] = True
            first_review["revision"] = f"已修订 {replaced} 条用例，复评失败（报告为修订前结论）"
            result.review = first_review
