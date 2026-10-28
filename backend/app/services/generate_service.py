"""用例生成任务服务

任务创建后进入 pending，由后台线程执行智能体工作流，
进度通过 task 表 progress 字段持久化，前端通过 SSE/轮询获取。
"""
import logging
import threading
import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.agents.workflow import GenerateWorkflow
from app.core.exceptions import BusinessError, NotFoundError
from app.database import SessionLocal
from app.models.document import Document
from app.models.generation_task import GenerationTask
from app.models.test_case import TestCase, TestCaseVersion
from app.models.test_point import TestPoint
from app.models.test_script import TestScript
from app.models.user import User
from app.services import notification_service
from app.services.case_quality import build_remark
from app.services.dedup_service import PreSaveDedupIndex, build_project_index, dedup_text
from app.services.document_service import parse_document
from app.services.test_case_service import save_generated_case

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 平台自身功能关键词（兜底拦截 AI 误生成的平台功能，避免混入产品用例）。
# 注意：该兜底拦截已取消。原因：关键词拦截会把真实业务需求误判为"平台功能"而
# 过滤掉（如"登录注册"相关需求曾被抑制，导致苹果/谷歌第三方登录用例缺失）。
# 平台功能混入的根本问题是选错文档，应由文档选择与 prompt 约束保证，而非关键词
# 兜底过滤。如需恢复过滤，将 _is_platform_feature 恢复为关键词匹配逻辑即可。
# ---------------------------------------------------------------------------
PLATFORM_FEATURE_KEYWORDS = (
    "需求管理", "需求列表", "需求评审", "需求导入", "需求跟踪", "需求编号",
    "用例管理", "用例评审", "测试用例平台", "用例库", "用例执行",
    "文档解析", "文档上传", "知识库", "向量检索",
    "审计日志", "操作日志", "租户", "多租户", "数据隔离",
    "项目管理", "项目成员", "项目列表", "项目归档", "项目导出", "项目导入",
    "公告管理", "用户权限管理", "系统访问控制", "接口访问控制",
    "数据备份", "数据迁移", "数据库连接", "系统部署", "敏感数据脱敏",
    "模板管理", "消息模板", "报表导出", "基线评审", "评审管理", "评审意见",
    "通知管理", "系统帮助", "用户信息管理", "操作审计", "并发用户", "附件管理",
)


def _is_platform_feature(*texts) -> bool:
    """平台功能拦截已取消，恒返回 False，测试点/用例全部保留，不再做兜底过滤"""
    return False


# 全新项目（无任何历史提取记录）时的估算密度：每字符约产出的测试点数。
# 依据历史真实数据（如 4577 字符 → 69 测试点的特制高密度文档）取保守值，
# 宁可低估避免误导用户"会生成太多"。有历史记录时会用真实比例自动替代。
DEFAULT_POINTS_PER_CHAR = 0.008


def estimate_cases(db: Session, project_id: int, document_ids: list[int]) -> dict:
    """生成前用例量预估（纯 DB 查询，不解析不调 LLM）

    预估策略（对每个文档）：
    1. 该文档在该项目已有测试点（历史生成过）→ 用真实测试点数，最准；
    2. 无历史但解析完成 → 按本项目历史"测试点数/文档总字符"密度粗估；
       项目从未生成过 → 按全局默认密度 DEFAULT_POINTS_PER_CHAR 粗估；
    3. 未解析完成的文档不计入（前端提示预估偏低）。

    预估总用例数 = Σ测试点 × 用户所选倍数（倍数由前端乘算展示）。
    """
    docs = db.scalars(
        select(Document).where(
            Document.id.in_(document_ids), Document.project_id == project_id
        )
    ).all()
    if not docs:
        raise NotFoundError("未找到所选文档")

    # 各文档历史真实测试点数（同项目下）
    doc_counts = dict(
        db.execute(
            select(TestPoint.document_id, func.count(TestPoint.id))
            .where(
                TestPoint.project_id == project_id,
                TestPoint.document_id.in_([d.id for d in docs]),
            )
            .group_by(TestPoint.document_id)
        ).all()
    )

    # 项目级历史密度：全部历史测试点数 / 全部已解析文档总字符数
    proj_points = db.scalar(
        select(func.count(TestPoint.id)).where(TestPoint.project_id == project_id)
    ) or 0
    proj_chars = 0
    for d in db.scalars(select(Document).where(Document.project_id == project_id)).all():
        if d.parse_status == "done":
            proj_chars += int((d.parse_result or {}).get("chars") or 0)
    ratio = (proj_points / proj_chars) if proj_chars > 0 else DEFAULT_POINTS_PER_CHAR

    items = []
    est_points = 0
    unparsed = 0
    for d in docs:
        chars = int((d.parse_result or {}).get("chars") or 0) if d.parse_status == "done" else 0
        existing = doc_counts.get(d.id, 0)
        if chars <= 0:
            unparsed += 1
        if existing > 0:
            est_pt = existing
        elif chars > 0:
            # 无历史时按密度粗估（至少 2 个，避免小文档估成 0）
            est_pt = max(2, int(chars * ratio))
        else:
            est_pt = 0
        est_points += est_pt
        items.append(
            {
                "id": d.id,
                "title": d.title,
                "chars": chars,
                "existing_points": existing,
                "estimated_points": est_pt,
            }
        )

    return {
        "documents": items,
        "est_points": est_points,
        "unparsed": unparsed,
        "has_history": proj_points > 0,
    }


