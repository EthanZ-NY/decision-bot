"""
SQLAlchemy data models.
Tables: users, impulses, evaluations, cooldowns, budgets, reports
"""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from config import config

Base = declarative_base()
engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class ImpulseStatus(str, PyEnum):
    PENDING = "pending"       # 刚录入，未评分
    COOLING = "cooling"       # 冷静期中
    APPROVED = "approved"     # 用户确认执行
    REJECTED = "rejected"     # 用户放弃/拦截
    EXPIRED = "expired"       # 冷静期过期未处理


class ImpulseType(str, PyEnum):
    IMPULSE = "impulse"       # 冲动型
    PLANNED = "planned"       # 蓄谋型


class ReportType(str, PyEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    open_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128))
    created_at = Column(DateTime, default=datetime.utcnow)

    impulses = relationship("Impulse", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")


class Impulse(Base):
    __tablename__ = "impulses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)           # 原始消息
    amount = Column(Integer)                         # 金额（元），解析失败为 NULL
    category = Column(String(32), default="其他")      # 自动分类
    status = Column(String(16), default=ImpulseStatus.PENDING.value)
    impulse_type = Column(String(16), default=ImpulseType.IMPULSE.value)
    executed_at = Column(DateTime)                   # 实际执行时间
    satisfaction = Column(Integer)                   # 1-10，NULL=未回访
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="impulses")
    evaluation = relationship("Evaluation", back_populates="impulse", uselist=False, cascade="all, delete-orphan")
    cooldown = relationship("Cooldown", back_populates="impulse", uselist=False, cascade="all, delete-orphan")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    impulse_id = Column(Integer, ForeignKey("impulses.id"), unique=True, nullable=False)
    opportunity_cost = Column(Integer)    # 1-10
    durability = Column(Integer)          # 1-10
    frequency = Column(Integer)           # 1-10
    alternative = Column(Integer)         # 1-10
    exit_cost = Column(Integer)           # 1-10
    total_score = Column(Integer)         # 0-100
    decision_level = Column(String(8))    # green / yellow / red
    created_at = Column(DateTime, default=datetime.utcnow)

    impulse = relationship("Impulse", back_populates="evaluation")


class Cooldown(Base):
    __tablename__ = "cooldowns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    impulse_id = Column(Integer, ForeignKey("impulses.id"), unique=True, nullable=False)
    duration_hours = Column(Integer, default=72)
    end_time = Column(DateTime, nullable=False)
    reminder_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    impulse = relationship("Impulse", back_populates="cooldown")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "year_month", "category", name="uix_budget"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    year_month = Column(String(7), nullable=False)   # "2026-10"
    category = Column(String(32), default="impulse")
    limit_amount = Column(Integer, nullable=False)   # 上限（元）
    spent_amount = Column(Integer, default=0)        # 已支出（元）

    user = relationship("User", back_populates="budgets")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    report_type = Column(String(16), nullable=False)   # weekly / monthly
    period = Column(String(16), nullable=False)        # "2026-W43" / "2026-10"
    total_impulses = Column(Integer, default=0)
    intercepted = Column(Integer, default=0)
    executed = Column(Integer, default=0)
    saved_amount = Column(Integer, default=0)
    content = Column(Text)                             # 报告正文
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    """Create all tables if not exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
