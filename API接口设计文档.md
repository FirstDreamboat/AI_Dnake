# 狄耐克AI驱动的研发质量前置平台 —— API接口设计文档

| 文档信息 | 内容 |
|---|---|
| 文档名称 | API接口设计文档 |
| 项目名称 | 狄耐克AI驱动的研发质量前置平台 |
| 文档版本 | V1.0 |
| 编写日期 | 2026-08-12 |
| 文档状态 | 初稿 |
| 基础路径 | `/api/v1` |

---

## 1. 概述

本平台采用 **RESTful API** 风格设计，后端基于 **FastAPI**，支持：

- JWT 认证（Bearer Token）
- 统一响应格式
- 分页查询参数
- SSE 实时流式输出（用例生成进度）
- 接口幂等性设计

### 1.1 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| code | int | 业务状态码，0 表示成功 |
| message | string | 提示信息 |
| data | object | 业务数据 |

### 1.2 分页参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| page | int | 1 | 页码 |
| page_size | int | 10 | 每页数量 |
| keyword | string | - | 关键字搜索 |

分页响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "list": [],
    "total": 100,
    "page": 1,
    "page_size": 10
  }
}
```

### 1.3 通用错误码

| 状态码 | 说明 |
|---|---|
| 401 | 未认证 / Token 过期 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 422 | 参数校验失败 |
| 500 | 服务器内部错误 |

---

## 2. 认证接口（/auth）

### 2.1 用户登录

- **POST** `/auth/login`
- **说明**：使用用户名密码登录，获取 JWT Token。
- **请求体**：

```json
{
  "username": "test_engineer",
  "password": "******"
}
```

- **响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "id": 1,
      "username": "test_engineer",
      "real_name": "张三",
      "role": "engineer"
    }
  }
}
```

### 2.2 刷新 Token

- **POST** `/auth/refresh`
- **说明**：使用 refresh_token 刷新 access_token。
- **请求体**：

```json
{
  "refresh_token": "eyJhbGciOi..."
}
```

### 2.3 获取当前用户信息

- **GET** `/auth/me`
- **说明**：获取当前登录用户信息。

### 2.4 退出登录

- **POST** `/auth/logout`
- **说明**：注销当前 Token。

### 2.5 获取登录验证码

- **GET** `/auth/captcha`
- **说明**：获取图形验证码（服务端内存存储，5 分钟有效，一次性）。
- **响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "captcha_id": "1787000000000-00001",
    "image": "data:image/png;base64,iVBORw0KGgo..."
  }
}
```

### 2.6 修改密码

- **POST** `/auth/change-password`
- **权限**：登录用户
- **说明**：修改当前登录用户密码；`must_change_password=true` 的用户（新建/重置后首次登录）必须调用此接口。
- **请求体**：

```json
{
  "old_password": "old_pass_123",
  "new_password": "new_pass_456"
}
```

---

## 3. 用户管理接口（/users）

### 3.1 用户列表

- **GET** `/users`
- **权限**：admin
- **说明**：分页查询用户列表，支持关键字搜索。

### 3.2 创建用户

- **POST** `/users`
- **权限**：admin
- **请求体**：

```json
{
  "username": "new_user",
  "password": "******",
  "real_name": "李四",
  "email": "lisi@example.com",
  "phone": "13800000000",
  "role": "engineer"
}
```

### 3.3 更新用户

- **PUT** `/users/{user_id}`
- **权限**：admin 或本人
- **说明**：更新用户基本信息。

### 3.4 重置密码

- **PUT** `/users/{user_id}/password`
- **权限**：admin 或本人

### 3.5 启用/禁用用户

- **PUT** `/users/{user_id}/status`
- **权限**：admin
- **请求体**：

```json
{
  "is_active": 0
}
```

### 3.6 删除用户

- **DELETE** `/users/{user_id}`
- **权限**：admin
- **说明**：删除用户（不可删除自身）。

---

## 4. 项目管理接口（/projects）

### 4.1 项目列表

- **GET** `/projects`
- **说明**：分页查询项目列表，支持按产品线、关键字筛选。
- **查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| product_line | string | 产品线（intercom/smart_home/hospital） |
| status | string | 状态（active/archived） |

### 4.2 创建项目

- **POST** `/projects`
- **请求体**：

```json
{
  "name": "楼宇对讲门禁系统",
  "product_line": "intercom",
  "description": "楼宇对讲项目测试用例生成"
}
```

### 4.3 项目详情

- **GET** `/projects/{project_id}`
- **说明**：获取项目详情，含统计信息（用例数、覆盖率等）。

### 4.4 更新项目

- **PUT** `/projects/{project_id}`

### 4.5 删除项目

- **DELETE** `/projects/{project_id}`
- **权限**：admin / manager

### 4.6 归档项目

- **PUT** `/projects/{project_id}/archive`

---

## 5. 需求文档接口（/documents）

### 5.1 文档上传

- **POST** `/documents/upload`
- **说明**：上传需求文档，支持 pdf/word/txt/md 格式，multipart/form-data。
- **参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| project_id | int | 所属项目 |
| file | file | 需求文档文件 |
| source_type | string | 来源类型（upload/link） |

- **响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "document_id": 101,
    "title": "门禁系统需求说明.pdf",
    "file_type": "pdf",
    "parse_status": "pending"
  }
}
```

