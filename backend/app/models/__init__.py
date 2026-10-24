"""ORM 模型注册"""
from app.models.document import Document
from app.models.case_file import CaseFile
from app.models.generation_task import GenerationTask
from app.models.knowledge import KnowledgeDoc, KnowledgeDocVersion
from app.models.notification import Notification
from app.models.operation_log import OperationLog
from app.models.project import Project
from app.models.script_template import ScriptTemplate
from app.models.sys_config import SysConfig
from app.models.test_case import TestCase, TestCaseVersion
from app.models.test_point import TestPoint
from app.models.test_script import TestScript
from app.models.ui_review_report import UIReviewReport
from app.models.user import User
from app.models.user_permission import UserPermission

__all__ = [
    "User",
    "UserPermission",
    "Project",
    "Document",
    "TestPoint",
    "TestCase",
    "TestCaseVersion",
    "GenerationTask",
    "KnowledgeDoc",
    "KnowledgeDocVersion",
    "Notification",
    "SysConfig",
    "TestScript",
    "ScriptTemplate",
    "UIReviewReport",
    "OperationLog",
]
