"""用例文件服务：上传存储、xlsx/csv 解析转换、单人编辑锁

锁机制（内存态，单机部署）：
- 打开文件时尝试抢锁，成功者可编辑，失败者只读
- 持锁者每 30s 心跳续期，TTL 90s，断线/崩溃自动超时释放
- 保存必须持有有效锁，防止覆盖他人修改
"""
import random
import threading
import time
from pathlib import Path

import pandas as pd
from fastapi import UploadFile

from app.config import settings
from app.core.exceptions import BusinessError

ALLOWED_SUFFIXES = {".xlsx", ".csv"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# file_id -> {"user_id", "username", "expires_at"}
_LOCKS: dict[int, dict] = {}
_LOCK_TTL = 90  # 秒
_SAVE_LOCK = threading.Lock()


# ===== 编辑锁 =====

def try_acquire_lock(file_id: int, user_id: int, username: str) -> dict:
    """尝试获取编辑锁：成功返回 acquired=True，被占则返回持有人信息（只读模式）"""
    now = time.time()
    with _SAVE_LOCK:
        _purge_expired_locked(now)
        lock = _LOCKS.get(file_id)
        if lock is None:
            _LOCKS[file_id] = {"user_id": user_id, "username": username, "expires_at": now + _LOCK_TTL}
            return {"acquired": True, "holder_id": user_id, "holder_name": username, "ttl": _LOCK_TTL}
        if lock["user_id"] == user_id:  # 自己重复打开，续期
            lock["expires_at"] = now + _LOCK_TTL
            return {"acquired": True, "holder_id": user_id, "holder_name": username, "ttl": _LOCK_TTL}
        return {"acquired": False, "holder_id": lock["user_id"], "holder_name": lock["username"], "ttl": 0}


def heartbeat_lock(file_id: int, user_id: int) -> bool:
    """持锁者心跳续期；非持锁者返回 False（前端应转入只读）"""
    with _SAVE_LOCK:
        lock = _LOCKS.get(file_id)
        if lock and lock["user_id"] == user_id:
            lock["expires_at"] = time.time() + _LOCK_TTL
            return True
        return False


def release_lock(file_id: int, user_id: int) -> bool:
    """释放锁（仅持锁者本人可释放）"""
    with _SAVE_LOCK:
        lock = _LOCKS.get(file_id)
        if lock and lock["user_id"] == user_id:
            _LOCKS.pop(file_id, None)
            return True
        return False


def check_lock_for_save(file_id: int, user_id: int) -> None:
    """保存前校验锁归属，无效则拒绝写入"""
    with _SAVE_LOCK:
        _purge_expired_locked(time.time())
        lock = _LOCKS.get(file_id)
    if not lock or lock["user_id"] != user_id:
        raise BusinessError("编辑锁已失效（可能已被他人占用），请刷新页面重新获取锁后再保存", http_status=409)


def _purge_expired_locked(now: float) -> None:
    """清理过期锁（调用方需已持有 _SAVE_LOCK）"""
    expired = [fid for fid, lk in _LOCKS.items() if lk["expires_at"] < now]
    for fid in expired:
        _LOCKS.pop(fid, None)


def lock_info(file_id: int, user_id: int) -> dict:
    """查询当前锁状态（列表页展示用）"""
    with _SAVE_LOCK:
        _purge_expired_locked(time.time())
        lock = _LOCKS.get(file_id)
    if not lock:
        return {"locked": False, "by_me": False, "holder_name": None}
    return {
        "locked": True,
        "by_me": lock["user_id"] == user_id,
        "holder_name": lock["username"],
    }


# ===== 文件存储 =====

def save_upload_file(file: UploadFile, original_name: str) -> tuple[Path, str]:
    """保存上传的用例表；csv 自动转换为 xlsx。返回 (存储路径, 展示文件名)"""
    suffix = Path(original_name or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise BusinessError("仅支持 .xlsx / .csv 格式，xls 请先用 Excel/WPS 另存为 xlsx")
    data = file.file.read()
    if len(data) > MAX_FILE_SIZE:
        raise BusinessError("文件超过 10MB 上限")
    if not data:
        raise BusinessError("文件内容为空")

    target_dir = settings.upload_dir / "case_files"
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(original_name).stem or "case_file"
    stored_name = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}_{stem[:50]}.xlsx"
    stored_path = target_dir / stored_name

    if suffix == ".csv":
        _csv_to_xlsx(data, stored_path)
    else:
        _validate_xlsx(data)
        stored_path.write_bytes(data)

    display_name = f"{stem}.xlsx"
    return stored_path, display_name


def _validate_xlsx(data: bytes) -> None:
    """校验 xlsx 可正常解析，并限制规模避免超大表拖垮前端"""
    try:
        sheets = pd.read_excel(io_bytes(data), sheet_name=None, header=None, engine="openpyxl")
    except Exception as e:
        raise BusinessError(f"Excel 解析失败，请确认文件未损坏: {e}")
    if len(sheets) > 30:
        raise BusinessError("工作表数量超过 30 个，请精简后再上传")
    for name, df in sheets.items():
        if df.size > 200_000:  # 单表 20 万单元格
            raise BusinessError(f"工作表「{name}」过大（{df.shape[0]}行×{df.shape[1]}列），请拆分后再上传")


def _csv_to_xlsx(data: bytes, target: Path) -> None:
    """csv 统一转存为 xlsx（后端在线编辑只处理 xlsx 一种格式）"""
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            df = pd.read_csv(io_bytes(data), encoding=encoding, header=None, dtype=str, keep_default_na=False)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    else:
        raise BusinessError("CSV 编码无法识别，请使用 UTF-8/GBK 编码后重新上传")
    if df.size > 200_000:
        raise BusinessError(f"CSV 过大（{df.shape[0]}行×{df.shape[1]}列），请拆分后再上传")
    df.to_excel(target, header=False, index=False)


def io_bytes(data: bytes):
    import io
    return io.BytesIO(data)


def resolve_stored_path(stored_path: str) -> Path:
    """将库中相对路径解析为绝对路径，并防御路径穿越"""
    base = settings.upload_dir.resolve()
    target = (base / stored_path).resolve()
    if not str(target).startswith(str(base)):
        raise BusinessError("非法文件路径")
    return target
