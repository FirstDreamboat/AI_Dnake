"""消息通知数据模型"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    id: int
    category: str
    title: str
    content: str | None
    related_id: int | None
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