### 5.2 文档列表

- **GET** `/documents`
- **说明**：按项目分页查询文档列表。

### 5.3 文档详情

- **GET** `/documents/{document_id}`
- **说明**：获取文档详情及解析状态。

### 5.4 触发文档解析

- **POST** `/documents/{document_id}/parse`
- **说明**：手动触发文档解析、分块、向量化。

### 5.5 删除文档

- **DELETE** `/documents/{document_id}`

### 5.6 平台链接解析（FR-1.2）

- **POST** `/documents/parse-url`
- **说明**：抓取需求平台/外部链接内容，自动保存为 Markdown 需求文档，无需手动下载上传。
- **请求体**：

```json
{
  "project_id": 1,
  "url": "https://example.com/requirements/intercom",
  "title": "楼宇对讲系统需求"
}
```

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| project_id | int | 是 | 所属项目 |
| url | string | 是 | 需求链接地址 |
| title | string | 否 | 文档标题，缺省时自动提取网页标题 |

- **响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "document_id": 102,
    "title": "楼宇对讲系统需求",
    "source_type": "url",
    "source_url": "https://example.com/requirements/intercom",
    "parse_status": "done",
    "parse_result": {"chars": 4521, "source_url": "https://example.com/requirements/intercom"}
  }
}
```

---

## 6. 测试点接口（/test-points）

### 6.1 创建测试点（手动）

- **POST** `/test-points`
- **说明**：手动创建测试点（AI 提取之外的补充）。
- **请求体**：

```json
{
  "project_id": 1,
  "document_id": 3,
  "name": "离线状态下门禁卡本地鉴权",
  "type": "exception",
  "technique": "error_guessing",
  "description": "设备离线时验证本地黑名单鉴权能力"
}
```

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| project_id | int | 是 | 所属项目 |
| document_id | int | 否 | 所属需求文档 |
| name | string | 是 | 测试点名称 |
| type | string | 是 | function/boundary/exception/performance/security/implicit |
| technique | string | 否 | 设计技术：equivalence/boundary/decision_table/state_transition/scenario/orthogonal/error_guessing/none，默认 none（与测试点提取器 ALL_TECHNIQUES 对齐） |
| description | string | 否 | 描述 |

### 6.2 测试点列表

- **GET** `/test-points`
- **说明**：按文档或项目查询测试点列表。
- **查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| document_id | int | 所属文档 |
| project_id | int | 所属项目 |
| type | string | 测试点类型（function/boundary/exception/performance/security/implicit） |
| technique | string | 设计技术（equivalence/boundary/decision_table/state_transition/scenario/orthogonal/error_guessing/none） |

### 6.3 测试点详情

- **GET** `/test-points/{point_id}`

### 6.4 更新测试点

- **PUT** `/test-points/{point_id}`
- **说明**：人工修改测试点名称、类型、设计技术、描述。

### 6.5 删除测试点

- **DELETE** `/test-points/{point_id}`

---

## 7. 测试用例接口（/test-cases）

### 7.1 用例列表

- **GET** `/test-cases`
- **说明**：分页查询测试用例，支持多维筛选。
- **查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| project_id | int | 所属项目 |
| test_point_id | int | 关联测试点 |
| priority | string | 优先级（P0/P1/P2/P3/P4） |
| status | string | 状态（draft/reviewed/approved） |
| source | string | 来源（ai/manual/ai_reviewed） |

### 7.2 用例详情

- **GET** `/test-cases/{case_id}`
- **说明**：获取用例详情（含测试步骤）。

### 7.3 创建用例（手动）

- **POST** `/test-cases`
- **请求体**：

```json
{
  "project_id": 1,
  "test_point_id": 5,
  "title": "门禁卡刷卡开门正常流程",
  "preconditions": "系统已就绪，刷卡器连接正常",
  "steps": [
    {"step_no": 1, "action": "在刷卡器前刷卡", "expected": "系统识别成功"},
    {"step_no": 2, "action": "输入合法密码", "expected": "门锁打开"}
  ],
  "priority": "P0",
  "test_type": "功能测试"
}
```

### 7.4 更新用例

- **PUT** `/test-cases/{case_id}`
- **说明**：更新用例内容，自动创建新版本快照。

### 7.5 用例评审

- **PUT** `/test-cases/{case_id}/review`
- **说明**：人工确认用例，审核通过状态流转 draft → reviewed；驳回后回退为 draft 重新修改。
- **请求体**：

```json
{
  "action": "approve",
  "comment": "用例已确认，符合规范"
}
```

| action | 说明 |
|---|---|
| approve | 审核通过，状态流转 reviewed |
| reject | 驳回用例，状态回退 draft，需填写驳回意见 |

### 7.6 批量操作

- **POST** `/test-cases/batch`
- **说明**：批量更新用例状态（审核/通过/删除）。
- **请求体**：

```json
{
  "case_ids": [101, 102, 103],
  "action": "approve"
}
```

### 7.7 用例版本历史

- **GET** `/test-cases/{case_id}/versions`
- **说明**：查询用例的历史版本列表。

### 7.8 用例导入

- **POST** `/test-cases/import`
- **说明**：从 Excel 导入历史测试用例（用于 RAG 知识库建设）。

### 7.9 用例导出

- **POST** `/test-cases/export`
- **说明**：按条件导出用例，支持 Excel/Markdown/JSON/XMind。
- **请求体**：

```json
{
  "project_id": 1,
  "format": "excel",
  "case_ids": [101, 102, 103]
}
```

- **响应**：返回下载链接或文件流。

### 7.10 用例自动补全（FR-5.5）

- **POST** `/test-cases/{case_id}/auto-complete`
- **说明**：AI 自动补全用例缺失的前置条件/测试步骤/预期结果，补全内容写入用例并生成版本快照。
- **请求体**：无（`{}`）
- **响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "case": {
      "id": 101,
      "title": "门禁卡刷卡开门正常流程",
      "preconditions": "系统已就绪，刷卡器连接正常",
      "steps": [{"step_no": 1, "action": "…", "expected": "…"}],
      "expected_result": "…"
    },
    "completed_fields": ["preconditions", "steps", "expected_result"]
  }
}
```

