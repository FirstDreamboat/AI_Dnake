# -*- coding: utf-8 -*-
"""验证改动后的模块可正常导入，并检查关键导出与 ORM 字段状态。"""
import importlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"c:\Users\admin\Desktop\AI\backend"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MODULES = (
    "app.services.case_quality",
    "app.agents.workflow",
    "app.agents.test_point_extractor",
    "app.agents.test_case_generator",
    "app.models.test_point",
    "app.models.test_case",
    "app.services.test_case_service",
    "app.services.generate_service",
)

failed = []
for name in MODULES:
    try:
        importlib.import_module(name)
        print("[ok] import", name)
    except Exception as exc:
        failed.append((name, exc))
        print("[FAIL] import", name, "->", exc)

if failed:
    print("\n导入失败，终止后续检查")
    raise SystemExit(1)

print("\n--- case_quality 导出 ---")
import app.services.case_quality as cq

for fn in ("annotate_cases", "audit_cases", "build_remark", "check_expected_result", "check_steps"):
    print(f"  {fn}: {'存在' if hasattr(cq, fn) else '缺失'}")

print("\n--- ORM 字段 ---")
from app.models.test_case import TestCase
from app.models.test_point import TestPoint

print("  test_case 列:", [c.name for c in TestCase.__table__.columns])
print("  test_point 列:", [c.name for c in TestPoint.__table__.columns])

print("\n--- 保存函数签名 ---")
import inspect

from app.services.test_case_service import save_generated_case

print("  save_generated_case 参数:", list(inspect.signature(save_generated_case).parameters))

print("\n全部模块导入成功")
