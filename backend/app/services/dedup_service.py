"""用例重复扫描服务: 识别并标注同一批次内【同义重复】的用例（只标注，不删除）

流程:
1) 候选召回: 同模块内用字符 n-gram 近似两两比对，合并出疑似重复的候选组
   （bigram 只能高效筛掉大量无关对，把真正可疑的小集合交给 LLM，避免全量两两调 LLM）
2) LLM 精判: 对每个候选组用 LLM 判定真实重复组、每组应保留的代表用例与原因
3) 结构化标注: 把"组号/代表/原因"以【疑似重复】行写入 ai_remark，同时写入结构化字段
   dup_group_no / dup_keep_case_id（供批量清理时按组保留代表、删除冗余）；
   保留原有 AI 自查备注行；重复执行扫描时会先清除旧的【疑似重复】标记与结构化字段
   再重写，保证结果与当次扫描一致

配合批量清理:
   cleanup_duplicates 以结构化字段为依据，每组只保留代表用例（dup_keep_case_id
   指向的用例），删除其余冗余；对被人工反馈 good 的冗余用例会跳过并提示。
"""
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.case_dedup_checker import CaseDedupCheckerAgent
from app.agents.requirement_matching import ngrams
from app.core.exceptions import BusinessError
from app.models.test_case import TestCase, TestCaseVersion
from app.models.test_script import TestScript

logger = logging.getLogger(__name__)

# 候选召回阈值：单向覆盖 >= _CAND_MAX 且双向覆盖 >= _CAND_MIN 判为疑似
_CAND_MAX = 0.65
_CAND_MIN = 0.4
# 一次交给 LLM 精判的候选成员上限
_GROUP_CHUNK = 15
# 标注原因的最长长度
_MAX_REASON = 100
# 成员编号展示数量上限（避免单条备注过长）
_MAX_MEMBERS_SHOWN = 6


def _case_text(c: TestCase) -> str:
    actions = []
    for s in c.steps or []:
        if isinstance(s, dict) and str(s.get("action") or "").strip():
            actions.append(str(s["action"]).strip())
    return " ".join(
        [
            str(c.title or ""),
            str(c.module or ""),
            str(c.preconditions or ""),
            " / ".join(actions),
            str(c.expected_result or ""),
        ]
    )


def _similar(a: str, b: str) -> bool:
    ga, gb = ngrams(a), ngrams(b)
    if not ga or not gb:
        return False
    inter = len(ga & gb)
    ab, ba = inter / len(ga), inter / len(gb)
    return max(ab, ba) >= _CAND_MAX and min(ab, ba) >= _CAND_MIN


def _build_candidates(cases: list[TestCase]) -> list[list[TestCase]]:
    """同模块内 bigram 近似两两合并（传递闭包）得到候选组，单成员组剔除"""
    buckets: dict[str, list[TestCase]] = {}
    for c in cases:
        buckets.setdefault(str(c.module or "").strip() or "通用", []).append(c)

    parent = {c.id: c.id for c in cases}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    cache = {c.id: _case_text(c) for c in cases}
    for bucket in buckets.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                if _similar(cache[bucket[i].id], cache[bucket[j].id]):
                    union(bucket[i].id, bucket[j].id)

    groups: dict[int, list[TestCase]] = {}
    for c in cases:
        groups.setdefault(find(c.id), []).append(c)
    return [members for members in groups.values() if len(members) > 1]


def _member_block(c: TestCase) -> str:
    actions = []
    for s in c.steps or []:
        if isinstance(s, dict) and str(s.get("action") or "").strip():
            actions.append(str(s["action"]).strip())
    steps_txt = " → ".join(actions)
    return (
        f"[code={c.id}]\n"
        f"用例号: {c.case_no}｜标题: {c.title or ''}\n"
        f"模块: {c.module or ''}｜类型: {c.test_type or ''}｜用例等级: {c.priority or ''}\n"
        f"前置: {c.preconditions or ''}\n"
        f"步骤: {steps_txt or '（无）'}\n"
        f"预期: {c.expected_result or ''}"
    )


