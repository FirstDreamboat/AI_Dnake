"""权限点目录与角色默认权限配置

权限模型说明：
- 系统提供一组可勾选的"权限点"（权限目录），管理员可在成员管理中为每个成员自定义。
- admin 角色拥有全部权限（不落库，动态返回），其余角色通过 user_permissions 表保存自定义权限。
- 业务模块权限点（project/generate/knowledge/script）主要控制前端菜单与路由可见性；
  管理模块权限点（script_template/statistics/logs/settings/user_manage）同时在后端接口做强校验。
"""

from typing import Any

# 权限点目录（code 必须与前端 src/utils/permissions.ts 保持一致）
PERMISSION_CATALOG: list[dict[str, Any]] = [
    {"code": "project", "label": "项目管理", "group": "业务功能", "description": "查看与管理测试项目"},
    {"code": "generate", "label": "AI 用例生成", "group": "业务功能", "description": "使用 AI 生成与评审测试用例"},
    {"code": "knowledge", "label": "知识库", "group": "业务功能", "description": "上传与管理知识库文档"},
    {"code": "script", "label": "脚本管理", "group": "业务功能", "description": "管理与下载测试脚本"},
    {"code": "script_template", "label": "脚本模板", "group": "管理功能", "description": "创建/编辑/删除自定义脚本模板"},
    {"code": "statistics", "label": "统计报表", "group": "管理功能", "description": "查看统计报表与趋势分析"},
    {"code": "logs", "label": "操作日志", "group": "管理功能", "description": "查看与检索操作日志"},
    {"code": "settings", "label": "系统设置", "group": "管理功能", "description": "查看与修改系统配置"},
    {"code": "user_manage", "label": "成员管理", "group": "管理功能", "description": "添加成员、分配权限、停用与删除成员"},
]

ALL_PERMISSIONS: list[str] = [p["code"] for p in PERMISSION_CATALOG]

# 各角色默认权限（admin 拥有全部权限，无需在此配置）
DEFAULT_PERMISSIONS: dict[str, list[str]] = {
    "manager": [
        "project",
        "generate",
        "knowledge",
        "script",
        "script_template",
        "statistics",
        "logs",
    ],
    "engineer": ["project", "generate", "knowledge", "script"],
    # 产品经理：需求体检 + 知识库 + 项目查看，不涉及测试脚本（把质量前置到需求阶段）
    "product": ["project", "generate", "knowledge"],
    # 研发人员：需求体检 + 提测自带脚本 + 知识库
    "developer": ["project", "generate", "knowledge", "script"],
}

# 校验权限点是否为合法值
VALID_PERMISSION_CODES: set[str] = set(ALL_PERMISSIONS)


def default_permissions_for(role: str) -> list[str]:
    """返回角色默认权限列表；admin 返回全部权限。"""
    if role == "admin":
        return list(ALL_PERMISSIONS)
    return list(DEFAULT_PERMISSIONS.get(role, []))
