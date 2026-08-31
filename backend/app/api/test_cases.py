"""测试用例接口"""
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.test_case import TestCase, TestCaseVersion
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.test_case import (
    BatchRequest,
    ExportRequest,
    ReviewRequest,
    TestCaseCreate,
    TestCaseOut,
    TestCaseUpdate,
    TestCaseVersionOut,
)
from app.services import test_case_service

router = APIRouter()


@router.get("")
def list_cases(
    project_id: int | None = Query(None),
    priority: str | None = Query(None),
    status: str | None = Query(None),
    source: str | None = Query(None),
    keyword: str | None = Query(None),
    module: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    ids_only: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if ids_only:
        # 跨页全选：返回当前查询条件下全部用例的 (id, source)，不分页
        items = test_case_service.list_case_ids(db, project_id, priority, status, source, keyword, module)
        return ok({"items": [{"id": i, "source": s} for i, s in items], "total": len(items)})
    cases, total = test_case_service.list_cases(
        db, page, page_size, project_id, priority, status, source, keyword, module
    )
    return ok(PageData(list=[TestCaseOut.model_validate(c) for c in cases], total=total, page=page, page_size=page_size))


@router.get("/modules")
def list_modules(
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """返回项目下已有用例的去重模块列表（用于模块筛选/编辑下拉）"""
    return ok({"modules": test_case_service.list_modules(db, project_id)})


@router.post("")
def create_case(
    req: TestCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = test_case_service.create_case(db, req, user.id)
    return ok(case, "用例创建成功")


@router.get("/{case_id}")
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = test_case_service.get_case(db, case_id)
    return ok(case)


@router.put("/{case_id}")
def update_case(
    case_id: int,
    req: TestCaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = test_case_service.update_case(db, case_id, req, user.id)
    return ok(TestCaseOut.model_validate(case), "用例更新成功")


@router.put("/{case_id}/review")
def review_case(
    case_id: int,
    req: ReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = test_case_service.review_case(db, case_id, req.action, req.comment, user.id)
    return ok(TestCaseOut.model_validate(case), "评审操作成功")


@router.post("/{case_id}/auto-complete")
def auto_complete_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """FR-5.5 用例自动补全: 调用 LLM 补全缺失的前置条件/步骤/预期结果"""
    case, completed = test_case_service.auto_complete_case(db, case_id, user.id)
    return ok(
        {"case": TestCaseOut.model_validate(case), "completed_fields": completed},
        f"已补全字段: {', '.join(completed)}" if completed else "用例字段已完整，无需补全",
    )


@router.get("/{case_id}/versions")
def case_versions(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    versions = db.scalars(
        select(TestCaseVersion).where(TestCaseVersion.case_id == case_id).order_by(TestCaseVersion.version.desc())
    ).all()
    return ok([TestCaseVersionOut.model_validate(v) for v in versions])


@router.post("/batch")
def batch_action(
    req: BatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = test_case_service.batch_action(db, req.case_ids, req.action, user.id)
    return ok({"affected": count}, f"批量{req.action}成功")


@router.post("/feedback")
def set_feedback(
    case_id: int = Query(...),
    feedback: str = Query(..., pattern="^(good|bad|clear)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI 生成质量人工反馈：good(质量好) / bad(质量差) / clear(清除)"""
    case = test_case_service.set_feedback(db, case_id, feedback)
    return ok(TestCaseOut.model_validate(case), "已记录反馈")


@router.post("/batch-regenerate")
def batch_regenerate(
    req: BatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """FR-3.8 批量重生成：选中 AI 用例，基于原上下文重新生成并覆盖"""
    cases = test_case_service.regenerate_cases(db, req.case_ids, user.id)
    return ok(
        {"regenerated": len(cases), "cases": [TestCaseOut.model_validate(c) for c in cases]},
        f"已重生成 {len(cases)} 条用例",
    )


@router.post("/import")
def import_cases(
    file: UploadFile = File(...),
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """从 Excel 导入用例（RAG 知识库建设）"""
    from app.services import excel_service

    count = excel_service.import_cases(db, file, project_id, user.id)
    return ok({"imported": count}, f"成功导入 {count} 条用例")


@router.post("/export")
def export_cases(
    req: ExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出用例（Excel / Markdown / JSON / XMind）"""
    from fastapi.responses import StreamingResponse
    from app.services import excel_service

    ts = int(__import__("time").time() * 1000)
    suffix = req.format or "excel"
    if suffix == "xmind":
        data = excel_service.export_cases_xmind(db, req.case_ids)
        filename = f"test_cases_{user.id}_{ts}.xmind"
        return StreamingResponse(
            iter([data]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if suffix == "markdown":
        content = excel_service.export_cases_markdown(db, req.case_ids)
        media_type = "text/markdown; charset=utf-8"
        filename = f"test_cases_{user.id}_{ts}.md"
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if suffix == "json":
        content = excel_service.export_cases_json(db, req.case_ids)
        media_type = "application/json; charset=utf-8"
        filename = f"test_cases_{user.id}_{ts}.json"
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    data = excel_service.export_cases(db, req.case_ids)
    filename = f"test_cases_{user.id}_{ts}.xlsx"
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
