"""用例生成任务服务

任务创建后进入 pending，由后台线程执行智能体工作流，
进度通过 task 表 progress 字段持久化，前端通过 SSE/轮询获取。
"""
import threading
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.workflow import GenerateWorkflow
from app.core.exceptions import BusinessError, NotFoundError
from app.database import SessionLocal
from app.models.document import Document
from app.models.generation_task import GenerationTask
from app.models.test_case import TestCase
from app.models.test_point import TestPoint
from app.models.user import User
from app.services import notification_service
from app.services.document_service import parse_document
from app.services.test_case_service import save_generated_case

# ---------------------------------------------------------------------------
# 平台自身功能关键词（兜底拦截 AI 误生成的平台功能，避免混入产品用例）。
# 仅收录高置信度的平台专属词，避免误杀产品真实功能（如对讲、门禁、家居等）。
# 注意：产品侧存在"成员角色权限""家庭头像上传"等含"权限/上传"字样的功能，
# 因此不使用"权限管理""文件上传"等宽泛词，防止误拦截。
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
    """文本命中平台自身功能关键词即判定为平台功能（用于兜底过滤）"""
    joined = "|".join(t for t in texts if t)
    if not joined:
        return False
    return any(kw in joined for kw in PLATFORM_FEATURE_KEYWORDS)


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
        contents: list[tuple[int, str]] = []
        for doc_id in document_ids:
            doc, text = parse_document(db, doc_id)
            if text:
                contents.append((doc_id, f"【文档：{doc.title}】\n{text}"))

        total_case = 0
        generated_cases: list[dict] = []
        reviews: list[dict] = []
        business_flows: list[dict] = []
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

        for doc_id, text in contents:
            workflow = GenerateWorkflow(progress_cb=progress_cb)
            result = workflow.run(text, options)
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
                    description=tp.get("description"),
                )
                db.add(point)
                db.commit()
                db.refresh(point)
                existing_point_names.add(name)
                test_points_in_db.append(point)
            # 测试点名称 -> 对象映射，供用例按名称匹配挂接
            test_point_map: dict = {p.name: p for p in test_points_in_db}

            # 用例入库（兜底拦截平台功能；按 test_point 名称匹配挂接测试点，
            # 匹配不到时挂空(NULL)而非轮询错配，避免污染覆盖率统计）
            for case in result.test_cases:
                if _is_platform_feature(case.get("module"), case.get("title"), case.get("test_point")):
                    continue
                title = str(case.get("title") or "").strip()
                # 标题已在项目内存在（含本批已生成）则跳过，避免重复
                if title and title in existing_case_titles:
                    continue
                point = _match_test_point(test_point_map, str(case.get("test_point") or "").strip())
                point_id = point.id if point else None
                saved = save_generated_case(db, task.project_id, case, point_id, user_id)
                if title:
                    existing_case_titles.add(title)
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

        task.total_case = total_case
        task.status = "success"
        task.progress = 100
        task.result_summary = {
            "total_case": total_case,
            "generated_cases": generated_cases[:200],
            "document_count": len(contents),
            "review": review_summary,
            "business_flows": business_flows[:30],
            "finished_at": datetime.now().isoformat(),
        }
        task.finished_at = datetime.now()
        db.commit()
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