def _clear_dup_marker(remark: str | None) -> str | None:
    """去掉 ai_remark 中旧的【疑似重复】行，保留 AI 自查等其它备注行"""
    if not remark:
        return None
    lines = [ln for ln in remark.splitlines() if not ln.startswith("【疑似重复")]
    return "\n".join(lines) or None


def _append_dup_marker(c: TestCase, text: str) -> None:
    remark = c.ai_remark
    c.ai_remark = (remark + "\n" if remark else "") + text


def scan_duplicates(
    db: Session,
    *,
    task_id: int | None = None,
    case_ids: list[int] | None = None,
) -> dict:
    """执行重复扫描并落标注，返回统计结果

    :return: {"scanned": 扫描条数, "groups": 判定出的重复组数,
              "flagged": 被标注为重复的条数, "failed_batches": 精判失败的批次数}
    """
    if not task_id and not case_ids:
        raise BusinessError("请指定生成任务或选择待扫描的用例")

    q = db.query(TestCase)
    if task_id:
        q = q.filter(TestCase.task_id == task_id)
    else:
        q = q.filter(TestCase.id.in_(case_ids))
    cases = q.order_by(TestCase.id.asc()).all()
    if not cases:
        raise BusinessError("未找到可扫描的用例")

    # 先清除当次范围内旧的重复标注与结构化字段（幂等，结果与当次扫描一致）
    for c in cases:
        c.ai_remark = _clear_dup_marker(c.ai_remark)
        c.dup_group_no = None
        c.dup_keep_case_id = None
    db.commit()

    if len(cases) == 1:
        return {"scanned": 1, "groups": 0, "flagged": 0, "failed_batches": 0}

    candidate_groups = _build_candidates(cases)
    agent = CaseDedupCheckerAgent()
    groups_found = 0
    flagged = 0
    failed_batches = 0
    group_seq = 0
    first_error: Exception | None = None

    for members in candidate_groups:
        for i in range(0, len(members), _GROUP_CHUNK):
            sub = members[i : i + _GROUP_CHUNK]
            try:
                result = agent.run([_member_block(m) for m in sub]) or {}
                raw_groups = result.get("groups") or []
            except Exception as e:  # noqa: BLE001 - 单组失败不中断整体扫描
                db.rollback()
                failed_batches += 1
                logger.warning("[dedup] 候选组精判失败: %s", e)
                if first_error is None:
                    first_error = e
                continue

            by_code = {m.id: m for m in sub}
            for g in raw_groups:
                if not isinstance(g, dict):
                    continue
                try:
                    codes = [int(x) for x in (g.get("codes") or []) if str(x).strip().isdigit()]
                except (TypeError, ValueError):
                    continue
                codes = sorted({x for x in codes if x in by_code})
                if len(codes) < 2:
                    continue
                try:
                    keep = int(g.get("keep"))
                except (TypeError, ValueError):
                    keep = codes[0]
                if keep not in codes:
                    keep = codes[0]
                reason = str(g.get("reason") or "与代表用例操作路径及预期本质相同")[:_MAX_REASON]
                group_seq += 1
                keep_case = by_code[keep]
                redundants = [x for x in codes if x != keep]
                member_no = "、".join(str(by_code[x].case_no) for x in codes[:_MAX_MEMBERS_SHOWN])
                if len(codes) > _MAX_MEMBERS_SHOWN:
                    member_no += f" 等{len(codes)}条"
                marker = (
                    f"【疑似重复·组{group_seq}】本组{len(codes)}条（{member_no}）被测对象与操作预期"
                    f"重复，建议保留 {by_code[keep].case_no}，本组其余可删除（原因：{reason}；请人工复核）"
                )
                for code in redundants:
                    dup_case = by_code[code]
                    _append_dup_marker(dup_case, marker)
                    dup_case.dup_group_no = group_seq
                    dup_case.dup_keep_case_id = keep_case.id
                    flagged += 1
                groups_found += 1
            db.commit()

    if groups_found == 0 and failed_batches > 0:
        raise BusinessError(f"重复扫描全部失败，请稍后重试。{first_error}")

    return {
        "scanned": len(cases),
        "groups": groups_found,
        "flagged": flagged,
        "failed_batches": failed_batches,
    }