### 7.11 用例反馈（FR-5.7）

- **POST** `/test-cases/feedback`
- **说明**：对 AI 生成质量进行人工反馈（好用/不好用），用于模型效果评估。
- **请求体**：

```json
{
  "case_id": 101,
  "feedback": "good"
}
```

| feedback | 说明 |
|---|---|
| good | 好用，质量认可 |
| bad | 不好用，质量不认可 |

### 7.12 批量重新生成（FR-3.6）

- **POST** `/test-cases/batch-regenerate`
- **说明**：对勾选的用例按对应测试点重新调用 AI 生成，覆盖原用例内容并生成版本快照。
- **请求体**：

```json
{
  "case_ids": [101, 102, 103]
}
```

- **响应**：返回每条的重新生成结果（成功/失败及原因）。

---

## 8. 用例生成接口（/generate）

### 8.1 发起用例生成任务

- **POST** `/generate/task`
- **说明**：基于需求文档发起用例生成任务，返回任务编号。
- **请求体**：

```json
{
  "project_id": 1,
  "document_ids": [101, 102],
  "options": {
    "include_types": ["function", "boundary", "exception"],
    "priority_levels": ["P0", "P1"],
    "enable_rag": true,
    "reference_count": 5
  }
}
```

- **响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": 1001,
    "task_no": "GEN-20260812-0001",
    "status": "pending"
  }
}
```

### 8.2 查询任务状态

- **GET** `/generate/task/{task_id}`
- **说明**：查询生成任务状态与进度。

### 8.3 订阅生成进度（SSE）

- **GET** `/generate/task/{task_id}/stream`
- **说明**：通过 SSE 实时推送生成进度。
- **事件格式**：

```
event: progress
data: {"progress": 30, "stage": "test_point_extraction", "message": "正在提取测试点..."}

event: case_generated
data: {"case_id": 101, "title": "门禁卡刷卡开门正常流程"}

