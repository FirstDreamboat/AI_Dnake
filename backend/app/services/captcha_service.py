"""图片验证码服务：生成与校验（内存存储，适合单机部署）"""
import base64
import io
import random
import string
import threading
import time

from PIL import Image, ImageDraw, ImageFont

from app.config import settings

# captcha_id -> (code, expire_at)
_STORE: dict[str, tuple[str, float]] = {}
_LOCK = threading.Lock()
_EXPIRE_SECONDS = 300  # 5 分钟有效期


def _random_code(length: int = 4) -> str:
    """生成 4 位数字验证码（避免 0/O、1/I 混淆）"""
    return "".join(random.choices("23456789ABCDEFGHJKLMNPQRSTUVWXYZ", k=length))


def generate_captcha() -> dict:
    """生成验证码图片，返回 captcha_id 与 base64 图片数据"""
    _cleanup()
    code = _random_code()
    captcha_id = f"{int(time.time() * 1000)}-{random.randint(10000, 99999)}"
    with _LOCK:
        _STORE[captcha_id] = (code, time.time() + _EXPIRE_SECONDS)

    img = _draw_image(code)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return {"captcha_id": captcha_id, "image": f"data:image/png;base64,{b64}"}


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """按优先级加载可用的 TrueType 字体；容器内无 arial，优先用 Dockerfile 安装的 DejaVu"""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Debian/容器
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf",                          # Windows 开发环境
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_image(code: str) -> Image.Image:
    """绘制带干扰线的验证码图片"""
    width, height = 160, 48
    img = Image.new("RGB", (width, height), (245, 247, 250))
    draw = ImageDraw.Draw(img)
    # 干扰线
    for _ in range(5):
        x1, y1 = random.randint(0, width // 2), random.randint(0, height)
        x2, y2 = random.randint(width // 2, width), random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=random.choice([(150, 150, 150), (180, 180, 180)]), width=1)
    # 干扰点
    for _ in range(40):
        draw.point(
            (random.randint(0, width), random.randint(0, height)),
            fill=random.choice([(200, 200, 200), (160, 160, 160)]),
        )
    # 字符
    font = _load_font(34)
    char_w = width // (len(code) + 1)
    for i, ch in enumerate(code):
        x = char_w // 2 + i * char_w + random.randint(-4, 4)
        y = random.randint(5, 12)
        color = random.choice([(30, 80, 180), (200, 60, 60), (30, 150, 90), (120, 60, 180)])
        draw.text((x, y), ch, font=font, fill=color)
    return img


def verify_captcha(captcha_id: str, code: str) -> bool:
    """校验验证码，校验后无论对错都立即删除（一次性）"""
    if not captcha_id or not code:
        return False
    with _LOCK:
        item = _STORE.pop(captcha_id, None)
    if not item:
        return False
    saved, expire_at = item
    if time.time() > expire_at:
        return False
    return saved.lower() == code.strip().lower()


def _cleanup() -> None:
    """清理过期验证码"""
    now = time.time()
    with _LOCK:
        expired = [k for k, (_, t) in _STORE.items() if t < now]
        for k in expired:
            _STORE.pop(k, None)


def captcha_enabled() -> bool:
    return bool(settings.LOGIN_CAPTCHA_ENABLED)
