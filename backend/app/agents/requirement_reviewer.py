"""需求质量评审智能体：从"需求质量"视角评审需求文档，输出体检报告

复用需求解析与测试点提取结果，让 LLM 以"这份需求能不能直接进入开发/测试"为标准
评审，输出评分 + 问题清单（歧义/缺失边界/流程断点/异常未定义/隐式场景过多）。
这是把平台从"测试用例生成器"拓展为"研发质量前置工具"的关键出口——产品/研发
上传 PRD 即可拿到需求体检报告，在提测前发现需求缺陷，减少返工。
"""
import json
import logging
import re

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """你是资深的需求评审专家，正在对一份产品需求文档（PRD）做"提测前体检"。
目标：判断这份需求是否清晰、完整、可直接进入开发与测试，找出会导致后续返工的质量缺陷。

【需求清单】（已由系统解析提取，共 {req_count} 条）
{requirements}

【测试点提取统计】
- 测试点总数：{tp_count}
- 隐式场景（implicit）数量：{implicit_count}（隐式场景占比过高，说明需求未显式写清状态流转/流程时序/默认规则）
- 设计技术分布：{technique_dist}

【评审维度】请逐项检查并报告问题：
1. 歧义表述：需求描述含糊、一词多义、可被多种理解
2. 缺失边界：输入/状态/数值的边界值未定义（如长度上限、超时阈值、容量上限、重试次数）
3. 流程断点：业务流程步骤不连贯、缺少前置/后置、分支未覆盖
4. 异常未定义：错误场景、失败处理、网络异常、权限不足、超时等未说明
5. 隐式场景过多：某模块隐式场景占比高，说明需求描述不充分
6. 优先级/分类缺失或不当

【输出要求】严格输出以下 JSON（不要 markdown 代码块、不要解释文字）：
{{
  "score": 0到100的整数,
  "summary": "一句话总体评价",
  "issues": [
    {{"type": "歧义表述|缺失边界|流程断点|异常未定义|隐式场景过多|优先级不当",
      "description": "具体问题描述", "requirement": "关联的需求编号或名称(可空)",
      "severity": "高|中|低", "suggestion": "修改建议"}}
  ],
  "highlights": ["做得好的地方1", "做得好的地方2"]
}}
注意：issues 可为空数组（需求质量好时）；highlights 至少 1 条。"""


class RequirementReviewerAgent(BaseAgent):
    name = "requirement_reviewer"

    def run(self, requirements: list[dict], test_points: list[dict]) -> dict:
        """输入需求清单 + 测试点，输出体检报告 dict"""
        req_count = len(requirements)
        tp_count = len(test_points)
        implicit_count = sum(
            1 for t in test_points if (t.get("type") or "").lower() == "implicit"
        )
        technique_dist: dict[str, int] = {}
        for t in test_points:
            tk = t.get("technique") or "none"
            technique_dist[tk] = technique_dist.get(tk, 0) + 1

        req_text = "\n".join(
            f"{r.get('no', '')} | {r.get('name', '')} | {r.get('description', '')} | "
            f"优先级:{r.get('priority', '')} | 类别:{r.get('category', '')} | "
            f"流程:{r.get('business_flow', '')}"
            for r in requirements[:80]
        ) or "（未解析出需求）"

        prompt = REVIEW_PROMPT.format(
            req_count=req_count,
            requirements=req_text,
            tp_count=tp_count,
            implicit_count=implicit_count,
            technique_dist=json.dumps(technique_dist, ensure_ascii=False),
        )
        text = self.llm.chat(prompt, system=self.system_prompt, temperature=0.2)
        return self._parse_report(
            text, req_count, tp_count, implicit_count, technique_dist
        )

    @staticmethod
    def _parse_report(text, req_count, tp_count, implicit_count, technique_dist) -> dict:
        """容错解析 LLM 输出为报告 dict，解析失败时给出可用兜底"""
        report: dict = {
            "score": 0,
            "summary": "",
            "issues": [],
            "highlights": [],
            "metrics": {
                "requirement_count": req_count,
                "test_point_count": tp_count,
                "implicit_count": implicit_count,
                "technique_distribution": technique_dist,
            },
        }
        m = re.search(r"\{.*\}", text or "", re.S)
        if not m:
            report["summary"] = (text or "").strip()[:500] or "评审未返回有效结果，请重试"
            return report
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            report["summary"] = "评审结果解析失败，请重试"
            return report
        report["score"] = int(data.get("score") or 0)
        report["summary"] = (data.get("summary") or "").strip()
        report["issues"] = [
            i for i in (data.get("issues") or []) if isinstance(i, dict)
        ]
        report["highlights"] = [
            h for h in (data.get("highlights") or []) if isinstance(h, str)
        ]
        return report
