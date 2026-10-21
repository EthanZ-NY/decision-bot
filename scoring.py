"""
Five-dimension scoring engine.
Dimensions: opportunity_cost, durability, frequency, alternative, exit_cost
Weights from config.
"""
from dataclasses import dataclass
from typing import Optional

from config import config


@dataclass
class DimensionScore:
    opportunity: int   # 1-10
    durability: int    # 1-10
    frequency: int     # 1-10
    alternative: int   # 1-10
    exit_cost: int     # 1-10


@dataclass
class ScoreResult:
    total: int                # 0-100
    level: str                # green / yellow / red
    dimension_scores: DimensionScore
    breakdown: dict[str, float]

    def level_emoji(self) -> str:
        return {"green": "绿灯", "yellow": "黄灯", "red": "红灯"}.get(self.level, "未知")

    def level_description(self) -> str:
        return {
            "green": "建议执行 — 预算充裕且评分较高",
            "yellow": "建议冷静 — 评分中等，设置冷静期再评估",
            "red": "建议放弃 — 评分较低，不建议执行",
        }.get(self.level, "")


def calculate_score(
    opportunity: int,
    durability: int,
    frequency: int,
    alternative: int,
    exit_cost: int,
) -> ScoreResult:
    """
    Calculate weighted total score and decision level.
    All inputs should be 1-10.
    """
    w = config.weights

    weighted_sum = (
        opportunity * w["opportunity"] +
        durability * w["durability"] +
        frequency * w["frequency"] +
        alternative * w["alternative"] +
        exit_cost * w["exit_cost"]
    )

    # Scale from 0-10 to 0-100
    total = round(weighted_sum * 10)
    total = max(0, min(100, total))

    # Decision level thresholds
    if total >= 70:
        level = "green"
    elif total >= 45:
        level = "yellow"
    else:
        level = "red"

    breakdown = {
        "机会成本": round(opportunity * w["opportunity"] * 10, 1),
        "效用持久度": round(durability * w["durability"] * 10, 1),
        "使用频率": round(frequency * w["frequency"] * 10, 1),
        "替代方案": round(alternative * w["alternative"] * 10, 1),
        "退出成本": round(exit_cost * w["exit_cost"] * 10, 1),
    }

    return ScoreResult(
        total=total,
        level=level,
        dimension_scores=DimensionScore(
            opportunity=opportunity,
            durability=durability,
            frequency=frequency,
            alternative=alternative,
            exit_cost=exit_cost,
        ),
        breakdown=breakdown,
    )


def quick_score(content: str, amount: Optional[int]) -> ScoreResult:
    """
    Quick default scoring when user hasn't answered dimension questions.
    Uses heuristic based on amount magnitude and content keywords.
    MVP fallback: returns a moderate yellow score to encourage cooldown.
    """
    # Default moderate scores
    opportunity = 5
    durability = 5
    frequency = 5
    alternative = 5
    exit_cost = 5

    # Adjust based on amount (higher amount = more caution)
    if amount:
        if amount >= 10000:
            opportunity = 4
            exit_cost = 3
        elif amount >= 5000:
            opportunity = 5
            exit_cost = 4
        elif amount <= 500:
            opportunity = 7
            exit_cost = 7

    # Keyword-based adjustments
    content_lower = content.lower()
    high_value_keywords = ["学习", "课程", "书", "技能", "健康", "体检"]
    low_value_keywords = ["零食", "奶茶", "冲动", "随便", "看看", "玩玩"]

    if any(kw in content_lower for kw in high_value_keywords):
        durability = min(10, durability + 2)
        frequency = min(10, frequency + 1)
    if any(kw in content_lower for kw in low_value_keywords):
        durability = max(1, durability - 2)
        frequency = max(1, frequency - 2)

    return calculate_score(opportunity, durability, frequency, alternative, exit_cost)


def format_score_card(result: ScoreResult, amount: Optional[int]) -> str:
    """Format score result as a text card for Feishu reply."""
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"决策评分：{result.total}/100（{result.level_emoji()}）",
        "",
        "各维度得分：",
    ]
    for dim, score in result.breakdown.items():
        lines.append(f"  • {dim}：{score}")

    lines.append("")
    lines.append(result.level_description())

    if amount:
        lines.append("")
        lines.append(f"涉及金额：约 {amount:,} 元")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