def _match_test_point(tp_map: dict, name: str) -> TestPoint | None:
    """按测试点名称匹配用例归属：先精确匹配，再包含匹配（避免模型输出微差导致挂空）"""
    if not name:
        return None
    if name in tp_map:
        return tp_map[name]
    for key, point in tp_map.items():
        if len(key) >= 3 and len(name) >= 3 and (key in name or name in key):
            return point
    return None


def _req_block(req: dict | None) -> str | None:
    """把配对到的需求原文整理成带标签文本，作为用例生成依据(req_ref)落库"""
    if not req:
        return None
    no = str(req.get("no") or "").strip()
    name = str(req.get("name") or "").strip()
    desc = str(req.get("description") or "").strip()
    flow = str(req.get("business_flow") or "").strip()
    header = f"[需求 {no}] {name}".strip()
    lines = [header]
    if desc:
        lines.append(f"需求描述: {desc}")
    if flow:
        lines.append(f"业务流程: {flow}")
    return "\n".join(lines) if len(lines) > 1 else None


def _match_req_ref(req_map: dict, name: str) -> str | None:
    """按测试点名称匹配到该测试点所依据的需求原文(req_ref)，用于落库"""
    if not name or not req_map:
        return None
    if name in req_map:
        return req_map[name]
    for key, ref in req_map.items():
        if len(key) >= 3 and len(name) >= 3 and (key in name or name in key):
            return ref
    return None


def _gen_task_no() -> str:
    return f"GEN-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"


