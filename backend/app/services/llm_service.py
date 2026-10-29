"""大模型调用服务 - 支持本地 Ollama 与云端 DeepSeek API

统一封装模型调用接口:
- 文本生成 (chat)  : LLM_PROVIDER=ollama 时走本地 qwen2.5，=deepseek 时走 DeepSeek API
- 向量生成 (embed) : 云端优先(硅基流动等 OpenAI 兼容接口)，失败自动回退本地 Ollama bge-m3
- 视觉解析 (describe_image): 仅使用云端硅基流动视觉模型（Qwen3-VL），不回退本地 Ollama
后续可通过 /system 接口查看 Provider 配置。
"""
import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 运行时 LLM 配置覆盖（可通过 /system/llm-config 接口动态切换，无需重启进程）
# 键说明: provider(ollama|deepseek) | llm_model(Ollama 模型) | deepseek_model(DeepSeek 模型)
# 值为 None 时回退到 backend/.env 中的默认配置
_runtime_llm_config: dict[str, str | None] = {
    "provider": None,
    "llm_model": None,
    "deepseek_model": None,
}


def set_runtime_llm_config(**kwargs) -> None:
    """更新运行时 LLM 配置；传 None 表示该键回退到 .env 默认值"""
    for key in _runtime_llm_config:
        if key in kwargs:
            _runtime_llm_config[key] = kwargs[key] or None


def get_runtime_llm_config() -> dict[str, str | None]:
    """获取当前运行时 LLM 配置"""
    return dict(_runtime_llm_config)