event: complete
data: {"task_id": 1001, "total_case": 56}
```

### 8.4 取消任务

- **POST** `/generate/task/{task_id}/cancel`

### 8.5 生成结果摘要

- **GET** `/generate/task/{task_id}/summary`
- **说明**：获取任务完成后统计摘要（覆盖类型、各优先级数量等）。

### 8.6 覆盖率分析

- **GET** `/generate/task/{task_id}/coverage`
- **说明**：获取测试点覆盖情况分析，标注未覆盖项。

### 8.7 生成任务历史

- **GET** `/generate/tasks`
- **说明**：分页查询当前用户/全部用户的生成任务历史。
- **查询参数**：`page`、`page_size`、`project_id`、`status`（pending/running/success/failed/cancelled）。

### 8.8 重试生成任务

- **POST** `/generate/task/{task_id}/retry`
- **说明**：对失败或被取消的任务重新发起生成（复用原任务配置，创建新任务）。
- **响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": 1002,
    "task_no": "GEN-20260812-0002",
    "status": "pending"
  }
}
```

---

## 9. 测试脚本接口（/scripts）

> 第三期进阶功能：将测试用例自动转换为可执行的自动化测试脚本（FR-6）。

### 9.1 生成测试脚本

- **POST** `/scripts/generate`
- **说明**：根据选中的测试用例调用 LLM 生成自动化脚本，支持四种类型。
- **请求体**：

```json
{
  "case_ids": [101, 102],
  "script_type": "pytest",
  "custom_prompt": "使用 requests 库并输出日志"
}
```

- **script_type 说明**：

| 类型 | 含义 | 技术栈 |
|---|---|---|
| pytest | 单元测试脚本 | pytest + pytest-mock（mock 硬件交互） |
| api | 接口自动化脚本 | pytest + requests |
| ui | UI 自动化脚本 | pytest + playwright |
| android | 安卓 APP UI 自动化 | pytest + Appium + uiautomator2 |
| ios | iOS APP UI 自动化 | pytest + Appium + XCUITest（需 Mac） |
| custom | 自定义脚本 | 按 custom_prompt 生成 |

- **响应**：返回 `content`（完整 Python 源码）、`suggest_name`、`framework`、`description` 等，不落库。

### 9.2 保存脚本

- **POST** `/scripts`
- **请求体**：

```json
{
  "project_id": 1,
  "case_id": 101,
  "name": "test_api_reg",
  "script_type": "api",
  "language": "python",
  "framework": "pytest + requests",
  "content": "# 脚本源码...",
  "description": "由 2 条测试用例自动生成的接口自动化脚本"
}
```

### 9.3 脚本列表

- **GET** `/scripts`
- **查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| project_id | int | 所属项目 |
| case_id | int | 关联用例 |
| script_type | string | 脚本类型 |
| page / page_size | int | 分页 |

### 9.4 脚本详情

- **GET** `/scripts/{script_id}`

### 9.5 更新脚本

- **PUT** `/scripts/{script_id}`
- **说明**：更新脚本名称、内容、描述。

### 9.6 删除脚本

- **DELETE** `/scripts/{script_id}`

### 9.7 下载脚本

- **GET** `/scripts/{script_id}/download`
- **说明**：以 `.py` 文件形式下载脚本源码。响应头 `Content-Disposition` 按 RFC 5987 处理中文文件名：`filename*=UTF-8''<百分号编码>` 传输真实中文名，同时保留 ASCII 兜底名，避免脚本名含中文时下载崩溃。

---

## 10. 知识库接口（/knowledge）

### 10.1 知识库文档列表

- **GET** `/knowledge/docs`
- **说明**：分页查询知识库文档，支持按类型、产品线筛选。
- **查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| doc_type | string | 文档类型（test_case/prd/tech_spec/defect/best_practice），可空 |
| product_line | string | 产品线（intercom/smart_home/hospital），可空；空=全部 |

### 10.2 上传知识文档

- **POST** `/knowledge/docs/upload`
- **参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| doc_type | string | 文档类型（test_case/prd/tech_spec/defect/best_practice） |
| product_line | string | 产品线（intercom/smart_home/hospital），可空；空=通用知识。同名同类型**同产品线**文档视为同一文档，更新上传自动递增版本 |
| file | file | 知识文档文件 |

### 10.3 知识文档详情

- **GET** `/knowledge/docs/{doc_id}`
- **说明**：获取文档详情、向量化状态及文档全文（content），用于前端内容预览。

### 10.4 触发向量化

- **POST** `/knowledge/docs/{doc_id}/vectorize`
- **说明**：对知识文档进行分块、向量化并入库。

### 10.5 语义检索测试

- **POST** `/knowledge/search`
- **说明**：检索相似历史用例，支持三种模式（FR-4.3 混合检索策略）。
- **请求体**：

```json
{
  "query": "门禁卡忘记带时如何开门",
  "top_k": 5,
  "mode": "hybrid"
}
```

- **参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| query | string | - | 检索内容 |
| top_k | int | 5 | 返回条数 |
| mode | string | hybrid | hybrid=向量+关键词融合 / vector=纯向量 / keyword=纯关键词 |

