"""LangGraph 状态图版工作流（可选生产方案）

MVP 使用 workflow.py 的顺序流水线，本文件为 LangGraph 版参考实现。
当 langgraph 依赖与生产环境就绪后，可直接替换 workflow.py 中的 GenerateWorkflow。

注意：本文件为可选参考实现，未安装 langgraph 时不会影响系统运行。
使用前需执行: pip install langgraph
"""
from typing import TypedDict

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - 可选依赖
    END = None
    StateGraph = None

from app.agents.requirement_parser import RequirementParserAgent
from app.agents.test_case_generator import TestCaseGeneratorAgent
from app.agents.test_case_reviewer import TestCaseReviewerAgent
from app.agents.test_point_extractor import TestPointExtractorAgent
from app.services.rag_service import rag_service


class WorkflowState(TypedDict):
    content: str
    options: dict
    requirements: list
    test_points: list
    rag_context: str
    test_cases: list
    review: dict


class LangGraphWorkflow:
    def __init__(self):
        self.parser = RequirementParserAgent()
        self.extractor = TestPointExtractorAgent()
        self.generator = TestCaseGeneratorAgent()
        self.reviewer = TestCaseReviewerAgent()
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(WorkflowState)

        def parse(state: WorkflowState):
            return {"requirements": self.parser.run(state["content"])}

        def extract(state: WorkflowState):
            return {"test_points": self.extractor.run(state["requirements"])}

        def retrieve(state: WorkflowState):
            ctx = ""
            if state.get("options", {}).get("enable_rag", True):
                ctx = rag_service.build_context(state["content"][:500])
            return {"rag_context": ctx}

        def generate(state: WorkflowState):
            return {"test_cases": self.generator.run(state["test_points"], state["rag_context"])}

        def review(state: WorkflowState):
            return {"review": self.reviewer.run(state["test_cases"], state["test_points"])}

        g.add_node("parse", parse)
        g.add_node("extract", extract)
        g.add_node("retrieve", retrieve)
        g.add_node("generate", generate)
        g.add_node("review", review)

        g.set_entry_point("parse")
        g.add_edge("parse", "extract")
        g.add_edge("extract", "retrieve")
        g.add_edge("retrieve", "generate")
        g.add_edge("generate", "review")
        g.add_edge("review", END)
        return g.compile()

    def run(self, content: str, options: dict | None = None) -> dict:
        result = self.graph.invoke({"content": content, "options": options or {}})
        return result
