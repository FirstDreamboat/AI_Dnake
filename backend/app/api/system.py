"""系统管理接口"""
from fastapi import APIRouter, Depends
import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import BusinessError
from app.database import get_db
from app.models.sys_config import SysConfig
from app.models.user import User
from app.schemas.common import ok
from app.services.llm_service import (
    get_runtime_llm_config,
    llm_service,
    set_runtime_llm_config,
)

router = APIRouter()


class LLMConfigIn(BaseModel):
    """LLM 模型配置（运行时动态切换）"""

    provider: str = Field(..., description="服务商: ollama | deepseek")
    llm_model: str | None = Field(None, description="Ollama 模型，如 qwen2.5:3b / qwen2.5:7b")
    deepseek_model: str | None = Field(None, description="DeepSeek 模型，如 deepseek-chat")


def _llm_config_payload() -> dict:
    """组装 LLM 配置响应"""
    runtime = get_runtime_llm_config()
    return {
        "provider": llm_service.provider,
        "llm_model": runtime["llm_model"] or settings.LLM_MODEL,
        "deepseek_model": runtime["deepseek_model"] or settings.DEEPSEEK_MODEL,
        "current_model": llm_service.current_model,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "deepseek_api_key_configured": bool(settings.DEEPSEEK_API_KEY),
        "installed": llm_service.list_models(),
        "ollama_installed": llm_service.list_ollama_installed(),
    }


@router.get("/health")
def health(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """系统健康检查"""
    # 数据库检查
    try:
        db.execute(SysConfig.__table__.select().limit(1))
        db_status = "ok"
    except Exception:
        db_status = "error"
    # LLM Provider 检查
    provider = llm_service.provider
    llm_ok = llm_service.health()
    # Ollama 承担 embedding 与视觉解析的本地兜底，单独检查
    ollama_ok = llm_service.ollama_health()
    # Embedding 云端优先、Ollama 兜底
    if settings.EMBED_PROVIDER.lower() != "ollama" and settings.EMBED_API_KEY:
        embed_ok = True
    else:
        embed_ok = ollama_ok
    return ok(
        {
            "database": db_status,
            "provider": provider,
            "llm": "ok" if llm_ok else "unavailable",
            "deepseek": "ok" if (provider == "deepseek" and llm_ok) else ("unavailable" if provider == "deepseek" else "not_used"),
            "ollama": "ok" if ollama_ok else "unavailable",
            "llm_model": llm_service.current_model,
            "embedding": "ok" if embed_ok else "unavailable",
            "embedding_provider": settings.EMBED_PROVIDER,
            "embedding_model": settings.EMBEDDING_MODEL,
            "vision": {
                "enabled": settings.VISION_ENABLED,
                "provider": settings.VISION_PROVIDER,
                "model": settings.VISION_MODEL,
                "cloud_model": settings.VISION_CLOUD_MODEL,
                "api_key_configured": bool(settings.VISION_API_KEY),
                "available": llm_service.vision_health(),
            },
        }
    )


@router.get("/models")
def list_models(
    user: User = Depends(get_current_user),
):
    """查看已安装模型与当前配置"""
    provider = llm_service.provider
    configured = {
        "provider": provider,
        "llm_model": llm_service.current_model,
        "ollama_model": llm_service.ollama_model,
        "deepseek_model": llm_service.deepseek_model,
        "embedding_provider": settings.EMBED_PROVIDER,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_api_key_configured": bool(settings.EMBED_API_KEY),
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "deepseek_api_key_configured": bool(settings.DEEPSEEK_API_KEY),
        "vision_enabled": settings.VISION_ENABLED,
        "vision_provider": settings.VISION_PROVIDER,
        "vision_model": settings.VISION_MODEL,
        "vision_api_key_configured": bool(settings.VISION_API_KEY),
    }
    return ok(
        {
            "configured": configured,
            "installed": llm_service.list_models(),
        }
    )


@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("settings")),
):
    configs = db.query(SysConfig).all()
    return ok([{"key": c.config_key, "value": c.config_value, "description": c.description} for c in configs])


@router.get("/manual-baseline")
def get_manual_baseline(
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("settings")),
):
    """读取人工效率基线（未标定时返回默认值：20 条/180 分钟）"""
    cfg = {
        c.config_key: c.config_value
        for c in db.query(SysConfig)
        .filter(SysConfig.config_key.in_(["manual_cases_per_day", "manual_time_minutes"]))
        .all()
    }
    try:
        cases = int(cfg.get("manual_cases_per_day") or 20)
    except ValueError:
        cases = 20
    try:
        minutes = int(cfg.get("manual_time_minutes") or 180)
    except ValueError:
        minutes = 180
    return ok({"avg_cases_per_day": cases, "avg_time_minutes": minutes})


class ManualBaselineIn(BaseModel):
    """人工效率基线（测试部实测标定，用于 AI vs 人工效率对比）"""

    avg_cases_per_day: int = Field(..., ge=1, le=10000, description="人均每日编写用例数")
    avg_time_minutes: int = Field(..., ge=1, le=100000, description="编写一批用例平均耗时（分钟）")


