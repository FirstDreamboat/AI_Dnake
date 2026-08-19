"""临时：真实 HTTP 触发 doc2 向量化（uvicorn 进程内后台线程执行）"""
import httpx

from app.database import SessionLocal
from app.models.knowledge import KnowledgeDoc

# 重置 stuck
with SessionLocal() as db:
    for kd in db.query(KnowledgeDoc).filter(KnowledgeDoc.vector_status == "indexing").all():
        kd.vector_status = "failed"
        kd.vector_error = "上次中断，可重试"
    db.commit()
    print("reset:", [(k.id, k.title[:15]) for k in db.query(KnowledgeDoc).all()])

BASE = "http://127.0.0.1:8000/api/v1"
with httpx.Client(base_url=BASE, timeout=30) as c:
    r = c.post("/auth/login", json={"username": "admin", "password": "admin123", "captcha_id": "x", "captcha_code": "x"})
    print("login:", r.status_code)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    r = c.post("/knowledge/docs/vectorize-all", headers=h)
    print("vectorize-all:", r.status_code, r.json()["message"], r.json()["data"])
    docs = c.get("/knowledge/docs", headers=h).json()["data"]["list"]
    for d in docs:
        print(f"doc {d['id']}: {d['title'][:18]} status={d['vector_status']} chunks={d['chunk_count']} err={d.get('vector_error')}")
print("DONE")