def create_task(db: Session, project_id: int, document_ids: list[int], options: dict, user_id: int) -> GenerationTask:
    """创建生成任务（document_ids 一并写入 options 以支持重试/重启恢复）"""
    task = GenerationTask(
        task_no=_gen_task_no(),
        project_id=project_id,
        document_id=document_ids[0],
        created_by=user_id,
        status="pending",
        progress=0,
        options={**(options or {}), "document_ids": document_ids},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _notify_task_done(db: Session, task: GenerationTask, user_id: int) -> None:
    """任务完成/失败后发送站内通知"""
    user = db.get(User, user_id)
    if not user:
        return
    if task.status == "success":
        notification_service.create_notification(
            db,
            user_id,
            category="task",
            title="用例生成任务完成",
            content=f"任务 {task.task_no} 已成功生成 {task.total_case} 条用例",
            related_id=task.id,
        )
    elif task.status == "failed":
        notification_service.create_notification(
            db,
            user_id,
            category="task",
            title="用例生成任务失败",
            content=f"任务 {task.task_no} 生成失败：{task.error_msg or '未知错误'}",
            related_id=task.id,
        )


def _run_workflow(task_id: int, document_ids: list[int], options: dict, user_id: int) -> None:
    """后台执行工作流（独立数据库会话）"""
    db = SessionLocal()
    try:
        task = db.get(GenerationTask, task_id)
        if not task:
            return
        task.status = "running"
        task.started_at = datetime.now()
        db.commit()

        # 解析所有关联文档（携带文档 id，保证测试点归属正确）
        # 解析阶段占用进度 0~10%，逐文档推进，避免多图文档长时间无进度被误判"卡死"
        contents: list[tuple[int, str]] = []
        total_docs = len(document_ids)
        for idx, doc_id in enumerate(document_ids, start=1):
            task.progress = min(10, int(idx / total_docs * 10)) if total_docs else 10
            db.commit()
            doc, text = parse_document(db, doc_id)
            if text:
                contents.append((doc_id, f"【文档：{doc.title}】\n{text}"))
        task.progress = 10
        db.commit()

        # 覆盖重建（replace_existing）：先清空所选文档名下旧测试点与用例，
        # 防止历史幻象点/旧数据残留累积。仅在解析成功后执行，失败则保留旧数据。
        if options.get("replace_existing"):
            for doc_id in document_ids:
                point_ids = select(TestPoint.id).where(
                    TestPoint.project_id == task.project_id, TestPoint.document_id == doc_id
                )
                case_ids = select(TestCase.id).where(TestCase.test_point_id.in_(point_ids))
                db.execute(delete(TestCaseVersion).where(TestCaseVersion.case_id.in_(case_ids)))
                db.execute(delete(TestScript).where(TestScript.case_id.in_(case_ids)))
                db.execute(delete(TestCase).where(TestCase.test_point_id.in_(point_ids)))
                db.execute(delete(TestPoint).where(TestPoint.document_id == doc_id))
            db.commit()

        total_case = 0
        generated_cases: list[dict] = []
        reviews: list[dict] = []
        business_flows: list[dict] = []
        qualities: list[dict] = []
        coverages: list[dict] = []
        error_msg = None

        def progress_cb(percent: int, stage: str):
            task = db.get(GenerationTask, task_id)
            task.progress = percent
            db.commit()

        # 幂等去重：加载项目内已有测试点名称与用例标题，防止重复任务/跨文档生成重复数据
        existing_point_names: set[str] = set(
            n for (n,) in db.execute(
                select(TestPoint.name).where(TestPoint.project_id == task.project_id)
            ).all() if n
        )
        existing_case_titles: set[str] = set(
            t for (t,) in db.execute(
                select(TestCase.title).where(TestCase.project_id == task.project_id)
            ).all() if t
        )
        # 入库前防重（生成阶段）：以项目内已有用例为底档，登记“前置+操作路径+预期”的
        # 模块级近似索引；后续每条候选写库前先比对，高度相似的不再写入库。
        # （options.dedup_on_generate=false 时关闭本能力）
        dedup_guard: PreSaveDedupIndex | None = None
        if bool(options.get("dedup_on_generate", True)):
            dedup_guard = build_project_index(db, task.project_id)
        dedup_skipped = 0
        dedup_skip_examples: list[str] = []

        for doc_id, text in contents:
            workflow = GenerateWorkflow(progress_cb=progress_cb)
            result = workflow.run(text, options)
            if result.quality:
                qualities.append(result.quality)
            if result.coverage:
                coverages.append(result.coverage)
            # 汇总业务流程（FR-1.4）
            for r in result.requirements:
                flow = (r.get("business_flow") or "").strip()
                if flow:
                    business_flows.append({"no": r.get("no"), "name": r.get("name"), "flow": flow})
            # 汇总评审结果（FR-5）
            if result.review:
                reviews.append(result.review)
            # 测试点入库（兜底拦截平台自身功能，避免混入产品测试点）
            test_points_in_db: list[TestPoint] = []
            for tp in result.test_points:
                if _is_platform_feature(tp.get("name"), tp.get("description")):
                    continue
                name = (tp.get("name") or "").strip() or "未命名测试点"
                # 项目内已有同名测试点时复用，避免重复堆积
                if name in existing_point_names:
                    continue
                point = TestPoint(
                    document_id=doc_id,
                    project_id=task.project_id,
                    name=name,
                    type=tp.get("type", "function"),
                    technique=tp.get("technique") or "none",
                    description=tp.get("description"),
                )
                db.add(point)
                db.commit()
                db.refresh(point)
                existing_point_names.add(name)
                test_points_in_db.append(point)
            # 测试点名称 -> 对象映射，供用例按名称匹配挂接。
            # 需并入该文档已有测试点：同名点在入库阶段被复用（不新建），若不入表
            # 用例会匹配不到而挂空(test_point_id=NULL)，导致覆盖率统计失真。
            test_point_map: dict = {
                p.name: p
                for p in db.scalars(
                    select(TestPoint).where(
                        TestPoint.project_id == task.project_id,
                        TestPoint.document_id == doc_id,
                    )
                ).all()
            }
            test_point_map.update({p.name: p for p in test_points_in_db})
            # 测试点名称 -> 需求原文依据(req_ref)映射，供用例落库记录"生成依据"
            req_map: dict[str, str] = {}
            for tp in result.test_points:
                tp_name = (tp.get("name") or "").strip()
                ref = _req_block(tp.get("_req"))
                if tp_name and ref:
                    req_map.setdefault(tp_name, ref)

            # 用例入库（兜底拦截平台功能；按 test_point 名称匹配挂接测试点，
            # 匹配不到时挂空(NULL)而非轮询错配，避免污染覆盖率统计）
            for case in result.test_cases:
                if _is_platform_feature(case.get("module"), case.get("title"), case.get("test_point")):
                    continue
                title = str(case.get("title") or "").strip()
                # 标题已在项目内存在（含本批已生成）则跳过，避免重复
                if title and title in existing_case_titles:
                    continue
                # 入库前文本近似防重：与库内已有用例（同模块）操作路径高度近似则不入库
                module = str(case.get("module") or "").strip()
                dup_text = ""
                if dedup_guard is not None:
                    dup_text = dedup_text(
                        case.get("preconditions"),
                        case.get("steps") or [],
                        case.get("expected_result"),
                    )
                    dup_hit = dedup_guard.find_duplicate(module, dup_text) if dup_text else None
                    if dup_hit:
                        dedup_skipped += 1
                        if len(dedup_skip_examples) < 3:
                            dedup_skip_examples.append(f"{title}≈已有「{dup_hit[:60]}」")
                        continue
                point_name = str(case.get("test_point") or "").strip()
                point = _match_test_point(test_point_map, point_name)
                point_id = point.id if point else None
                saved = save_generated_case(
                    db,
                    task.project_id,
                    case,
                    point_id,
                    user_id,
                    task_id=task.id,
                    req_ref=_match_req_ref(req_map, point_name),
                    ai_remark=build_remark(case.get("_quality") or []) or None,
                )
                if title:
                    existing_case_titles.add(title)
                if dedup_guard is not None and dup_text:
                    dedup_guard.add(module, dup_text)
                generated_cases.append(
                    {"case_id": saved.id, "title": saved.title, "priority": saved.priority}
                )
                total_case += 1

        # 聚合评审汇总（FR-5.2 评审结果展示）
        review_summary: dict = {
            "overall_score": 0,
            "issues": [],
            "missing_coverage": [],
            "doc_reviews": [],
        }
        if reviews:
            scores = [r.get("overall_score") or 0 for r in reviews if isinstance(r.get("overall_score"), (int, float))]
            review_summary["overall_score"] = round(sum(scores) / len(scores), 1) if scores else 0
            for r in reviews:
                for it in (r.get("issues") or [])[:30]:
                    review_summary["issues"].append(it)
                for it in (r.get("missing_coverage") or [])[:15]:
                    if it not in review_summary["missing_coverage"]:
                        review_summary["missing_coverage"].append(it)
                review_summary["doc_reviews"].append(
                    {
                        "overall_score": r.get("overall_score", 0),
                        "conclusion": r.get("conclusion", ""),
                    }
                )

        # 质量校验汇总：多文档任务把各文档的扫描结果合并，
        # 使"预期结果模糊率"成为任务级可观测指标，而非只散落在评审文本中
        q_total = sum(q.get("total") or 0 for q in qualities)
        q_flagged = sum(q.get("flagged") or 0 for q in qualities)
        quality_summary = {
            "total": q_total,
            "flagged": q_flagged,
            "rate": round(q_flagged / q_total, 4) if q_total else 0.0,
        }

        # 覆盖追溯汇总：合并各文档的需求/测试点覆盖计数，并给出零覆盖清单。
        # 早期"查看覆盖率"按全项目口径统计，历史用例会把本次新测试点"洗白"成
        # 已覆盖，指标长期虚高、漏测不可见；此处严格按本次任务产出计算。
        cov_pt = sum(c.get("point_total") or 0 for c in coverages)
        cov_pt_ok = sum(c.get("point_covered") or 0 for c in coverages)
        cov_rq = sum(c.get("requirement_total") or 0 for c in coverages)
        cov_rq_ok = sum(c.get("requirement_covered") or 0 for c in coverages)
        uncovered_points: list[str] = []
        uncovered_requirements: list[str] = []
        for c in coverages:
            uncovered_points.extend(c.get("uncovered_points") or [])
            uncovered_requirements.extend(c.get("uncovered_requirements") or [])
        coverage_summary = {
            "point_total": cov_pt,
            "point_covered": cov_pt_ok,
            "point_rate": round(cov_pt_ok / cov_pt, 4) if cov_pt else 0.0,
            "requirement_total": cov_rq,
            "requirement_covered": cov_rq_ok,
            "requirement_rate": round(cov_rq_ok / cov_rq, 4) if cov_rq else 0.0,
            "uncovered_points": uncovered_points[:50],
            "uncovered_requirements": uncovered_requirements[:50],
        }

        task.total_case = total_case
        task.status = "success"
        task.progress = 100
        task.result_summary = {
            "total_case": total_case,
            "dedup_skipped": dedup_skipped,
            "dedup_skip_examples": dedup_skip_examples[:10],
            "generated_cases": generated_cases[:200],
            "document_count": len(contents),
            "review": review_summary,
            "quality": quality_summary,
            "coverage": coverage_summary,
            "business_flows": business_flows[:30],
            "finished_at": datetime.now().isoformat(),
        }
        task.finished_at = datetime.now()
        db.commit()

        # 收尾：对本批生成结果自动执行一次重复扫描标注（options.auto_dedup 可关闭）。
        # 只标注不删除；若失败只记录到 result_summary，不影响任务成功状态。
        auto_dedup_result: dict | None = None
        if bool(options.get("auto_dedup", True)) and total_case > 1:
            try:
                from app.services import dedup_service

                auto_dedup_result = dedup_service.scan_duplicates(db, task_id=task.id)
            except Exception as e:  # noqa: BLE001 - 自动扫描失败不推翻生成结果
                logger.warning("[auto-dedup] 本批自动重复扫描失败: %s", e)
                auto_dedup_result = {"error": str(e)}
            try:
                task = db.get(GenerationTask, task_id)
                if task and auto_dedup_result is not None:
                    summary = dict(task.result_summary or {})
                    summary["auto_dedup"] = auto_dedup_result
                    task.result_summary = summary
                    db.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning("[auto-dedup] 回写自动扫描结果失败: %s", e)
                db.rollback()
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        task = db.get(GenerationTask, task_id)
        if task:
            task.status = "failed"
            task.error_msg = str(e)
            task.finished_at = datetime.now()
            db.commit()
    finally:
        db.close()


def start_task(task_id: int, document_ids: list[int], options: dict, user_id: int) -> None:
    """启动后台线程执行生成任务"""
    thread = threading.Thread(
        target=_run_workflow,
        args=(task_id, document_ids, options, user_id),
        daemon=True,
    )
    thread.start()

def recover_stuck_tasks() -> int:
    """服务启动时清理僵尸任务：进程重启会杀死后台线程，遗留的 running/pending
    任务永远不会再推进，统一标记为 failed(悬挂)，用户可在任务列表一键重试。"""
    db = SessionLocal()
    try:
        stuck = db.scalars(
            select(GenerationTask).where(GenerationTask.status.in_(["running", "pending"]))
        ).all()
        now = datetime.now()
        for t in stuck:
            t.status = "failed"
            t.progress = t.progress or 0
            t.finished_at = now
            t.error_msg = "服务重启导致任务中断（悬挂），可点击重试恢复"
        if stuck:
            db.commit()
        return len(stuck)
    finally:
        db.close()


def get_task(db: Session, task_id: int) -> GenerationTask:
    task = db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("任务不存在")
    return task


def cancel_task(db: Session, task_id: int) -> GenerationTask:
    task = get_task(db, task_id)
    if task.status in ("success", "failed", "cancelled"):
        raise BusinessError(f"任务已处于 {task.status} 状态，无法取消")
    task.status = "cancelled"
    task.finished_at = datetime.now()
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    user_id: int | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[GenerationTask], int]:
    """分页查询任务历史；user_id 为空表示全部（管理员）"""
    stmt = select(GenerationTask)
    if user_id is not None:
        stmt = stmt.where(GenerationTask.created_by == user_id)
    if status:
        stmt = stmt.where(GenerationTask.status == status)
    total = len(db.scalars(stmt).all())
    rows = db.scalars(
        stmt.order_by(GenerationTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total


def retry_task(db: Session, task_id: int, user_id: int) -> GenerationTask:
    """重试失败/取消/悬挂的任务：基于持久化的 options 重新入队执行"""
    task = get_task(db, task_id)
    if task.status == "running" or task.status == "pending":
        raise BusinessError("任务仍在执行中，无法重试")
    if task.created_by != user_id and db.get(User, user_id).role != "admin":
        raise BusinessError("无权操作该任务")
    options = task.options or {}
    doc_ids = options.get("document_ids") or ([task.document_id] if task.document_id else [])
    if not doc_ids:
        raise BusinessError("任务缺少关联文档，无法重试")
    # 重置状态后重新入队
    task.status = "pending"
    task.progress = 0
    task.error_msg = None
    task.started_at = None
    task.finished_at = None
    db.commit()
    start_task(task.id, doc_ids, options, user_id)
    return task
