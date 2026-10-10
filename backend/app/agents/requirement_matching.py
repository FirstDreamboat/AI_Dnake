"""测试点 ↔ 需求原文 配对工具

问题背景:
    需求解析(6列) → 测试点提取(3列) 之间存在信息压缩: 生成器只拿到简短的
    测试点描述, 看不到需求原文里的按钮/toast/数值/流程, 于是靠"脑补"设计用例,
    导致大量臆想(自创按钮名、编造提示文案、篡改验证码位数/有效期等)。

解决思路:
    提取器在产出测试点后, 用字符 n-gram 重叠做粗粒度配对, 把每个测试点关联到
    最可能的需求原文(no/name/description/business_flow), 作为隐藏字段随测试点
    一起透传给用例生成器; 生成器将原文作为"需求原文依据"注入 prompt, 使用例
    设计严格锚定原文, 而不是靠常识脑补。
"""
import re

# 预留/暂不实现类标记: 命中任一标记的需求, 其对应功能不得被当作正向功能测试
_RESERVED_MARKERS = (
    "预留", "暂不实现", "暂不开放", "暂不提供", "暂不支持",
    "后续版本", "后续实现", "以后版本", "以后实现",
    "第一期不实现", "第一期暂不", "本期不实现", "一期不",
    "不在本期", "待功能开放", "待开放", "二期",
)


def norm(text: str | None) -> str:
    """归一化文本: 去空白/常见分隔符/英文标点, 转小写, 便于 n-gram 比较"""
    return re.sub(
        r"[\s|,.;:：，。；、()（）\[\]{}<>《》\"'“”‘’\-_+=/\\!?！？*&^%$#@~`]",
        "", text or "",
    ).lower()


def ngrams(text: str | None, n: int = 2) -> set[str]:
    """取文本的字符 n-gram 集合(默认 bigram), 用于中文短文本模糊相似度"""
    t = norm(text)
    if not t:
        return set()
    if len(t) <= n:
        return {t}
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def overlap_ratio(a: str | None, b: str | None, n: int = 2) -> float:
    """a 相对 b 的 n-gram 覆盖率: a 中有多少比例的 n-gram 出现在 b 中"""
    ga, gb = ngrams(a, n), ngrams(b, n)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga)


def req_text(r: dict) -> str:
    """拼接需求的关键文本(编号+名称+描述+流程)用于匹配"""
    return " ".join(str(r.get(k) or "") for k in ("no", "name", "description", "business_flow"))


def is_reserved_req(r: dict) -> bool:
    """需求是否标注了预留/暂不实现等字样"""
    t = req_text(r)
    return any(m in t for m in _RESERVED_MARKERS)


def best_match(text: str | None, requirements: list[dict]) -> tuple[dict | None, float]:
    """在需求清单中找出与 text 最相似的需求, 返回 (需求dict|None, 覆盖率)"""
    best, best_score = None, 0.0
    if not text:
        return None, 0.0
    for r in requirements:
        score = overlap_ratio(text, req_text(r))
        if score > best_score:
            best, best_score = r, score
    return best, best_score
