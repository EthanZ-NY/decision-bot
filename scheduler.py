"""
APScheduler setup for:
- Cooldown expiry reminders
- Weekly reports (Monday 9:00)
- Monthly reports (1st of month 9:00)
- Satisfaction follow-ups (7 days after execution)
"""
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from config import config
from feishu_client import feishu
from models import Cooldown, Impulse, ImpulseStatus, Report, ReportType, SessionLocal, User


scheduler = AsyncIOScheduler()


async def check_cooldown_reminders() -> None:
    """Scan for cooldowns that have expired and send reminders."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        expired = db.query(Cooldown).filter(
            Cooldown.end_time <= now,
            Cooldown.reminder_sent == False,
        ).all()

        for cd in expired:
            impulse = db.query(Impulse).filter(Impulse.id == cd.impulse_id).first()
            if not impulse:
                continue

            user = db.query(User).filter(User.id == impulse.user_id).first()
            if not user:
                continue

            text = (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "冷静期提醒\n\n"
                f"72h 前你想：{impulse.content}\n"
            )
            if impulse.amount:
                text += f"金额：约 {impulse.amount:,} 元\n"
            text += (
                "\n现在还想执行吗？\n"
                "输入「确认」—— 执行购买，记录支出\n"
                "输入「不买了」—— 标记为成功拦截\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )

            await feishu.send_message(user.open_id, text)
            cd.reminder_sent = True
            impulse.status = ImpulseStatus.EXPIRED.value
            db.commit()
    finally:
        db.close()


async def send_weekly_reports() -> None:
    """Generate and send weekly reports to all users."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        week_start = now - timedelta(days=7)
        week_label = now.strftime("%Y-W%W")

        users = db.query(User).all()
        for user in users:
            impulses = db.query(Impulse).filter(
                Impulse.user_id == user.id,
                Impulse.created_at >= week_start,
            ).all()

            total = len(impulses)
            executed = sum(1 for i in impulses if i.status == ImpulseStatus.APPROVED.value)
            intercepted = sum(1 for i in impulses if i.status == ImpulseStatus.REJECTED.value)
            cooling = sum(1 for i in impulses if i.status == ImpulseStatus.COOLING.value)
            saved = sum(i.amount or 0 for i in impulses if i.status == ImpulseStatus.REJECTED.value)

            text = (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"本周冲动清单（{week_label}）\n\n"
                f"共记录 {total} 个想法\n"
                f"  执行 {executed} 笔\n"
                f"  拦截 {intercepted} 笔\n"
                f"  冷静中 {cooling} 笔\n\n"
            )
            if saved > 0:
                text += f"拦截成就：避免了 {saved:,} 元的潜在支出\n"

            # Budget remaining
            from models import Budget
            ym = now.strftime("%Y-%m")
            budget = db.query(Budget).filter(
                Budget.user_id == user.id,
                Budget.year_month == ym,
                Budget.category == "impulse",
            ).first()
            if budget:
                remaining = budget.limit_amount - budget.spent_amount
                pct = round(remaining / budget.limit_amount * 100) if budget.limit_amount > 0 else 0
                text += f"\n本月冲动预算剩余：{remaining:,} 元（{pct}%）\n"

            text += "━━━━━━━━━━━━━━━━━━━━━━"

            # Hybrid mode: send report to webhook group if configured, else to user directly
            if feishu.webhook_url:
                await feishu.send_to_webhook(text)
            else:
                await feishu.send_message(user.open_id, text)

            # Record report sent
            report = Report(
                user_id=user.id,
                report_type=ReportType.WEEKLY.value,
                period=week_label,
                total_impulses=total,
                intercepted=intercepted,
                executed=executed,
                saved_amount=saved,
                content=text,
                sent_at=now,
            )
            db.add(report)
            db.commit()
    finally:
        db.close()


