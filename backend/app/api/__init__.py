"""API 路由注册"""
from fastapi import APIRouter

from app.api import auth, case_files, documents, generate, knowledge, logs, notifications, permissions, projects, requirement_review, script_templates, scripts, stats, system, test_cases, test_points, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, tags=["认证"])
api_router.include_router(case_files.router, prefix="/case-files", tags=["用例文件"])
api_router.include_router(users.router, prefix="/users", tags=["用户"])
api_router.include_router(permissions.router, tags=["权限"])
api_router.include_router(projects.router, prefix="/projects", tags=["项目"])
api_router.include_router(documents.router, prefix="/documents", tags=["需求文档"])
api_router.include_router(test_points.router, prefix="/test-points", tags=["测试点"])
api_router.include_router(test_cases.router, prefix="/test-cases", tags=["测试用例"])
api_router.include_router(generate.router, prefix="/generate", tags=["用例生成"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["知识库"])
api_router.include_router(stats.router, prefix="/stats", tags=["统计"])
api_router.include_router(system.router, prefix="/system", tags=["系统"])
api_router.include_router(scripts.router, prefix="/scripts", tags=["测试脚本"])
api_router.include_router(script_templates.router, prefix="/script-templates", tags=["脚本模板"])
api_router.include_router(logs.router, prefix="/logs", tags=["操作日志"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["消息通知"])
api_router.include_router(requirement_review.router, prefix="/req-review", tags=["需求体检"])
