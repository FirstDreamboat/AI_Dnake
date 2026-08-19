"""知识库相关数据模型"""
from datetime import datetime

from pydantic import BaseModel


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    # FR-4.3 检索模式: hybrid（混合）/ vector（向量）/ keyword（关键词）
    mode: str = "hybrid"
    # 产品线（业务域）过滤: intercom / smart_home / hospital；空=全库检索
    product_line: str | None = None


class KnowledgeHit(BaseModel):
    doc_id: int
    title: str
    chunk_index: int
    content: str
    score: float


class KnowledgeChatMessage(BaseModel):
    """知识问答中的一条历史消息"""

    role: str  # user | assistant
    content: str


class KnowledgeChatRequest(BaseModel):
    """知识库对话问答请求（RAG）：检索 + LLM 生成"""

    question: str
    history: list[KnowledgeChatMessage] = []
    top_k: int = 5
    # FR-4.3 检索模式: hybrid（混合）/ vector（向量）/ keyword（关键词）
    mode: str = "hybrid"
    # 产品线（业务域）过滤: intercom / smart_home / hospital；空=全库检索
    product_line: str | None = None


class KnowledgeChatResponse(BaseModel):
    """知识库对话问答响应：回答正文 + 引用来源"""

    answer: str
    sources: list[KnowledgeHit]


class KnowledgeDocOut(BaseModel):
    id: int
    doc_type: str
    product_line: str | None = None
    title: str
    chunk_count: int
    vector_status: str
    vector_error: str | None = None
    version: int
    content: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocVersionOut(BaseModel):
    """知识文档历史版本（FR-4.4 版本管理）"""

    id: int
    doc_id: int
    version: int
    title: str
    content: str | None = None
    change_log: str
    created_by: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