class LLMService:
    def __init__(self, base_url: str | None = None):
        # Ollama 地址（用于生成 + embedding）
        self.ollama_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        # DeepSeek API 地址（OpenAI 兼容）
        self.deepseek_url = settings.DEEPSEEK_BASE_URL.rstrip("/")

    @property
    def provider(self) -> str:
        return (_runtime_llm_config["provider"] or settings.LLM_PROVIDER or "ollama").lower()

    @property
    def current_model(self) -> str:
        """当前生效的文本生成模型"""
        if self.provider == "deepseek":
            return _runtime_llm_config["deepseek_model"] or settings.DEEPSEEK_MODEL
        return _runtime_llm_config["llm_model"] or settings.LLM_MODEL

    @property
    def ollama_model(self) -> str:
        """当前生效的 Ollama 模型"""
        return _runtime_llm_config["llm_model"] or settings.LLM_MODEL

    @property
    def deepseek_model(self) -> str:
        """当前生效的 DeepSeek 模型"""
        return _runtime_llm_config["deepseek_model"] or settings.DEEPSEEK_MODEL

    # ---------- 文本生成 ----------
    @staticmethod
    def _friendly_api_error(provider: str, resp) -> RuntimeError:
        """把云 API 的 4xx/5xx 转成用户能看懂的错误（余额不足/Key 无效/限流）"""
        try:
            body = resp.json()
            msg = (body.get("error") or {}).get("message") or body.get("message") or ""
        except Exception:  # noqa: BLE001
            msg = ""
        low = (msg or "").lower()
        if resp.status_code in (402, 403) or "insufficient" in low or "balance" in low or "余额" in (msg or ""):
            hint = f"—— {provider} 余额不足或账号受限，请前往平台充值/检查账号状态"
        elif resp.status_code == 401:
            hint = f"—— {provider} API Key 无效或未配置"
        elif resp.status_code == 429:
            hint = f"—— {provider} 请求限流，请稍后重试或降低并发"
        else:
            hint = ""
        return RuntimeError(f"{provider} API 调用失败 [{resp.status_code}]{hint}: {msg or resp.reason_phrase}")

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        timeout: float = 600,
    ) -> str:
        """生成文本，返回纯文本内容"""
        if self.provider == "deepseek":
            return self._chat_deepseek(
                prompt, system=system, model=model, temperature=temperature,
                json_mode=json_mode, timeout=timeout,
            )
        return self._chat_ollama(
            prompt, system=system, model=model, temperature=temperature,
            json_mode=json_mode, timeout=timeout,
        )

    def _chat_ollama(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        timeout: float = 600,
    ) -> str:
        """调用 Ollama 生成文本，返回纯文本内容"""
        payload: dict[str, Any] = {
            "model": model or self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature or settings.LLM_TEMPERATURE},
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        resp = httpx.post(
            f"{self.ollama_url}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    def _chat_deepseek(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        timeout: float = 600,
    ) -> str:
        """调用 DeepSeek API (OpenAI 兼容 /chat/completions)"""
        api_key = settings.DEEPSEEK_API_KEY
        if not api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中设置")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if json_mode:
            # DeepSeek 要求请求消息中必须出现 "json" 字样
            if not system or "json" not in system.lower():
                messages.append({"role": "system", "content": "You must respond in valid JSON format."})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model or self.deepseek_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.DEEPSEEK_TEMPERATURE,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        resp = httpx.post(
            f"{self.deepseek_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise LLMService._friendly_api_error("DeepSeek", resp)
        content = resp.json()["choices"][0]["message"]["content"]
        return (content or "").strip()

    def chat_json(self, prompt: str, system: str | None = None, **kwargs) -> dict:
        """调用模型并解析 JSON 输出，失败时抛出异常"""
        text = self.chat(prompt, system=system, json_mode=True, **kwargs)
        # 兼容模型输出包含 ```json 代码块的情况
        if "```" in text:
            start = text.find("```")
            text = text[start + 3 :]
            text = text[text.find("\n") + 1 :]
            end = text.rfind("```")
            if end != -1:
                text = text[:end]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"模型返回非法 JSON: {text[:200]}... 原始错误: {e}")

    # ---------- 视觉模型（原型图/设计稿解析）：云端优先、Ollama 兜底 ----------
    _IMAGE_MIME = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }

    def describe_image(self, image_path: str, prompt: str | None = None, timeout: float = 300) -> str:
        """解析图片为文本描述，仅使用云端硅基流动视觉模型

        - VISION_PROVIDER=ollama 或未配置 VISION_API_KEY 时，不解析图片直接返回空串
          （不再回退本地 Ollama：本地 CPU 推理极慢且常不可用，会拖垮解析任务）；
        - 默认走云端 OpenAI 兼容视觉接口（硅基流动 Qwen/Qwen3-VL-32B-Instruct），
          云端失败时直接抛出异常，由调用方决定如何处理（如跳过该图保留原引用）。
        """
        if settings.VISION_PROVIDER.lower() != "ollama" and settings.VISION_API_KEY:
            return self._describe_image_cloud(image_path, prompt, timeout)
        return ""

    def _describe_image_cloud(self, image_path: str, prompt: str | None = None, timeout: float = 300) -> str:
        """调用云端 OpenAI 兼容视觉接口（默认硅基流动）"""
        path = Path(image_path)
        mime = self._IMAGE_MIME.get(path.suffix.lower(), "image/png")
        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        default_prompt = (
            "你是资深测试工程师。请仔细分析这张原型图/设计稿/业务截图，"
            "提取其中的页面功能、操作流程、输入输出项、交互逻辑与业务规则，"
            "用结构化 Markdown 输出（标题、列表、字段说明、流程步骤）。"
        )
        resp = httpx.post(
            f"{settings.VISION_API_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.VISION_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.VISION_CLOUD_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                            {"type": "text", "text": prompt or default_prompt},
                        ],
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 4096,
                "stream": False,
            },
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise LLMService._friendly_api_error("硅基流动(视觉)", resp)
        content = resp.json()["choices"][0]["message"]["content"]
        return (content or "").strip()

    def _describe_image_ollama(self, image_path: str, prompt: str | None = None, timeout: float = 300) -> str:
        """调用 Ollama 多模态模型解析图片，返回文本描述

        依赖: Ollama 已 pull 支持视觉的模型（如 qwen2.5vl:3b），并设置 VISION_ENABLED=true
        """
        model = settings.VISION_MODEL
        default_prompt = (
            "你是资深测试工程师。请仔细分析这张原型图/设计稿/业务截图，"
            "提取其中的页面功能、操作流程、输入输出项、交互逻辑与业务规则，"
            "用结构化 Markdown 输出（标题、列表、字段说明、流程步骤）。"
        )
        data = Path(image_path).read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt or default_prompt,
            "images": [b64],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        resp = httpx.post(
            f"{self.ollama_url}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    def vision_health(self) -> bool:
        """检查视觉模型是否可用

        云端模式：校验 VISION_API_KEY 是否有效（请求 /models）；
        本地模式：检查 Ollama 是否已安装 VISION_MODEL。
        """
        if not settings.VISION_ENABLED:
            return False
        if settings.VISION_PROVIDER.lower() != "ollama" and settings.VISION_API_KEY:
            try:
                resp = httpx.get(
                    f"{settings.VISION_API_BASE_URL.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {settings.VISION_API_KEY}"},
                    timeout=10,
                )
                return resp.status_code == 200
            except httpx.HTTPError:
                return False
        try:
            resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            names = [m["name"] for m in resp.json().get("models", [])]
            return any(settings.VISION_MODEL in n for n in names)
        except httpx.HTTPError:
            return False

    # ---------- 向量生成 ----------
    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """生成文本向量，云端优先、Ollama 兜底

        当配置了 EMBED_API_KEY（EMBED_PROVIDER != ollama）时优先调用云端
        OpenAI 兼容接口；云端失败或未配置时回退本地 Ollama。
        """
        if settings.EMBED_PROVIDER.lower() != "ollama" and settings.EMBED_API_KEY:
            try:
                return self._embed_cloud(texts, model)
            except Exception as e:  # noqa: BLE001 - 云端失败回退本地
                logger.warning("云端 embedding 失败，回退本地 Ollama: %s", e)
        return self._embed_ollama(texts, model)

    def _embed_cloud(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """调用云端 OpenAI 兼容 embedding 接口（默认硅基流动）"""
        base = settings.EMBED_API_BASE_URL.rstrip("/")
        resp = httpx.post(
            f"{base}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.EMBED_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or settings.EMBED_CLOUD_MODEL,
                "input": texts,
                "encoding_format": "float",
            },
            timeout=settings.EMBED_TIMEOUT,
        )
        if resp.status_code >= 400:
            raise LLMService._friendly_api_error("硅基流动(向量化)", resp)
        data = resp.json().get("data", [])
        # 按 index 排序，保证与输入顺序一致
        data = sorted(data, key=lambda d: d.get("index", 0))
        return [d.get("embedding", []) for d in data]

    def _embed_ollama(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """调用 Ollama 生成文本向量 (bge-m3)"""
        resp = httpx.post(
            f"{self.ollama_url}/api/embed",
            json={
                "model": model or settings.EMBEDDING_MODEL,
                "input": texts,
            },
            timeout=settings.EMBED_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        if embeddings is None and data.get("embedding") is not None:
            embeddings = [data["embedding"]]
        return embeddings or []

    # ---------- 模型检查 ----------
    def health(self) -> bool:
        """检查当前文本生成 Provider 是否可用"""
        if self.provider == "deepseek":
            return self.deepseek_health()
        return self.ollama_health()

    def ollama_health(self) -> bool:
        """检查 Ollama 服务是否可用（embedding 依赖）"""
        try:
            resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def deepseek_health(self) -> bool:
        """检查 DeepSeek API 是否可用（验证 API Key）"""
        api_key = settings.DEEPSEEK_API_KEY
        if not api_key:
            return False
        try:
            resp = httpx.get(
                f"{self.deepseek_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        """列出当前 Provider 可用的模型"""
        if self.provider == "deepseek":
            models = [self.deepseek_model, "deepseek-chat", "deepseek-reasoner"]
            return list(dict.fromkeys(models))
        return self.list_ollama_installed()

    def list_ollama_installed(self) -> list[str]:
        """列出 Ollama 已安装的模型（与当前 Provider 无关）"""
        try:
            resp = httpx.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except httpx.HTTPError:
            return []


llm_service = LLMService()
