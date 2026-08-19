"""需求文档相关数据模型"""
from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    project_id: int
    title: str
    file_type: str
    source_type: str | None
    source_url: str | None = None
    parse_status: str
    parse_result: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ParseResultOut(BaseModel):
    document_id: int
    chunk_count: int
    vector_status: str
    message: str


class URLParseRequest(BaseModel):
    """平台链接解析请求 (FR-1.2)"""

    project_id: int
    url: str
    title: str | None = None
