"""验证新功能：多格式导出 / 混合检索 / 版本管理"""
import json
import io
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"


def call(path, method="GET", data=None, token=None, headers=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# 1. 登录
_, raw = call("/auth/login", "POST", {"username": "admin", "password": "admin123"})
login = json.loads(raw)
assert login["code"] == 0, login
token = login["data"]["access_token"]
print("[OK] 登录成功")

# 2. 取用例列表（找两个用例 id）
_, raw = call("/test-cases?page=1&page_size=5", token=token)
cases = json.loads(raw)["data"]["list"]
if not cases:
    print("[SKIP] 无用例可导出，跳过导出测试")
else:
    ids = [c["id"] for c in cases[:2]]
    print(f"[OK] 获取用例 {ids}")

    # 3. 导出 Excel
    status, raw = call("/test-cases/export", "POST", {"case_ids": ids, "format": "excel"}, token)
    assert status == 200 and raw[:2] == b"PK", (status, raw[:20])
    print("[OK] 导出 Excel（xlsx 有效）")

    # 4. 导出 Markdown
    status, raw = call("/test-cases/export", "POST", {"case_ids": ids, "format": "markdown"}, token)
    assert status == 200 and b"#" in raw and b"\xe6\xb5\x8b\xe8\xaf\x95\xe7\x94\xa8\xe4\xbe\x8b" in raw, (status, raw[:100])
    print("[OK] 导出 Markdown（含标题）")

    # 5. 导出 JSON
    status, raw = call("/test-cases/export", "POST", {"case_ids": ids, "format": "json"}, token)
    parsed = json.loads(raw)
    assert status == 200 and "cases" in parsed, (status, raw[:100])
    print(f"[OK] 导出 JSON（{parsed['total']} 条）")

    # 6. 导出 XMind
    status, raw = call("/test-cases/export", "POST", {"case_ids": ids, "format": "xmind"}, token)
    assert status == 200 and raw[:2] == b"PK", (status, raw[:20])
    import zipfile
    zf = zipfile.ZipFile(io.BytesIO(raw))
    assert "content.json" in zf.namelist()
    print("[OK] 导出 XMind（zip 含 content.json）")

# 7. 混合检索
_, raw = call("/knowledge/search", "POST", {"query": "登录 权限 校验", "top_k": 3}, token)
hits = json.loads(raw)["data"]["hits"]
print(f"[OK] 混合检索返回 {len(hits)} 条，首条 title={hits[0].get('title') if hits else 'N/A'} score={hits[0].get('score') if hits else 'N/A'}")

# 8. 知识库列表（版本字段）
_, raw = call("/knowledge/docs?page=1&page_size=5", token=token)
docs = json.loads(raw)["data"]["list"]
for d in docs[:3]:
    print(f"[OK] 知识文档 v{d['version']} - {d['title']}")

print("\n全部验证通过")
