# 狄耐克AI驱动的研发质量前置平台

基于 **大语言模型（LLM）+ 检索增强生成（RAG）** 的研发质量前置平台，服务狄耐克三大核心产品线（楼宇对讲、智能家居、智慧病房），覆盖需求体检、测试点提取、用例生成、评审与脚本生成全流程，把质量前置到需求阶段。

## 核心价值

| 指标 | 目标提升 |
|---|---|
| 用例编写效率 | 提升 50%+ |
| 测试覆盖率 | 提升 30%+ |
| 人力投入 | 节省 60%+ |
| 漏测率 | 降低 40%+ |

## 功能模块

- **用户认证与权限**：用户名密码 + 图形验证码登录，JWT Token；admin / manager / engineer 三角色，支持基于权限点的细粒度接口级权限控制（非 admin 账号由管理员按权限点分配），账号锁定与强制改密机制
- **需求文档智能解析**：支持 PDF/Word/TXT/Markdown 上传，以及飞书、语雀、TAPD、Confluence 等平台链接一键导入解析；输出业务流程图（FR-1.4）
- **测试点智能提取**：功能 / 边界 / 异常 / 性能 / 安全 / 隐式场景 六类测试点，支持手动创建，测试点管理页支持增删改查与类型筛选
- **测试用例自动生成**（核心）：结合 RAG 知识库自动生成结构化用例，编号遵循 `{产品线代码}-{模块代码}-{序号}` 规则（FR-3.1），支持批量重新生成、Excel 批量导入
- **RAG知识库管理**：历史用例库、PRD文档库、技术规格库、缺陷报告库、最佳实践库；支持混合/向量/关键词三种检索模式（FR-4.3）、版本历史管理（FR-4.4）与**知识库对话问答**（RAG 检索 + LLM 生成，回答附引用来源，支持多轮追问）
- **用例评审与优化**：覆盖率、完整性、规范性、可执行性检查，生成结果展示综合评分、问题清单、缺失覆盖（FR-5.1~5.4），支持人工编辑、驳回、AI 自动补全（缺失的前置条件/步骤/预期结果）、AI 生成质量人工反馈（好用/不好用）
- **测试脚本自动生成**：pytest / 接口 / UI 自动化脚本，支持用户自定义脚本模板（FR-6.4）
- **统计报表**：平台总览、项目统计、AI vs 人工效率对比、质量分布、测试类型/优先级分布、生成趋势
- **消息通知**：生成任务完成等系统通知，未读数角标、一键已读
- **操作日志**：关键写操作审计日志，支持查询、导出 CSV
- **系统设置**：模型服务健康检查（数据库/LLM/DeepSeek/Ollama）、已安装模型列表、智能体配置展示
- **用例导入导出**：支持 Excel 导入，Excel / Markdown / JSON / XMind 多种格式导出

## 技术栈

| 层次 | 技术 |
|---|---|
| 前端 | Vue3 + TypeScript + Element Plus + Pinia + Vite |
| 后端 | FastAPI + SQLAlchemy 2.0 |
| 大模型 | DeepSeek API（deepseek-chat / deepseek-reasoner），可选 Ollama 本地模型 |
| Embedding | BGE-M3（硅基流动云端 API 优先，Ollama 本地兜底） |
| 视觉模型 | Qwen3-VL-32B（硅基流动云端 API 优先，Ollama qwen2.5vl 本地兜底），用于原型图/设计稿解析 |
| 向量库 | Chroma（开发）/ Milvus（生产，规划） |
| 关系库 | SQLite（开发）/ MySQL（生产） |
| 部署 | Docker Compose（前后端 + MySQL 一键编排） |

## 快速开始

### 环境要求

- Python 3.10+、Node.js 18+
- （本地 LLM 模式）Ollama + qwen2.5:7b / bge-m3；云端 DeepSeek 模式无需 Ollama
- 向量生成默认走硅基流动云端 API（`BAAI/bge-m3`，免费额度，秒级），未配置 `EMBED_API_KEY` 时自动回退本地 Ollama bge-m3
- 原型图/设计稿解析默认走硅基流动云端视觉模型（`Qwen/Qwen3-VL-32B-Instruct`），未配置 `VISION_API_KEY` 时自动回退本地 Ollama qwen2.5vl

### 1. 启动后端

```bash
cd backend
python -m venv venv
venv\Scripts\activate                      # Windows；Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                     # 按需修改配置（Windows）；Linux: cp .env.example .env
python run.py                              # 启动 http://localhost:8000
```