### 10.6 知识库对话问答

- **POST** `/knowledge/chat`
- **说明**：知识库对话形式问答（RAG）。检索知识库相关片段 → 组装上下文 → 调用 LLM 生成回答，响应附带引用来源（FR-4.5）。支持指定产品线（业务域）限定检索范围，避免跨产品线知识污染回答。支持指定产品线（业务域）限定检索范围，避免跨产品线知识污染回答。
- **请求体**：

```json
{
  "question": "离线开锁功能有哪些测试要点？",
  "history": [
    { "role": "user", "content": "智能门锁有哪些核心功能？" },
    { "role": "assistant", "content": "智能门锁核心功能包括离线开锁、指纹识别等。" }
  ],
  "top_k": 5,
  "mode": "hybrid",
  "product_line": "smart_home"
}
```

- **参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| question | string | - | 用户问题（必填） |
| history | array | [] | 历史消息（`{role, content}`，最多携带最近 8 条，支持多轮追问） |
| top_k | int | 5 | 检索片段数 |
| mode | string | hybrid | 检索模式：hybrid=混合 / vector=向量 / keyword=关键词 |
| product_line | string | 空 | 产品线过滤（intercom/smart_home/hospital）；空=全库检索 |

- **响应体**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "answer": "根据参考知识，离线开锁的测试要点包括……",
    "sources": [
      { "doc_id": "xxx", "title": "智能锁V4.0.3功能需求", "chunk_index": 660, "content": "……", "score": 0.7188 }
    ]
  }
}
```

### 10.7 删除知识文档

- **DELETE** `/knowledge/docs/{doc_id}`

### 10.8 知识文档版本历史

- **GET** `/knowledge/docs/{doc_id}/versions`
- **说明**：FR-4.4 版本管理。返回该文档的历史版本快照列表（含变更说明、快照内容），同名文档更新上传时自动递增版本号并保存旧版本快照。

---

## 11. 统计与报表接口（/stats）

### 11.1 平台总览

- **GET** `/stats/overview`
- **说明**：平台总览统计（用户数、项目数、用例总数、生成任务数）。

### 11.2 项目统计

- **GET** `/stats/projects/{project_id}`
- **说明**：项目维度的用例统计、覆盖率、生成效率。

### 11.3 生成效率对比

- **GET** `/stats/efficiency`
- **说明**：AI 生成 vs 人工编写用例的效率对比数据（用于 POC 效果验证）。

### 11.4 用例质量分布

- **GET** `/stats/quality`
- **说明**：按用例来源（AI/人工/审校后）统计质量指标。

### 11.5 测试类型分布

- **GET** `/stats/test-types`
- **说明**：按测试类型（功能/边界/异常/性能/安全/隐式）统计用例数量分布。

### 11.6 优先级分布

- **GET** `/stats/priorities`
- **说明**：按优先级（P0/P1/P2/P3/P4）统计用例数量分布。

### 11.7 生成趋势

- **GET** `/stats/trend`
- **说明**：近 N 天用例生成数量趋势（按日聚合，支持按项目过滤）。

---

## 12. 系统管理接口（/system）

### 12.1 模型配置

- **GET** `/system/models`
- **说明**：查看当前可用的 LLM 模型列表及配置。

### 12.2 更新模型配置

- **PUT** `/system/models/{model_id}`
- **权限**：admin
- **说明**：切换模型、更新 API 地址、超时等参数。

### 12.3 智能体工作流配置

- **GET** `/system/agents`
- **说明**：查看智能体（需求解析/测试点提取/用例生成/用例评审）配置。

### 12.4 更新智能体配置

- **PUT** `/system/agents/{agent_id}`
- **权限**：admin
- **说明**：更新智能体的 Prompt 模板、模型、温度等参数。

### 12.5 系统配置

- **GET** `/system/config`

### 12.6 系统健康检查

- **GET** `/system/health`
- **说明**：检查后端、数据库、向量库、模型服务是否正常。

---

## 13. 消息通知接口（/notifications）

### 13.1 通知列表

- **GET** `/notifications`
- **权限**：登录用户
- **说明**：分页查询当前用户通知（可按 `is_read` 过滤）。

### 13.2 未读通知数

- **GET** `/notifications/unread-count`
- **说明**：获取当前用户未读通知数量（顶部铃铛角标）。

### 13.3 标记已读

- **PUT** `/notifications/{notification_id}/read`
- **说明**：单条通知标记已读。

### 13.4 全部已读

- **PUT** `/notifications/read-all`
- **说明**：当前用户全部通知一键已读。

---

## 14. 操作日志接口（/logs）

### 14.1 日志列表

- **GET** `/logs`
- **权限**：admin
- **说明**：分页查询操作日志，支持按模块/操作用户/操作动作/时间范围过滤。

### 14.2 清空日志

- **DELETE** `/logs`
- **权限**：admin
- **说明**：清空全部操作日志。

### 14.3 导出日志

- **GET** `/logs/export`
- **权限**：admin
- **说明**：导出操作日志 CSV 文件。

---

## 15. 脚本模板接口（/script-templates）—— FR-6.4

### 15.1 模板列表

- **GET** `/script-templates`
- **说明**：分页查询脚本模板（管理员可查全部，其他角色可查自己创建的）。

### 15.2 全部启用模板

- **GET** `/script-templates/all`
- **说明**：获取所有已启用的模板（用于脚本生成下拉选择）。

### 15.3 创建模板

- **POST** `/script-templates`
- **请求体**：

```json
{
  "name": "pytest接口用例模板",
  "script_type": "pytest",
  "language": "python",
  "framework": "pytest",
  "template_content": "import requests\n...",
  "description": "接口自动化用例模板"
}
```

### 15.4 更新模板

- **PUT** `/script-templates/{template_id}`
- **说明**：更新模板内容、启用状态等。

### 15.5 删除模板

- **DELETE** `/script-templates/{template_id}`

---

## 16. 权限点管理接口（/permissions）

> 非 admin 用户的接口级权限点管理（admin 动态拥有全部权限，不走此接口）。

### 16.1 权限点目录

- **GET** `/permissions/catalog`
- **权限**：admin
- **说明**：获取全部权限点目录（模块分组编码与说明）。

### 16.2 查询用户权限点

- **GET** `/permissions/users/{user_id}/permissions`
- **权限**：admin
- **说明**：查询指定用户已分配的权限点编码列表。

### 16.3 更新用户权限点

- **PUT** `/permissions/users/{user_id}/permissions`
- **权限**：admin
- **请求体**：

```json
{
  "permission_codes": ["project:view", "test_case:create", "test_case:generate"]
}
```

- **说明**：覆盖式更新用户权限点分配。

---

## 17. 需求体检接口（/req-review）

> 研发质量前置出口：上传 PRD 即出体检报告（评分 + 问题清单），面向产品/研发在提测前发现需求缺陷。报告落库，支持随时查看与导出 PDF。

### 17.1 上传并体检

- **POST** `/req-review/analyze`
- **请求**：multipart 文件（md/txt/docx/pdf/图片）
- **说明**：解析 → 需求提取 → 测试点提取 → 质量评审，报告自动落库后返回（含 id）。耗时约 1-2 分钟。
- **响应**：完整报告（score/summary/metrics/issues/highlights + id/filename/created_at）

### 17.2 历史报告列表

- **GET** `/req-review/reports`
- **查询参数**：page / page_size
- **说明**：返回摘要列表（id/filename/score/summary 摘要/created_at）

### 17.3 报告详情

- **GET** `/req-review/reports/{report_id}`
- **说明**：返回完整报告（含全部问题清单与亮点）。

### 17.4 下载报告 PDF

- **GET** `/req-review/reports/{report_id}/download`
- **说明**：reportlab 生成 PDF（中文字体），`Content-Disposition` 按 RFC 5987 处理中文文件名。

### 17.5 报告可见性规则（当前实现 + 规划方案）

**当前实现（方案 A：账号隔离 + 管理员全局）：**

| 操作 | 普通账号 | 管理员 |
|---|---|---|
| 历史列表 | 仅本人报告 | 全部用户报告 |
| 详情 / PDF 下载 | 仅本人报告 | 任意报告 |

- 生成即归属：报告落库时记录 `user_id`，接口层（非前端）强制校验归属，越权访问返回 404。
- 设计理由：报告视为个人工作产出，按账号隔离保证数据安全。

**规划中可选方案（暂未实现，按需启动）：**

| 方案 | 规则 | 适用场景 | 改动量 |
|---|---|---|---|
| B 团队可见 | manager 及以上可查看团队报告 | 项目经理统览团队体检情况 | 小（暂无部门维度，manager 可见范围=全部，与 admin 重合） |
| C 项目级共享 | 报告挂 `project_id`，项目成员可见 | 团队围绕同一份 PRD 协作 | 中（表加字段 + 接口过滤 + 前端筛选；协作叙事最顺） |

> 落地提示：B/C 均只需在 `ui_review_report` 增加 `project_id` 字段并调整列表过滤逻辑；对外口径："当前按账号隔离保证数据安全，项目级共享已在规划中"。

## 18. 文件管理接口（/files）

> ⏳ 规划中（未实现）。当前文件上传/下载分别集成于对应业务模块：
> - 需求文档上传：`POST /documents/upload`、链接解析 `POST /documents/parse-url`
> - 知识库文档上传：`POST /knowledge/docs/upload`
> - 用例导出：`POST /test-cases/export`（Excel/Markdown/JSON/XMind）
> - 脚本下载：`GET /scripts/{script_id}/download`

### 13.1 上传文件

- **POST** `/files/upload`

### 13.2 下载文件

- **GET** `/files/{file_id}/download`

### 13.3 删除文件

- **DELETE** `/files/{file_id}`

---

## 19. 接口调用时序

### 18.1 完整生成流程时序

```
用户                  前端                后端                 智能体编排          大模型
 │                    │                  │                     │                │
 │ 上传需求文档        │                  │                     │                │
 ├────────────────────►  POST /documents/upload                  │                │
 │                    │──────────────────►                       │                │
 │                    │◄─ document_id ───│                       │                │
 │ 发起生成           │                  │                     │                │
 ├────────────────────►  POST /generate/task                    │                │
 │                    │──────────────────►                      │                │
 │                    │◄─ task_id ───────│                       │                │
 │                    │ GET /generate/task/{id}/stream (SSE)    │                │
 │◄───────────────────│                   │──调用需求解析───────► │──调用LLM──────►│
 │◄── progress 30% ───│◄─ RAG检索结果 ────│◄─────────────────────│◄──响应────────│
 │◄── progress 60% ───│                   │──调用用例生成────────►│──调用LLM──────►│
 │◄── case_generated ─│◄─ 用例结果 ───────│◄─────────────────────│◄──响应────────│
 │◄── progress 100% ──│◄─ complete ──────│                       │                │
 │ 查看结果           │                  │                     │                │
 ├────────────────────► GET /test-cases?task_id=1001             │                │
 │                    │◄── 用例列表 ──────│                       │                │