def cleanup_duplicates(
    db: Session,
    *,
    task_id: int | None = None,
    case_ids: list[int] | None = None,
    dry_run: bool = True,
) -> dict:
    """按结构化标注清理重复用例：每组保留代表用例，删除其余冗余。

    - 只在用例带 dup_group_no（被扫描标为疑似重复）时才会进入删除候选；
    - 每组保留 dup_keep_case_id 指向的代表用例（天然不带 dup_group_no）；
    - 被人工反馈 good 的冗余用例跳过删除，避免误删高评价用例；
    - dry_run=True 只统计不落库，供前端预览确认。

    :return: {"groups": 生效重复组数, "keep_count": 保留代表数,
              "deleted": 将删/已删条数, "skipped_good": 因 good 跳过的条数,
              "groups_detail": 按组的明细, "dry_run": bool}
    """
    if not task_id and not case_ids:
        raise BusinessError("请指定生成任务或选择待清理的用例")

    q = db.query(TestCase)
    if task_id:
        q = q.filter(TestCase.task_id == task_id)
    else:
        q = q.filter(TestCase.id.in_(case_ids))
    cases = q.order_by(TestCase.id.asc()).all()
    if not cases:
        raise BusinessError("未找到可清理的用例")

    dups = [c for c in cases if c.dup_group_no is not None]
    if not dups:
        return {
            "groups": 0,
            "keep_count": 0,
            "deleted": 0,
            "skipped_good": 0,
            "groups_detail": [],
            "dry_run": dry_run,
        }

    # 按 (组号, 保留代表) 聚合；一个组只会有一个 keep，故每条冗余都属唯一键
    group_rows: dict[tuple, list[TestCase]] = {}
    for c in dups:
        group_rows.setdefault((c.dup_group_no, c.dup_keep_case_id), []).append(c)

    keep_ids = {c.dup_keep_case_id for c in dups if c.dup_keep_case_id}
    keep_rows = {}
    if keep_ids:
        keep_rows = {k.id: k for k in db.query(TestCase).filter(TestCase.id.in_(keep_ids)).all()}

    to_delete: list[TestCase] = []
    skipped_good: list[TestCase] = []
    groups_detail: list[dict] = []
    for (group_no, keep_id), members in group_rows.items():
        keep = keep_rows.get(keep_id)
        delete_members: list[TestCase] = []
        for m in members:
            if m.feedback == "good":
                skipped_good.append(m)
            else:
                delete_members.append(m)
                to_delete.append(m)
        if delete_members:
            groups_detail.append(
                {
                    "group_no": group_no,
                    "keep": {
                        "id": keep.id if keep else None,
                        "case_no": keep.case_no if keep else None,
                        "title": keep.title if keep else None,
                    },
                    "delete_count": len(delete_members),
                    "delete_codes": [m.case_no for m in delete_members],
                }
            )

    deleted = len(to_delete)
    result = {
        "groups": len(groups_detail),
        "keep_count": len(groups_detail),
        "deleted": deleted,
        "skipped_good": len(skipped_good),
        "groups_detail": groups_detail,
        "dry_run": dry_run,
    }
    if dry_run or not to_delete:
        return result

    delete_ids = [c.id for c in to_delete]
    db.execute(delete(TestCaseVersion).where(TestCaseVersion.case_id.in_(delete_ids)))
    db.execute(delete(TestScript).where(TestScript.case_id.in_(delete_ids)))
    db.execute(delete(TestCase).where(TestCase.id.in_(delete_ids)))
    db.commit()
    logger.info("[dedup-cleanup] 已清理重复用例 %s 条（%s 个组，跳过 good %s 条）",
                deleted, len(groups_detail), len(skipped_good))
    return result


# ============================================================
# 入库前防重（生成阶段）：新用例写库前先与库内已有用例做“操作路径近似”比对，
# 高度相似的不再入库，避免同一批/同一文档反复生成时把重复内容写进库。
# 只做基于文本 n-gram 的强相似拦截（保守阈值，避免误杀真实变体）；
# 措辞不同但语义相同的漏网用例仍由收尾的 auto_dedup 扫描标注、一键清理兜底。
# ============================================================