async def send_monthly_reports() -> None:
    """Generate and send monthly reports to all users."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        month_start = now.replace(day=1)
        month_label = now.strftime("%Y-%m")

        users = db.query(User).all()
        for user in users:
            impulses = db.query(Impulse).filter(
                Impulse.user_id == user.id,
                Impulse.created_at >= month_start,
            ).all()

            total = len(impulses)
            executed = sum(1 for i in impulses if i.status == ImpulseStatus.APPROVED.value)
            intercepted = sum(1 for i in impulses if i.status == ImpulseStatus.REJECTED.value)
            saved = sum(i.amount or 0 for i in impulses if i.status == ImpulseStatus.REJECTED.value)
            total_spent = sum(i.amount or 0 for i in impulses if i.status == ImpulseStatus.APPROVED.value)

            text = (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"月度拦截报告（{month_label}）\n\n"
                f"本月共记录 {total} 个冲动想法\n"
                f"  执行 {executed} 笔，合计 {total_spent:,} 元\n"
                f"  拦截 {intercepted} 笔\n\n"
            )
            if saved > 0:
                text += f"拦截成就：避免了 {saved:,} 元的潜在支出\n"

            # Budget
            from models import Budget
            budget = db.query(Budget).filter(
                Budget.user_id == user.id,
                Budget.year_month == month_label,
                Budget.category == "impulse",
            ).first()
            if budget:
                remaining = budget.limit_amount - budget.spent_amount
                text += f"\n冲动预算：{budget.limit_amount:,} 元\n"
                text += f"已支出：{budget.spent_amount:,} 元\n"
                text += f"剩余：{remaining:,} 元\n"

            text += "━━━━━━━━━━━━━━━━━━━━━━"

            # Hybrid mode: send report to webhook group if configured, else to user directly
            if feishu.webhook_url:
                await feishu.send_to_webhook(text)
            else:
                await feishu.send_message(user.open_id, text)

            report = Report(
                user_id=user.id,
                report_type=ReportType.MONTHLY.value,
                period=month_label,
                total_impulses=total,
                intercepted=intercepted,
                executed=executed,
                saved_amount=saved,
                content=text,
                sent_at=now,
            )
            db.add(report)
            db.commit()
    finally:
        db.close()


async def check_satisfaction_followups() -> None:
    """Ask for satisfaction 7 days after execution."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        followup_date = now - timedelta(days=7)

        impulses = db.query(Impulse).filter(
            Impulse.status == ImpulseStatus.APPROVED.value,
            Impulse.executed_at <= followup_date,
            Impulse.satisfaction.is_(None),
        ).all()

        for impulse in impulses:
            user = db.query(User).filter(User.id == impulse.user_id).first()
            if not user:
                continue

            text = (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "满意度回访\n\n"
                f"7 天前你执行了：{impulse.content}\n"
            )
            if impulse.amount:
                text += f"金额：{impulse.amount:,} 元\n"
            text += (
                "\n现在感觉怎么样？\n"
                "请回复 1-10 分（10=非常满意，1=非常后悔）\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )

            await feishu.send_message(user.open_id, text)
    finally:
        db.close()


def setup_scheduler() -> None:
    """Register all scheduled jobs."""
    # Cooldown reminders: every 5 minutes
    scheduler.add_job(
        check_cooldown_reminders,
        "interval",
        minutes=5,
        id="cooldown_reminders",
        replace_existing=True,
    )

    # Weekly report: Monday at 9:00
    scheduler.add_job(
        send_weekly_reports,
        CronTrigger(day_of_week=config.WEEKLY_REPORT_DAY, hour=config.WEEKLY_REPORT_HOUR, minute=0),
        id="weekly_report",
        replace_existing=True,
    )

    # Monthly report: 1st of month at 9:00
    scheduler.add_job(
        send_monthly_reports,
        CronTrigger(day=config.MONTHLY_REPORT_DAY, hour=config.MONTHLY_REPORT_HOUR, minute=0),
        id="monthly_report",
        replace_existing=True,
    )

    # Satisfaction follow-up: daily at 10:00
    scheduler.add_job(
        check_satisfaction_followups,
        CronTrigger(hour=10, minute=0),
        id="satisfaction_followup",
        replace_existing=True,
    )

    print("[Scheduler] Jobs registered:")
    for job in scheduler.get_jobs():
        print(f"  - {job.id}: {job.trigger}")
