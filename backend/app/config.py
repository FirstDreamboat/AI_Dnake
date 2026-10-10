"""应用配置管理"""
import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# 项目根目录 (backend/)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """全局配置，支持从 .env 文件或环境变量读取"""

    # 应用
    APP_NAME: str = "AI驱动的研发质量前置平台"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "please-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # 数据库（默认 SQLite 便于开箱即用；生产配置 MySQL 如 mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4）
    DATABASE_URL: str = "sqlite:///./data/db/app.db"

    # 向量库
    VECTOR_DB_TYPE: str = "chroma"
    VECTOR_DB_PATH: str = "./data/vector"

    # 大模型
    # LLM_PROVIDER: ollama(本地) | deepseek(云端 API)
    LLM_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "qwen2.5:3b"
    LLM_TEMPERATURE: float = 0.6
    EMBEDDING_MODEL: str = "bge-m3"
    # 向量生成服务: ollama(本地) | siliconflow(云端硅基流动) | openai(兼容接口)
    # 云端优先、Ollama 兜底：配置了 API Key 时走云端，失败自动回退本地
    EMBED_PROVIDER: str = "siliconflow"
    EMBED_API_KEY: str = ""
    EMBED_API_BASE_URL: str = "https://api.siliconflow.cn/v1"
    EMBED_CLOUD_MODEL: str = "BAAI/bge-m3"
    # DeepSeek API (OpenAI 兼容接口，无 embedding，向量仍走 Ollama)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TEMPERATURE: float = 0.3
    DEEPSEEK_TIMEOUT: float = 600

    # 视觉模型（原型图/设计稿解析）：云端优先、Ollama 兜底
    VISION_ENABLED: bool = False
    # 视觉服务: siliconflow(云端硅基流动, 优先) | ollama(仅本地)
    VISION_PROVIDER: str = "siliconflow"
    VISION_API_KEY: str = ""
    VISION_API_BASE_URL: str = "https://api.siliconflow.cn/v1"
    VISION_CLOUD_MODEL: str = "Qwen/Qwen3-VL-32B-Instruct"
    VISION_MODEL: str = "qwen2.5vl:3b"  # Ollama 本地兜底模型（需预先 pull）

    # 登录安全
    LOGIN_CAPTCHA_ENABLED: bool = True
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 15

    # RAG
    RAG_TOP_K: int = 5
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 100

    # 向量化(embedding) 分批策略：避免大文档单次请求超时
    EMBED_BATCH_SIZE: int = 16          # 每批 embedding 的文本条数
    EMBED_TIMEOUT: float = 300          # 单次 embedding 请求超时(秒)
    EMBED_MAX_INPUT_CHARS: int = 60000  # 单批输入总字符数上限（超出时截断尾部）
    RAG_CHUNK_MIN_SIZE: int = 80        # 结构化分块时单块最小字符数

    # 存储目录
    UPLOAD_DIR: str = "./data/uploads"
    EXPORT_DIR: str = "./data/exports"

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"

    @property
    def cors_origins(self) -> list[str]:
        """支持从环境变量传入 JSON 格式的 CORS 白名单"""
        raw = os.getenv("CORS_ORIGINS")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return [raw]
        return self.CORS_ORIGINS

    @property
    def upload_dir(self) -> Path:
        p = Path(self.UPLOAD_DIR)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def export_dir(self) -> Path:
        p = Path(self.EXPORT_DIR)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vector_db_path(self) -> Path:
        p = Path(self.VECTOR_DB_PATH)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