def dedup_text(preconditions, steps, expected_result) -> str:
    """生成阶段防重用的用例文本表示：
    只取【前置条件 + 步骤动作 + 预期结果】，不含标题与模块名，
    聚焦“操作路径/断言”，避免标题措辞不同导致同路径用例被放行。
    """
    actions: list[str] = []
    for s in steps or []:
        if isinstance(s, dict) and str(s.get("action") or "").strip():
            actions.append(str(s["action"]).strip())
    return " ".join(
        [
            str(preconditions or ""),
            " / ".join(actions),
            str(expected_result or ""),
        ]
    )


class PreSaveDedupIndex:
    """写库前防重索引（按模块分桶的 bigram 倒排）。

    用法:
        index.add(module, text)                  # 每成功保存一条后登记
        hit = index.find_duplicate(module, text) # 高度近似则返回已存文本片段，否则 None

    相似判定: 双向 bigram 覆盖率 max>=0.90 且 min>=0.75（保守，专抓“逐字雷同”类重复）。
    """

    MAX_COVERAGE = 0.90  # 较长文本中近似重复占比下限
    MIN_COVERAGE = 0.75  # 较短文本中近似重复占比下限

    @staticmethod
    def _bucket(module) -> str:
        return str(module or "").strip() or "通用"

    def __init__(self) -> None:
        self._texts: dict[str, list[str]] = {}
        self._grams: dict[str, list[set[str]]] = {}
        self._inverted: dict[str, dict[str, list[int]]] = {}

    def add(self, module, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        bucket = self._bucket(module)
        idx = len(self._texts.setdefault(bucket, []))
        gram = ngrams(text)
        self._grams.setdefault(bucket, []).append(gram)
        self._texts[bucket].append(text)
        inv = self._inverted.setdefault(bucket, {})
        for g in gram:
            inv.setdefault(g, []).append(idx)

    def find_duplicate(self, module, text: str, max_cov: float = None, min_cov: float = None) -> str | None:
        """返回与 text 高度近似的已存文本片段（前若干字符），无则 None。"""
        max_cov = self.MAX_COVERAGE if max_cov is None else max_cov
        min_cov = self.MIN_COVERAGE if min_cov is None else min_cov
        text = (text or "").strip()
        if not text:
            return None
        bucket = self._bucket(module)
        texts = self._texts.get(bucket)
        if not texts:
            return None
        grams = self._grams[bucket]
        inv = self._inverted.get(bucket)
        query_gram = ngrams(text)
        if not query_gram:
            return None

        # 倒排粗筛：只对共享 bigram 够多的已存文本做精确双向覆盖判定
        scores: dict[int, int] = {}
        for g in query_gram:
            for idx in inv.get(g, ()):  # 倒排中同一 (g,idx) 不会重复，cnt=|交集|
                scores[idx] = scores.get(idx, 0) + 1
        thr = max(int(len(query_gram) * min_cov), 2)
        for idx, cnt in scores.items():
            if cnt < thr:
                continue
            other = grams[idx]
            if not other:
                continue
            ab = cnt / len(query_gram)
            ba = cnt / len(other)
            if max(ab, ba) >= max_cov and min(ab, ba) >= min_cov:
                return texts[idx]
        return None


def build_project_index(db: Session, project_id: int) -> PreSaveDedupIndex:
    """把项目内已有用例（只读 module/steps 等判定所需字段）登记为防重索引。
    应放在 replace_existing 清理之后调用，避免把将被覆盖的旧内容当“已存在”。
    """
    index = PreSaveDedupIndex()
    rows = db.execute(
        select(
            TestCase.module,
            TestCase.preconditions,
            TestCase.steps,
            TestCase.expected_result,
        ).where(TestCase.project_id == project_id)
    ).all()
    for module, preconditions, steps, expected_result in rows:
        index.add(module, dedup_text(preconditions, steps, expected_result))
    return index

