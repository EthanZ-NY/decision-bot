"""
Natural language parser: extract idea content + amount from user messages.
Uses jieba + regex, no LLM dependency.
"""
import re
from dataclasses import dataclass
from typing import Optional

import jieba


@dataclass
class ParseResult:
    content: str          # 想法内容
    amount: Optional[int] # 金额（元），None if not found
    raw: str              # 原始消息


# Keywords that indicate a purchase intent
INTENT_KEYWORDS = [
    "想", "打算", "准备", "计划", "考虑", "看看", "买", "购", "入", "换",
    "想要", "想买", "想换", "想入", "想购", "准备买", "打算买",
    "想买", "想换", "想入", "想购", "准备买", "打算买",
]

# Category keywords
CATEGORY_MAP = {
    "电子数码": ["手机", "电脑", "相机", "镜头", "耳机", "平板", "键盘", "鼠标",
               "显示器", "音箱", "充电宝", "数据线", "游戏机", "switch", "ps5",
               "macbook", "iphone", "ipad", "sony", "canon", "nikon", "无人机"],
    "课程学习": ["课", "课程", "班", "培训", "学习", "教程", "训练营", "会员",
               "知识付费", "订阅", "考证", "考试", "书", "教材"],
    "生活消费": ["衣服", "鞋", "包", "化妆品", "护肤品", "香水", "手表", "首饰",
               "家具", "家电", "厨具", "餐具", "床", "沙发", "灯", "窗帘"],
    "出行旅游": ["旅行", "旅游", "机票", "酒店", "民宿", "门票", "签证", "护照",
               "租车", "火车票", "高铁", " cruise", "游轮"],
    "健康运动": ["健身", "瑜伽", "跑步", "游泳", "健身房", "私教", "蛋白粉",
               "补剂", "体检", "按摩", "理疗", "牙医"],
    "餐饮美食": ["餐厅", "饭店", "火锅", "烧烤", "奶茶", "咖啡", "甜品", "蛋糕"],
}


def _extract_amount(text: str) -> Optional[int]:
    """
    Extract amount in yuan from text.
    Supports: 15000, 1万5, 1.5万, 15k, 1500元, 一万五
    """
    # Replace commas with space to avoid merging numbers like "16，8000" → "168000"
    text = text.lower().replace(",", " ").replace("，", " ")

    # Pattern: "1.5万" or "1万5" or "一万五"
    wan_patterns = [
        r"(\d+)\s*[w万]\s*(\d+)",         # 1万5 (must be first, more specific)
        r"(\d+\.?\d*)\s*[w万]",           # 1.5万, 2万
        r"([一二两三四五六七八九十百千万]+)\s*[w万]",  # 一万, 两万
    ]

    for pat in wan_patterns:
        m = re.search(pat, text)
        if m:
            if len(m.groups()) == 2:
                # e.g. "1万5" -> 15000
                return int(m.group(1)) * 10000 + int(m.group(2)) * 1000
            else:
                val = m.group(1)
                try:
                    return int(float(val) * 10000)
                except ValueError:
                    # Chinese numerals fallback
                    cn_map = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
                    num = 0
                    for c in val:
                        if c in cn_map:
                            num = num * 10 + cn_map[c]
                    return num * 10000 if num > 0 else None

    # Pattern: "15k"
    m = re.search(r"(\d+)\s*[k千]", text)
    if m:
        return int(m.group(1)) * 1000

    # Pattern: pure number near 元/块/块钱
    m = re.search(r"(\d{3,})\s*[元块]", text)
    if m:
        return int(m.group(1))

    # Pattern: any 4+ digit number (likely an amount)
    m = re.search(r"(\d{4,})", text)
    if m:
        return int(m.group(1))

    # Pattern: "几百" -> 500 (approximate)
    if re.search(r"几\s*[百]", text):
        return 500
    if re.search(r"几\s*[千]", text):
        return 5000
    if re.search(r"几\s*[万]", text):
        return 50000

    return None


def _extract_content(text: str) -> str:
    """Extract the idea description, removing amount and filler words."""
    # Remove amount expressions (most specific first)
    cleaned = re.sub(r"\d+\s*[w万]\s*\d+", "", text, flags=re.IGNORECASE)       # 1万5
    cleaned = re.sub(r"\d+\.?\d*\s*[w万k千]", "", cleaned, flags=re.IGNORECASE)  # 1.5万, 15k
    cleaned = re.sub(r"[一二两三四五六七八九十百千万]+\s*[w万]", "", cleaned)      # 一万五
    cleaned = re.sub(r"\d{3,}\s*[元块]", "", cleaned)
    cleaned = re.sub(r"大概|大约|约|差不多|左右|大概要|差不多要", "", cleaned)
    cleaned = re.sub(r"[,.，。!！?？]", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned if cleaned else text


def _classify_category(text: str) -> str:
    """Classify impulse into category based on keywords."""
    text_lower = text.lower()
    for category, keywords in CATEGORY_MAP.items():
        for kw in keywords:
            if kw in text_lower:
                return category
    return "其他"


def parse_message(text: str) -> ParseResult:
    """
    Parse a user message to extract idea content and amount.
    Returns ParseResult with content, amount, and raw text.
    """
    amount = _extract_amount(text)
    content = _extract_content(text)
    return ParseResult(content=content, amount=amount, raw=text)


def classify_message(text: str) -> str:
    """Classify the message category."""
    return _classify_category(text)


# --- Intent detection for command routing ---

BUDGET_SET_PATTERN = re.compile(r"设置.*预算\s*(\d+)")
BUDGET_QUERY_PATTERN = re.compile(r"查看.*预算|预算.*多少|还剩.*预算")
CONFIRM_PATTERN = re.compile(r"^确认$|^执行$|^买$|^确定$")
REJECT_PATTERN = re.compile(r"^不买了$|^取消$|^放弃$|^拦截$")
HELP_PATTERN = re.compile(r"帮助|怎么用|指令|说明")
HISTORY_PATTERN = re.compile(r"历史|记录|清单|列表")
COOLING_PATTERN = re.compile(r"冷静|冷静期")
SATISFACTION_PATTERN = re.compile(r"^(\d+)[分]?$|^([很非常比较]).*满意|^一般|^不满意")


def detect_intent(text: str) -> tuple[str, Optional[dict]]:
    """
    Detect user intent from message text.
    Returns (intent, params_dict).
    Intents: impulse, budget_set, budget_query, confirm, reject,
             help, history, cooling, satisfaction, unknown
    """
    t = text.strip()

    m = BUDGET_SET_PATTERN.search(t)
    if m:
        return "budget_set", {"amount": int(m.group(1))}

    if BUDGET_QUERY_PATTERN.search(t):
        return "budget_query", {}

    if CONFIRM_PATTERN.match(t):
        return "confirm", {}

    if REJECT_PATTERN.match(t):
        return "reject", {}

    if HELP_PATTERN.search(t):
        return "help", {}

    if HISTORY_PATTERN.search(t):
        return "history", {}

    if COOLING_PATTERN.search(t):
        return "cooling", {}

    m = SATISFACTION_PATTERN.match(t)
    if m:
        score = m.group(1)
        if score and score.isdigit():
            return "satisfaction", {"score": int(score)}
        return "satisfaction", {"text": t}

    # Default: treat as impulse recording
    parsed = parse_message(t)
    if parsed.content or parsed.amount:
        return "impulse", {"content": parsed.content, "amount": parsed.amount, "category": classify_message(t)}

    return "unknown", {}
