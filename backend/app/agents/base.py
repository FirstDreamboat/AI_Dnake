"""智能体基类"""
from abc import ABC, abstractmethod

from app.services.llm_service import llm_service


class BaseAgent(ABC):
    """所有智能体的抽象基类，封装 LLM 调用"""

    name: str = "base"
    system_prompt: str = "你是一名专业的嵌入式软件测试工程师。"

    def __init__(self):
        self.llm = llm_service

    @abstractmethod
    def run(self, *args, **kwargs):
        """智能体核心执行逻辑"""
        raise NotImplementedError
