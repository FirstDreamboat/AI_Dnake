"""
把「AI测试用例生成平台」本身作为被测项目，完整录入系统（演示/自测数据）。
- 测试用例内容全部由脚本内置生成，不调用 AI 生成接口（不调用外部 LLM API）
- 文档上传走真实上传 + 本地解析
- 幂等：项目已存在时复用
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient

from app.main import app
from app.services import captcha_service

captcha_service.verify_captcha = lambda cid, code: True

client = TestClient(app)

PROJECT_NAME = "AI测试用例生成平台"
PRODUCT_LINE = "smart_home"  # schema 限定: intercom|smart_home|hospital
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOC_FILES = [
    "方案书.docx",
    "项目需求规格说明书-PRD.md",
    "系统架构设计文档.md",
    "数据库设计文档.md",
    "API接口设计文档.md",
    "项目开发计划书.md",
    "Prompt模板集.md",
    "测试计划与方案文档.md",
    "部署与使用说明.md",
    "README.md",
    "系统测试报告.md",
]


def req(method, url, headers, **kw):
    r = getattr(client, method)(url, headers=headers, **kw)
    return r


def login():
    r = client.post("/api/v1/auth/login", json={
        "username": "admin", "password": "admin123",
        "captcha_id": "x", "captcha_code": "x",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def find_project(headers):
    r = req("get", "/api/v1/projects", headers, params={"keyword": PROJECT_NAME, "page_size": 100})
    if r.status_code != 200:
        return None
    for p in r.json()["data"]["list"]:
        if p["name"] == PROJECT_NAME:
            return p["id"]
    return None


def create_project(headers):
    pid = find_project(headers)
    if pid:
        print(f"[项目] 已存在，复用 id={pid}")
        return pid
    r = req("post", "/api/v1/projects", headers, json={
        "name": PROJECT_NAME,
        "product_line": PRODUCT_LINE,
        "description": "基于大语言模型(LLM)+检索增强生成(RAG)的嵌入式测试用例自动生成平台。"
                       "本记录将该平台本身作为被测对象，演示从需求文档到测试用例/脚本的全流程数据。",
    })
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    print(f"[项目] 创建成功 id={pid}")
    return pid


def upload_and_parse(headers, pid, filename):
    path = os.path.join(ROOT, filename)
    if not os.path.exists(path):
        print(f"[文档] 跳过(文件不存在): {filename}")
        return None
    with open(path, "rb") as f:
        r = req("post", "/api/v1/documents/upload", headers,
                data={"project_id": str(pid), "source_type": "upload"},
                files={"file": (filename, f, "application/octet-stream")})
    if r.status_code != 200:
        print(f"[文档] 上传失败 {filename}: status={r.status_code} {r.text[:200]}")
        return None
    doc_id = r.json()["data"]["id"]
    try:
        r2 = req("post", f"/api/v1/documents/{doc_id}/parse", headers)
        st = r2.json().get("data", {}).get("parse_status", "?")
    except Exception as e:  # noqa: BLE001
        st = f"parse error: {e}"
    print(f"[文档] {filename} -> id={doc_id} parse={st}")
    return doc_id


def create_points(headers, pid, prd_doc_id):
    points = [
        ("用户认证与权限", "function", "登录、图形验证码、JWT鉴权、角色与权限点控制"),
        ("登录安全策略", "security", "验证码校验、账号锁定、强制改密"),
        ("项目管理", "function", "项目增删改查、归档与权限控制"),
        ("需求文档解析", "function", "文档上传、格式校验、内容解析提取"),
        ("测试点管理", "function", "测试点创建、编辑、删除、类型筛选"),
        ("用例自动生成", "function", "AI生成任务、用例编号规则、批量重生成"),
        ("用例管理", "function", "用例CRUD、批量操作、版本历史"),
        ("用例导入导出", "boundary", "Excel导入，Excel/Markdown/JSON/XMind导出"),
        ("用例评审与优化", "function", "评分、问题清单、驳回、AI补全、质量反馈"),
        ("RAG知识库", "function", "文档入库、混合/向量/关键词检索"),
        ("脚本生成与模板", "function", "pytest/api/ui脚本、自定义模板"),
        ("统计报表", "function", "总览、生成趋势、优先级/类型分布、效率对比"),
        ("系统设置", "function", "模型切换、健康检查、已安装模型列表"),
        ("用户与权限管理", "function", "用户创建、权限点分配"),
        ("操作日志与通知", "function", "审计日志、日志导出、消息通知"),
    ]
    doc_id = prd_doc_id or 0
    ids = {}
    for name, tp, desc in points:
        r = req("post", "/api/v1/test-points", headers, json={
            "project_id": pid, "document_id": doc_id,
            "name": name, "type": tp, "description": desc,
        })
        if r.status_code == 200:
            ids[name] = r.json()["data"]["id"]
            print(f"[测试点] {name} id={ids[name]}")
        else:
            print(f"[测试点] 创建失败 {name}: {r.text[:150]}")
    return ids


def review_cases(headers, case_ids, action="approve", comment=""):
    for cid in case_ids:
        try:
            r = req("put", f"/api/v1/test-cases/{cid}/review", headers,
                    json={"action": action, "comment": comment})
            print(f"[评审] {cid} -> {r.status_code}")
        except Exception as e:  # noqa: BLE001
            print(f"[评审] {cid} 失败: {e}")


def main():
    headers = login()
    print("== 登录成功 ==")
    pid = create_project(headers)

    print("\n== 上传需求文档 ==")
    doc_ids = {}
    for fn in DOC_FILES:
        did = upload_and_parse(headers, pid, fn)
        if did:
            doc_ids[fn] = did
    prd_doc_id = doc_ids.get("项目需求规格说明书-PRD.md")

    print("\n== 创建测试点 ==")
    point_ids = create_points(headers, pid, prd_doc_id)

    from seed_test_cases import CASES, SCRIPTS
    print("\n== 创建测试用例 ==")
    created = []
    for i, c in enumerate(CASES, 1):
        payload = {
            "project_id": pid,
            "test_point_id": point_ids.get(c["point"], point_ids.get("用例管理")),
            "title": c["title"],
            "priority": c["priority"],
            "test_type": c["test_type"],
            "source": c.get("source", "manual"),
            "preconditions": c.get("preconditions", ""),
            "steps": c["steps"],
            "expected_result": c.get("expected_result", ""),
        }
        r = req("post", "/api/v1/test-cases", headers, json=payload)
        if r.status_code == 200:
            cid = r.json()["data"]["id"]
            created.append((cid, c))
            print(f"  用例[{i:02d}] {c['title'][:26]} -> id={cid}")
        else:
            print(f"  用例[{i:02d}] 失败 {c['title'][:26]}: {r.text[:200]}")

    # 对 source=ai_reviewed 的用例执行评审通过，体现评审流程
    reviewed = [cid for cid, c in created if c.get("source") == "ai_reviewed"]
    if reviewed:
        print(f"\n== 评审通过 {len(reviewed)} 条 ==")
        review_cases(headers, reviewed, action="approve", comment="人工评审通过（演示数据）")

    print("\n== 保存测试脚本 ==")
    for i, sc in enumerate(SCRIPTS, 1):
        cid = None
        for cid2, c in created:
            if c.get("script_key") == sc["case_key"]:
                cid = cid2
                break
        payload = {
            "project_id": pid,
            "case_id": cid,
            "name": sc["name"],
            "script_type": sc["script_type"],
            "language": "python",
            "framework": "pytest",
            "content": sc["content"],
            "description": sc["description"],
        }
        r = req("post", "/api/v1/scripts", headers, json=payload)
        print(f"  脚本[{i}] {sc['name']} -> {r.status_code}")
        if r.status_code != 200:
            print(f"    {r.text[:200]}")

    print("\n== 完成 ==")


if __name__ == "__main__":
    main()
