"""
Message handlers for all user intents.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from config import config
from feishu_client import feishu
from models import (
    Budget,
    Cooldown,
    Evaluation,
    Impulse,
    ImpulseStatus,
    SessionLocal,
    User,
)
from parser import detect_intent, parse_message
from scoring import calculate_score, format_score_card, quick_score


# ---------- User management ----------

def get_or_create_user(db: Session, open_id: str, name: str = "") -> User:
    user = db.query(User).filter(User.open_id == open_id).first()
    if not user:
        user = User(open_id=open_id, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# ---------- Budget helpers ----------

def get_current_budget(db: Session, user_id: int) -> Optional[Budget]:
    ym = datetime.utcnow().strftime("%Y-%m")
    return db.query(Budget).filter(
        Budget.user_id == user_id,
        Budget.year_month == ym,
        Budget.category == "impulse",
    ).first()


def format_budget_info(budget: Optional[Budget], amount: Optional[int] = None) -> str:
    if not budget:
        return "本月冲动预算：尚未设置\n输入「设置预算 XXXX」来设置"
    remaining = budget.limit_amount - budget.spent_amount
    pct = round(remaining / budget.limit_amount * 100) if budget.limit_amount > 0 else 0
    lines = [f"本月冲动预算：{budget.limit_amount:,} 元"]
    lines.append(f"已支出：{budget.spent_amount:,} 元")
    lines.append(f"剩余：{remaining:,} 元（{pct}%）")
    if amount and amount > remaining:
        lines.append(f"⚠️ 执行后将超支 {amount - remaining:,} 元")
    elif amount:
        after_pct = round((remaining - amount) / budget.limit_amount * 100) if budget.limit_amount > 0 else 0
        lines.append(f"执行后将降至：{after_pct}%")
    return "\n".join(lines)


# ---------- Handlers ----------

async def handle_impulse(user: User, content: str, amount: Optional[int], category: str, db: Session) -> str:
    """Handle a new impulse recording."""
    # Create impulse record
    impulse = Impulse(
        user_id=user.id,
        content=content,
        amount=amount,
        category=category,
        status=ImpulseStatus.PENDING.value,
    )
    db.add(impulse)
    db.commit()
    db.refresh(impulse)

    # Quick scoring (MVP: default scores, user can refine later)
    score_result = quick_score(content, amount)

    # Save evaluation
    eval_record = Evaluation(
        impulse_id=impulse.id,
        opportunity_cost=score_result.dimension_scores.opportunity,
        durability=score_result.dimension_scores.durability,
        frequency=score_result.dimension_scores.frequency,
        alternative=score_result.dimension_scores.alternative,
        exit_cost=score_result.dimension_scores.exit_cost,
        total_score=score_result.total,
        decision_level=score_result.level,
    )
    db.add(eval_record)
    db.commit()

    # Build reply
    lines = [
        f"已记录：{content}",
    ]
    if amount:
        lines.append(f"金额：约 {amount:,} 元")
    lines.append(f"分类：{category}")
    lines.append("")
    lines.append(format_score_card(score_result, amount))
    lines.append("")

    # Budget info
    budget = get_current_budget(db, user.id)
    lines.append(format_budget_info(budget, amount))
    lines.append("")

    if score_result.level == "green":
        lines.append("输入「确认」立即执行")
        lines.append("输入「冷静」开始 72h 冷静期")
    else:
        lines.append("建议设置 72h 冷静期。")
        lines.append("输入「确认」立即执行")
        lines.append("输入「冷静」开始 72h 冷静期")

    return "\n".join(lines)


async def handle_confirm(user: User, db: Session) -> str:
    """User confirms to execute the most recent pending/cooling impulse."""
    # Find the most recent non-executed impulse
    impulse = db.query(Impulse).filter(
        Impulse.user_id == user.id,
        Impulse.status.in_([ImpulseStatus.PENDING.value, ImpulseStatus.COOLING.value]),
    ).order_by(Impulse.created_at.desc()).first()

    if not impulse:
        return "没有找到待执行的想法。先发送一个想法给我吧。"

    # Update status
    impulse.status = ImpulseStatus.APPROVED.value
    impulse.executed_at = datetime.utcnow()

    # Update budget spent
    budget = get_current_budget(db, user.id)
    if budget and impulse.amount:
        budget.spent_amount += impulse.amount

    db.commit()

    lines = [
        "✅ 已确认执行",
        f"内容：{impulse.content}",
    ]
    if impulse.amount:
        lines.append(f"金额：{impulse.amount:,} 元")
    lines.append("")
    lines.append("7 天后我会来问你满意度，记得回复哦。")

    return "\n".join(lines)


async def handle_reject(user: User, db: Session) -> str:
    """User rejects/abandons the most recent impulse."""
    impulse = db.query(Impulse).filter(
        Impulse.user_id == user.id,
        Impulse.status.in_([
            ImpulseStatus.PENDING.value,
            ImpulseStatus.COOLING.value,
            ImpulseStatus.EXPIRED.value,
        ]),
    ).order_by(Impulse.created_at.desc()).first()

    if not impulse:
        return "没有找到可拦截的想法。"

    impulse.status = ImpulseStatus.REJECTED.value
    db.commit()

    saved = impulse.amount or 0
    # Count total saved this month
    ym = datetime.utcnow().strftime("%Y-%m")
    month_start = datetime.utcnow().replace(day=1)
    total_saved = sum(
        i.amount or 0 for i in db.query(Impulse).filter(
            Impulse.user_id == user.id,
            Impulse.status == ImpulseStatus.REJECTED.value,
            Impulse.created_at >= month_start,
        ).all()
    )

    lines = [
        "🎉 成功拦截！",
        f"放弃：{impulse.content}",
    ]
    if saved > 0:
        lines.append(f"避免支出：{saved:,} 元")
    lines.append("")
    lines.append(f"本月累计拦截：{total_saved:,} 元")
    lines.append("你越来越会理性消费了 👍")

    return "\n".join(lines)


async def handle_budget_set(user: User, amount: int, db: Session) -> str:
    """Set monthly impulse budget."""
    ym = datetime.utcnow().strftime("%Y-%m")
    budget = db.query(Budget).filter(
        Budget.user_id == user.id,
        Budget.year_month == ym,
        Budget.category == "impulse",
    ).first()

    if budget:
        budget.limit_amount = amount
    else:
        budget = Budget(user_id=user.id, year_month=ym, category="impulse", limit_amount=amount)
        db.add(budget)

    db.commit()
    return f"已设置 {ym} 冲动预算上限：{amount:,} 元\n\n{format_budget_info(budget)}"


async def handle_budget_query(user: User, db: Session) -> str:
    """Query current budget status."""
    budget = get_current_budget(db, user.id)
    return format_budget_info(budget)


async def handle_cooling(user: User, db: Session) -> str:
    """User requests to start cooldown on the most recent impulse."""
    impulse = db.query(Impulse).filter(
        Impulse.user_id == user.id,
        Impulse.status.in_([ImpulseStatus.PENDING.value, ImpulseStatus.EXPIRED.value]),
    ).order_by(Impulse.created_at.desc()).first()

    if not impulse:
        return "没有找到待处理的想法。"

    # Create or update cooldown
    existing = db.query(Cooldown).filter(Cooldown.impulse_id == impulse.id).first()
    if existing:
        # Extend cooldown
        existing.end_time = datetime.utcnow() + timedelta(hours=config.COOLDOWN_HOURS)
        existing.reminder_sent = False
    else:
        cd = Cooldown(
            user_id=user.id,
            impulse_id=impulse.id,
            duration_hours=config.COOLDOWN_HOURS,
            end_time=datetime.utcnow() + timedelta(hours=config.COOLDOWN_HOURS),
        )
        db.add(cd)

    impulse.status = ImpulseStatus.COOLING.value
    db.commit()

    end_time_str = (datetime.utcnow() + timedelta(hours=config.COOLDOWN_HOURS)).strftime("%m-%d %H:%M")
    return (
        "⏳ 冷静期已启动\n"
        f"内容：{impulse.content}\n"
        f"到期时间：{end_time_str}\n\n"
        "到期后我会提醒你确认。冷静期间可以输入「确认」提前执行，"
        "或「不买了」直接拦截。"
    )


async def handle_satisfaction(user: User, score: int, db: Session) -> str:
    """Record satisfaction score for the most recent executed impulse."""
    impulse = db.query(Impulse).filter(
        Impulse.user_id == user.id,
        Impulse.status == ImpulseStatus.APPROVED.value,
        Impulse.satisfaction.is_(None),
    ).order_by(Impulse.executed_at.desc()).first()

    if not impulse:
        return "没有找到需要回访的执行记录。"

    impulse.satisfaction = max(1, min(10, score))
    db.commit()

    emoji = "😊" if score >= 8 else "😐" if score >= 5 else "😔"
    return (
        f"{emoji} 已记录满意度：{score}/10\n"
        f"内容：{impulse.content}\n\n"
        "感谢反馈，这会帮我更好地了解你的偏好。"
    )


async def handle_history(user: User, db: Session) -> str:
    """Show recent impulse history."""
    impulses = db.query(Impulse).filter(
        Impulse.user_id == user.id,
    ).order_by(Impulse.created_at.desc()).limit(10).all()

    if not impulses:
        return "还没有记录任何想法。有任何消费冲动就发给我吧！"

    lines = ["📋 最近记录（最近 10 条）", ""]
    for i, imp in enumerate(impulses, 1):
        status_map = {
            ImpulseStatus.PENDING.value: "⏳",
            ImpulseStatus.COOLING.value: "⏳",
            ImpulseStatus.APPROVED.value: "✅",
            ImpulseStatus.REJECTED.value: "🚫",
            ImpulseStatus.EXPIRED.value: "⏰",
        }
        icon = status_map.get(imp.status, "❓")
        amt = f"{imp.amount:,}元" if imp.amount else "金额未知"
        lines.append(f"{icon} {imp.content}（{amt}）— {imp.status}")

    return "\n".join(lines)


async def handle_help(user: User, db: Session) -> str:
    """Show help message."""
    return (
        "🤖 决策助手 — 使用指南\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "【记录想法】\n"
        "直接发送你想买的东西，比如：\n"
        "  想买 Sony A7M4，大概 1 万 5\n"
        "  想报个 Python 课程，3000 块\n"
        "\n"
        "【决策指令】\n"
        "  确认 — 执行当前想法\n"
        "  不买了 / 取消 — 放弃当前想法\n"
        "  冷静 — 启动 72h 冷静期\n"
        "\n"
        "【预算管理】\n"
        "  设置预算 5000 — 设置本月冲动预算\n"
        "  查看预算 — 查看预算余量\n"
        "\n"
        "【查看记录】\n"
        "  历史 / 记录 — 查看最近的想法清单\n"
        "\n"
        "【满意度回访】\n"
        "  执行 7 天后我会问你满意度，回复 1-10 分即可\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )


# ---------- Main dispatcher ----------

async def dispatch_message(open_id: str, text: str, message_id: str = "") -> str:
    """
    Main message dispatcher.
    Returns the reply text.
    """
    db = SessionLocal()
    try:
        intent, params = detect_intent(text)
        user = get_or_create_user(db, open_id)

        if intent == "impulse":
            return await handle_impulse(
                user,
                params.get("content", text),
                params.get("amount"),
                params.get("category", "其他"),
                db,
            )
        elif intent == "confirm":
            return await handle_confirm(user, db)
        elif intent == "reject":
            return await handle_reject(user, db)
        elif intent == "budget_set":
            return await handle_budget_set(user, params["amount"], db)
        elif intent == "budget_query":
            return await handle_budget_query(user, db)
        elif intent == "cooling":
            return await handle_cooling(user, db)
        elif intent == "satisfaction":
            return await handle_satisfaction(user, params.get("score", 5), db)
        elif intent == "history":
            return await handle_history(user, db)
        elif intent == "help":
            return await handle_help(user, db)
        else:
            return (
                "没太听懂 🤔\n"
                "你可以直接发送想买东西的想法，比如「想买 iPhone，大概 8000」\n"
                "输入「帮助」查看完整指令列表。"
            )
    finally:
        db.close()