> 首次启动会自动创建数据表并初始化管理员账号 **admin / admin123**。
> 登录页默认启用图形验证码（配置 `LOGIN_CAPTCHA_ENABLED` 可关闭）。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev                                # 访问 http://localhost:5173
```

访问 http://localhost:5173 ，接口文档 http://localhost:8000/docs 。

### 3. 数据库配置

- **开发（默认）**：SQLite，`DATABASE_URL=sqlite:///./data/db/app.db`
- **MySQL 生产**：修改 `.env`

```ini
DATABASE_URL=mysql+pymysql://root:1234@localhost:3306/ai_testcase?charset=utf8mb4
```

### 4. Docker 一键部署

```bash
docker compose up -d --build
# 后端 http://localhost:8000，前端 http://localhost:5173，MySQL 数据卷持久化
```

> 详细部署步骤见 [部署与使用说明.md](部署与使用说明.md)

## 文档索引

| 文档 | 说明 |
|---|---|
| [项目需求规格说明书-PRD.md](项目需求规格说明书-PRD.md) | 功能与非功能需求定义 |
| [系统架构设计文档.md](系统架构设计文档.md) | 整体架构与技术选型 |
| [数据库设计文档.md](数据库设计文档.md) | 数据表与向量库设计（15 张表） |
| [API接口设计文档.md](API接口设计文档.md) | RESTful接口定义 |
| [项目开发计划书.md](项目开发计划书.md) | 开发排期与任务分工 |
| [测试计划与方案文档.md](测试计划与方案文档.md) | 测试策略与POC验证方案 |
| [Prompt模板集.md](Prompt模板集.md) | AI智能体Prompt模板 |
| [部署与使用说明.md](部署与使用说明.md) | 部署步骤与使用指南 |
| [方案书.docx](方案书.docx) | 原始项目方案书 |

## 项目目录

```
├── backend/                     # 后端服务（FastAPI）
│   ├── app/
│   │   ├── api/                 # 路由层（15 个模块：认证/用户/权限/项目/文档/测试点/用例/生成/脚本/模板/知识库/统计/系统/通知/日志）
│   │   ├── models/              # ORM 模型（15 张表）
│   │   ├── schemas/             # Pydantic 数据校验
│   │   ├── services/            # 业务服务（LLM调用/RAG检索/文档解析/生成任务/验证码）
│   │   ├── agents/              # AI智能体层（需求解析/测试点提取/用例生成/用例评审）
│   │   ├── rag/                 # RAG检索（分块/向量化/混合检索）
│   │   ├── core/                # JWT安全/权限/依赖注入/异常
│   │   └── utils/               # 种子数据
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py
├── frontend/                    # 前端工程（Vue3 + Element Plus）
│   └── src/
│       ├── api/                 # 接口封装（axios）
│       ├── router/              # 路由 + 角色守卫
│       ├── stores/              # Pinia 状态管理
│       └── views/               # 页面（登录/工作台/项目/文档/测试点/用例/AI生成/知识库/脚本/模板/统计/设置/通知/日志/用户）
├── docker-compose.yml           # Docker 编排（backend + frontend + mysql）
├── data/                        # 数据目录（运行时生成）
│   ├── db/                      # 关系数据库
│   ├── vector/                  # 向量库（Chroma）
│   ├── uploads/                 # 上传文档
│   └── exports/                 # 导出的用例
└── docs/                        # 项目文档（*.md 及 方案书.docx）
```

## 数据表清单（15 张）

| 表名 | 说明 |
|---|---|
| user | 用户（角色/启停/锁定/强制改密） |
| project | 项目（产品线/归档） |
| document | 需求文档（上传/链接/解析状态） |
| test_point | 测试点（六类） |
| test_case | 测试用例（评审状态/反馈） |
| test_case_version | 用例版本快照 |
| generation_task | 生成任务（进度/取消） |
| knowledge_doc | 知识库文档（向量化） |
| knowledge_doc_version | 知识文档版本快照 |
| sys_config | 系统配置 |
| notification | 消息通知 |
| operation_log | 操作日志 |
| script_template | 脚本模板 |
| test_script | 生成的测试脚本 |
| user_permissions | 用户权限点关联 |

## 授权

本项目用于狄耐克内部创新大赛，详细技术方案请参阅《方案书.docx》。
