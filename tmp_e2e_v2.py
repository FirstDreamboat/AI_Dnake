"""端到端验证 v2：验证码、登录锁定、通知、任务历史、反馈、批量操作、日志导出
使用 TestClient 直接验证应用代码（独立内存，与运行服务互不影响）。
"""
import sys

sys.path.insert(0, "backend")
sys.path.insert(0, "backend/.")

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}", file=sys.stderr)


from fastapi.testclient import TestClient
from app.database import Base, engine, SessionLocal, init_db
from app.main import app
from app.services import captcha_service, auth_service, notification_service
from app.models.user import User
from app.schemas.user import LoginRequest

init_db()

client = TestClient(app)


# ---------- 1. 验证码 ----------
r = client.get("/api/v1/auth/captcha")
d = r.json()
check("获取验证码接口", r.status_code == 200 and d.get("code") == 0 and "captcha_id" in d.get("data", {}))
captcha_id = d["data"]["captcha_id"]
# 验证码错误拒绝
r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123", "captcha_id": captcha_id, "captcha_code": "XXXX"})
check("错误验证码被拒", r.status_code == 401, f"status={r.status_code}")
# 直接校验内部函数（模拟正确输入）
with captcha_service._LOCK:
    captcha_service._STORE[captcha_id] = ("AB12", __import__("time").time() + 300)
check("验证码校验函数", captcha_service.verify_captcha(captcha_id, "AB12") is True)
check("验证码一次性", captcha_service.verify_captcha(captcha_id, "AB12") is False)


# ---------- 2. 登录锁定 ----------
db = SessionLocal()
u = db.query(User).filter(User.username == "admin").first()
old_failed, old_locked = u.failed_attempts, u.locked_until
try:
    # 造一个临时锁定用户
    from app.core.security import hash_password
    tu = User(username="__locktest__", password_hash=hash_password("Passw0rd!"), role="engineer", is_active=True)
    db.add(tu)
    db.commit()
    tid = tu.id

    locked = False
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"username": "__locktest__", "password": "wrong"})
    db.refresh(tu)
    check("连续失败触发锁定", tu.locked_until is not None, f"locked_until={tu.locked_until}")
    r = client.post("/api/v1/auth/login", json={"username": "__locktest__", "password": "Passw0rd!"})
    check("锁定后正确密码被拒", r.status_code == 401 and "锁定" in r.json().get("message", ""), f"msg={r.json().get('message')}")
    # 清理
    db.delete(tu)
    db.commit()
finally:
    db.close()


# ---------- 3. 登录（获取 token） ----------
# 关闭验证码开关以便通过 API 登录（避免图片内容问题）
orig = captcha_service.settings.LOGIN_CAPTCHA_ENABLED
captcha_service.settings.LOGIN_CAPTCHA_ENABLED = False
r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
captcha_service.settings.LOGIN_CAPTCHA_ENABLED = orig
check("admin 登录", r.status_code == 200 and r.json().get("code") == 0, f"status={r.status_code} msg={r.json().get('message')}")
token = r.json()["data"]["access_token"]
H = {"Authorization": f"Bearer {token}"}


# ---------- 4. 通知 ----------
db = SessionLocal()
from app.models.user import User as U
admin = db.query(U).filter(U.username == "admin").first()
notification_service.create_notification(db, admin.id, "task", "测试通知", "内容", related_id=1)
db.close()
r = client.get("/api/v1/notifications", headers=H)
check("通知列表", r.status_code == 200 and r.json().get("code") == 0, f"status={r.status_code}")
r = client.get("/api/v1/notifications/unread-count", headers=H)
check("未读计数", r.json()["data"]["unread"] >= 1)
nid = r = client.get("/api/v1/notifications", headers=H).json()["data"]["list"][0]["id"]
r = client.put(f"/api/v1/notifications/{nid}/read", headers=H)
check("标记已读", r.status_code == 200)
r = client.put("/api/v1/notifications/read-all", headers=H)
check("全部已读", r.status_code == 200 and r.json().get("data", {}).get("marked", 0) >= 1)
r = client.get("/api/v1/notifications/unread-count", headers=H)
check("已读后未读归零", r.json()["data"]["unread"] == 0)


# ---------- 5. 任务历史 & 重试 ----------
r = client.get("/api/v1/generate/tasks", headers=H)
check("任务历史列表", r.status_code == 200 and r.json().get("code") == 0)
# 造一个失败任务用于重试测试
db = SessionLocal()
from app.models.generation_task import GenerationTask
admin_id = admin.id  # 在 session 关闭前取 id
t = GenerationTask(task_no="T-TEST-RETRY", project_id=None, document_id=1, created_by=admin_id, status="failed", progress=0, options={"document_ids": [1]}, error_msg="test fail")
db.add(t)
db.commit()
tid2 = t.id
db.close()
r = client.post(f"/api/v1/generate/task/{tid2}/retry", headers=H)
check("失败任务重试入队", r.status_code == 200 and r.json().get("data", {}).get("status") == "pending", f"status={r.status_code} body={r.json()}")
# 清理
db = SessionLocal()
db.query(GenerationTask).filter(GenerationTask.id == tid2).delete()
db.commit()
db.close()


# ---------- 6. 用例反馈 & 批量重生成(无 LLM 时失败也走服务层) ----------
db = SessionLocal()
from app.models.test_case import TestCase
tc = TestCase(case_no="TC-FB-001", title="反馈测试", priority="P1", test_type="功能", source="ai", status="draft", steps=[], created_by=admin.id)
db.add(tc)
db.commit()
tcid = tc.id
db.close()
r = client.post(f"/api/v1/test-cases/feedback?case_id={tcid}&feedback=good", headers=H)
check("用例反馈 good", r.status_code == 200 and r.json().get("data", {}).get("feedback") == "good")
r = client.post(f"/api/v1/test-cases/feedback?case_id={tcid}&feedback=clear", headers=H)
check("用例反馈 clear", r.json().get("data", {}).get("feedback") is None)
db = SessionLocal()
db.query(TestCase).filter(TestCase.id == tcid).delete()
db.commit()
db.close()


# ---------- 7. 日志导出 ----------
r = client.get("/api/v1/logs/export", headers=H)
check("日志导出", r.status_code == 200 and b"operation_logs" in r.headers.get("Content-Disposition", "").encode(), f"status={r.status_code}")


print("\n=== 汇总 ===", file=sys.stderr)
failed = [n for n, ok in results if not ok]
print(f"PASS {len(results) - len(failed)} / {len(results)}", file=sys.stderr)
if failed:
    print("FAILED: " + ", ".join(failed), file=sys.stderr)
    sys.exit(1)
print("ALL PASS", file=sys.stderr)