```

---

## 20. 接口安全设计

| 项目 | 方案 |
|---|---|
| 认证方式 | JWT Bearer Token，过期时间 24h |
| 刷新机制 | refresh_token 自动续期 |
| 权限控制 | RBAC，基于角色（admin/manager/engineer） |
| 接口限流 | 登录接口限流，防止暴力破解 |
| 数据校验 | Pydantic 参数校验，统一 422 错误 |
| 日志审计 | 关键操作记录操作日志 |
| CORS | 仅允许前端域名访问 |
| 传输安全 | 生产环境启用 HTTPS |

---

## 21. 接口清单汇总

| 模块 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 认证 | POST | /auth/login | 登录（含验证码） |
| 认证 | GET | /auth/captcha | 获取登录验证码 |
| 认证 | POST | /auth/refresh | 刷新Token |
| 认证 | GET | /auth/me | 当前用户 |
| 认证 | POST | /auth/change-password | 修改密码（强制改密） |
| 认证 | POST | /auth/logout | 退出 |
| 用户 | GET/POST | /users | 用户列表/创建 |
| 用户 | PUT/DELETE | /users/{id} | 更新/删除用户 |
| 用户 | PUT | /users/{id}/password | 重置密码 |
| 用户 | PUT | /users/{id}/status | 启用/禁用 |
| 权限 | GET | /permissions/catalog | 权限点目录 |
| 权限 | GET/PUT | /permissions/users/{id}/permissions | 用户权限点查询/分配 |
| 项目 | GET/POST | /projects | 项目列表/创建 |
| 项目 | GET/PUT/DELETE | /projects/{id} | 项目详情/更新/删除 |
| 项目 | PUT | /projects/{id}/archive | 归档/取消归档 |
| 文档 | POST | /documents/upload | 文档上传 |
| 文档 | GET | /documents | 文档列表 |
| 文档 | GET/DELETE | /documents/{id} | 详情/删除 |
| 文档 | POST | /documents/{id}/parse | 触发解析 |
| 文档 | POST | /documents/parse-url | 平台链接解析（FR-1.2） |
| 测试点 | GET/POST | /test-points | 测试点列表/手动创建 |
| 测试点 | PUT/DELETE | /test-points/{id} | 更新/删除 |
| 用例 | GET/POST | /test-cases | 用例列表/手动创建 |
| 用例 | GET/PUT | /test-cases/{id} | 详情/更新 |
| 用例 | PUT | /test-cases/{id}/review | 评审（含驳回） |
| 用例 | POST | /test-cases/{id}/auto-complete | AI 自动补全（FR-5.5） |
| 用例 | GET | /test-cases/{id}/versions | 版本历史 |
| 用例 | POST | /test-cases/batch | 批量状态操作 |
| 用例 | POST | /test-cases/feedback | 生成质量反馈（FR-5.7） |
| 用例 | POST | /test-cases/batch-regenerate | 批量重新生成（FR-3.6） |
| 用例 | POST | /test-cases/import | Excel 导入 |
| 用例 | POST | /test-cases/export | 导出（Excel/MD/JSON/XMind） |
| 生成 | POST | /generate/task | 发起生成 |
| 生成 | GET | /generate/tasks | 任务历史 |
| 生成 | GET | /generate/task/{id} | 任务状态 |
| 生成 | GET | /generate/task/{id}/stream | SSE进度 |
| 生成 | POST | /generate/task/{id}/retry | 重试任务 |
| 生成 | POST | /generate/task/{id}/cancel | 取消任务 |
| 生成 | GET | /generate/task/{id}/summary | 结果摘要 |
| 生成 | GET | /generate/task/{id}/coverage | 覆盖率分析 |
| 脚本 | POST | /scripts/generate | 生成测试脚本 |
| 脚本 | GET/POST | /scripts | 脚本列表/保存 |
| 脚本 | GET/PUT/DELETE | /scripts/{id} | 详情/更新/删除 |
| 脚本 | GET | /scripts/{id}/download | 下载脚本 |
| 模板 | GET/POST | /script-templates | 模板列表/创建 |
| 模板 | GET | /script-templates/all | 全部启用模板 |
| 模板 | PUT/DELETE | /script-templates/{id} | 更新/删除模板 |
| 需求体检 | POST | /req-review/analyze | 上传 PRD 体检并落库 |
| 需求体检 | GET | /req-review/reports | 历史报告列表 |
| 需求体检 | GET | /req-review/reports/{id} | 报告详情 |
| 需求体检 | GET | /req-review/reports/{id}/download | 下载报告 PDF |
| 知识库 | GET/POST | /knowledge/docs | 知识库列表/上传 |
| 知识库 | GET/DELETE | /knowledge/docs/{id} | 详情/删除 |
| 知识库 | GET | /knowledge/docs/{id}/versions | 版本历史 |
| 知识库 | POST | /knowledge/docs/{id}/vectorize | 触发向量化 |
| 知识库 | POST | /knowledge/search | 语义检索 |
| 知识库 | POST | /knowledge/chat | 知识库对话问答（RAG，附引用来源） |
| 统计 | GET | /stats/overview | 平台总览 |
| 统计 | GET | /stats/projects/{id} | 项目统计 |
| 统计 | GET | /stats/efficiency | 效率对比 |
| 统计 | GET | /stats/quality | 质量分布 |
| 统计 | GET | /stats/test-types | 测试类型分布 |
| 统计 | GET | /stats/priorities | 优先级分布 |
| 统计 | GET | /stats/trend | 生成趋势 |
| 系统 | GET | /system/models | 模型配置（只读） |
| 系统 | GET | /system/agents | 智能体配置 |
| 系统 | GET | /system/config | 系统配置 |
| 系统 | GET | /system/health | 健康检查 |
| 通知 | GET | /notifications | 通知列表 |
| 通知 | GET | /notifications/unread-count | 未读数量 |
| 通知 | PUT | /notifications/{id}/read | 标记已读 |
| 通知 | PUT | /notifications/read-all | 全部已读 |
| 日志 | GET | /logs | 操作日志列表 |
| 日志 | DELETE | /logs | 清空日志 |
| 日志 | GET | /logs/export | 导出日志CSV |

---

## 22. 示例：完整调用流程

**场景：工程师生成楼宇对讲系统测试用例**

1. **登录**：`POST /auth/login` 获取 Token。
2. **创建项目**：`POST /projects`，创建"楼宇对讲门禁系统"项目。
3. **获取需求文档**：上传 PDF（`POST /documents/upload`）或通过平台链接导入（`POST /documents/parse-url`）。
4. **触发解析**：`POST /documents/{id}/parse`，解析并向量化文档。
5. **发起生成**：`POST /generate/task`，选择文档和生成选项。
6. **订阅进度**：通过 SSE 实时查看生成进度。
7. **任务完成**：获取生成结果统计。
8. **用例审核**：人工逐个 `PUT /test-cases/{id}/review` 确认；缺失内容可先 `POST /test-cases/{id}/auto-complete` 由 AI 补全。
9. **导出**：`POST /test-cases/export` 导出 Excel 测试用例。

---

*本接口设计基于《系统架构设计文档》与《完整方案书》编写，具体字段以最终实现为准。*
