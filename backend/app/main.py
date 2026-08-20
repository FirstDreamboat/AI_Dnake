"""FastAPI 应用入口"""
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import settings
from app.core.exceptions import BusinessError
from app.core.security import decode_token
from app.database import SessionLocal, init_db

logger = logging.getLogger("operation_log")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库与种子数据，并加载持久化的 LLM 配置"""
    init_db()
    from app.utils.seed import create_admin_user

    create_admin_user()
    # 若用户曾通过系统设置界面切换过模型，启动时恢复该配置（优先于 .env）
    from app.models.sys_config import SysConfig
    from app.services.llm_service import set_runtime_llm_config

    db = SessionLocal()
    try:
        cfg = {c.config_key: c.config_value for c in db.query(SysConfig).all()}
        if cfg.get("llm_provider"):
            set_runtime_llm_config(
                provider=cfg.get("llm_provider"),
                llm_model=cfg.get("llm_model"),
                deepseek_model=cfg.get("deepseek_model"),
            )
    except Exception:
        logger.exception("加载持久化 LLM 配置失败")
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="狄耐克AI驱动嵌入式测试用例自动生成平台 API",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(api_router)

# 写操作日志中间件（排除登录/健康检查/文档类接口）
_LOG_SKIP_PATTERNS = re.compile(
    r"^/(docs|redoc|openapi\.json|favicon\.ico)|/health|/auth/login"
)
_LOG_WRITE_METHODS = {"POST", "PUT", "DELETE"}


@app.middleware("http")
async def operation_log_middleware(request: Request, call_next):
    response = await call_next(request)
    try:
        method = request.method
        path = request.url.path
        if method in _LOG_WRITE_METHODS and not _LOG_SKIP_PATTERNS.search(path):
            user_id = username = None
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                try:
                    payload = decode_token(auth[7:])
                    user_id = payload.get("sub")
                except Exception:
                    pass
            # 解析模块与动作
            segments = [s for s in path.split("/") if s]
            module = segments[1] if len(segments) > 1 else ""
            action = segments[-1] if segments else ""
            # 非 multipart 的写操作记录请求体摘要
            detail = None
            if "multipart/form-data" not in request.headers.get("content-type", ""):
                try:
                    body = await request.body()
                    if body:
                        raw = body.decode("utf-8", errors="ignore")
                        detail = raw[:500]
                except Exception:
                    detail = None
            ip = request.client.host if request.client else None
            db = SessionLocal()
            try:
                from app.models.user import User
                from app.services.log_service import create_log

                if user_id is not None:
                    u = db.get(User, int(user_id)) if str(user_id).isdigit() else None
                    username = u.username if u else None
                create_log(
                    db,
                    user_id=user_id,
                    username=username,
                    module=module,
                    action=action,
                    method=method,
                    path=path,
                    detail=detail,
                    ip=ip,
                    status_code=response.status_code,
                )
            except Exception:
                db.rollback()
                logger.exception("写入操作日志失败")
            finally:
                db.close()
    except Exception:
        logger.exception("操作日志中间件异常")
    return response


@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError):
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


@app.get("/")
def root():
    # 已构建前端产物时，根路径直接返回前端页面（单端口部署）
    index = _DIST_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/system/health",
    }


# ===== 前端静态资源托管（单端口部署：页面与 API 同源）=====
_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def _mount_frontend(app: FastAPI) -> None:
    """若存在 frontend/dist 构建产物，则挂载静态资源并提供 history 路由回退"""
    if not (_DIST_DIR / "index.html").exists():
        return
    app.mount(
        "/assets",
        StaticFiles(directory=_DIST_DIR / "assets"),
        name="frontend-assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # API 路径未被匹配时应返回 404，而非回退到前端页面
        if full_path.startswith("api/") or full_path.startswith("docs"):
            raise HTTPException(status_code=404, detail="Not Found")
        target = _DIST_DIR / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(_DIST_DIR / "index.html")


_mount_frontend(app)