@router.put("/manual-baseline")
def set_manual_baseline(
    payload: ManualBaselineIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("settings")),
):
    """保存人工效率基线（写入 sys_config，供 /stats/efficiency 读取）"""
    items = {
        "manual_cases_per_day": (str(payload.avg_cases_per_day), "人工效率基线：人均每日编写用例数（实测标定）"),
        "manual_time_minutes": (str(payload.avg_time_minutes), "人工效率基线：编写一批用例平均耗时/分钟（实测标定）"),
    }
    for key, (value, desc) in items.items():
        row = db.query(SysConfig).filter(SysConfig.config_key == key).first()
        if row:
            row.config_value = value
            row.description = desc
        else:
            db.add(SysConfig(config_key=key, config_value=value, description=desc))
    db.commit()
    return ok(message="人工效率基线已保存")


@router.get("/agents")
def get_agents(
    user: User = Depends(get_current_user),
):
    """查看智能体配置"""
    from app.agents import requirement_parser, test_case_generator, test_case_reviewer, test_point_extractor

    return ok(
        {
            "agents": [
                {"name": "需求解析智能体", "key": "requirement_parser", "model": llm_service.current_model},
                {"name": "测试点提取智能体", "key": "test_point_extractor", "model": llm_service.current_model},
                {"name": "用例生成智能体", "key": "test_case_generator", "model": llm_service.current_model},
                {"name": "用例评审智能体", "key": "test_case_reviewer", "model": llm_service.current_model},
            ]
        }
    )


@router.get("/llm-balance")
def get_llm_balance(
    user: User = Depends(get_current_user),
):
    """云服务余额查询：DeepSeek(/user/balance) + 硅基流动(/v1/user/info)

    用于演示前检查账户余量；未配置 Key 或接口异常时返回 available=False 与原因。
    """
    result: dict = {}

    # DeepSeek
    key = settings.DEEPSEEK_API_KEY
    if not key:
        result["deepseek"] = {"configured": False, "error": "未配置 DEEPSEEK_API_KEY"}
    else:
        try:
            r = httpx.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if r.status_code == 200:
                d = r.json()
                info = (d.get("balance_infos") or [{}])[0]
                result["deepseek"] = {
                    "configured": True,
                    "available": bool(d.get("is_available")),
                    "currency": info.get("currency", "CNY"),
                    "balance": float(info.get("total_balance") or 0),
                }
            else:
                result["deepseek"] = {"configured": True, "available": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:  # noqa: BLE001
            result["deepseek"] = {"configured": True, "available": False, "error": str(e)[:120]}

    # 硅基流动（向量/视觉共用 Key）
    key = settings.EMBED_API_KEY or settings.VISION_API_KEY
    if not key:
        result["siliconflow"] = {"configured": False, "error": "未配置 EMBED_API_KEY / VISION_API_KEY"}
    else:
        try:
            base = settings.EMBED_API_BASE_URL.rstrip("/")
            r = httpx.get(f"{base}/user/info", headers={"Authorization": f"Bearer {key}"}, timeout=10)
            if r.status_code == 200:
                d = (r.json() or {}).get("data") or {}
                balance = d.get("remainBalance") or d.get("balance") or d.get("chargeBalance") or 0
                result["siliconflow"] = {
                    "configured": True,
                    "available": d.get("status") in (None, "normal"),
                    "currency": "CNY",
                    "balance": float(balance or 0),
                }
            elif r.status_code == 410:
                # 硅基流动已下线 /user/info 等余额查询接口，无替代端点
                result["siliconflow"] = {
                    "configured": True,
                    "query_unavailable": True,
                    "error": "平台已下线余额查询接口，请登录 siliconflow.cn 控制台查看",
                }
            else:
                result["siliconflow"] = {"configured": True, "available": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:  # noqa: BLE001
            result["siliconflow"] = {"configured": True, "available": False, "error": str(e)[:120]}

    return ok(result)


@router.get("/llm-config")
def get_llm_config(
    user: User = Depends(get_current_user),
):
    """获取当前 LLM 配置（provider 与模型，支持运行时动态切换）"""
    return ok(_llm_config_payload())


@router.put("/llm-config")
def update_llm_config(
    payload: LLMConfigIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("settings")),
):
    """保存 LLM 配置（写入 sys_config 持久化并即时生效，无需重启）"""
    provider = (payload.provider or "").strip().lower()
    if provider not in ("ollama", "deepseek"):
        raise BusinessError("provider 仅支持 ollama 或 deepseek")
    llm_model = (payload.llm_model or "").strip()
    deepseek_model = (payload.deepseek_model or "").strip()

    save_items = {
        "llm_provider": provider,
        "llm_model": llm_model or settings.LLM_MODEL,
        "deepseek_model": deepseek_model or settings.DEEPSEEK_MODEL,
    }
    descriptions = {
        "llm_provider": "LLM 服务商: ollama | deepseek（界面动态切换）",
        "llm_model": "Ollama 对话模型（如 qwen2.5:3b / qwen2.5:7b）",
        "deepseek_model": "DeepSeek 对话模型（如 deepseek-chat）",
    }
    for key, value in save_items.items():
        row = db.query(SysConfig).filter(SysConfig.config_key == key).first()
        if row:
            row.config_value = value
        else:
            db.add(SysConfig(config_key=key, config_value=value, description=descriptions[key]))
    db.commit()

    # 更新内存运行时配置，立即生效
    set_runtime_llm_config(
        provider=provider,
        llm_model=llm_model or None,
        deepseek_model=deepseek_model or None,
    )
    return ok(_llm_config_payload())
