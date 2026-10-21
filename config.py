"""
Configuration - all sensitive values from environment variables.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # Feishu Custom App (企业自建应用)
    FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET", "")

    # Feishu Webhook Bot (群聊自定义机器人)
    FEISHU_WEBHOOK_URL: str = os.getenv("FEISHU_WEBHOOK_URL", "")

    # Bot mode: "app" | "webhook" | "mock"
    BOT_MODE: str = os.getenv("BOT_MODE", "mock")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./decision_bot.db")

    # Cooldown default (hours)
    COOLDOWN_HOURS: int = int(os.getenv("COOLDOWN_HOURS", "72"))

    # Scheduler
    WEEKLY_REPORT_DAY: int = int(os.getenv("WEEKLY_REPORT_DAY", "0"))  # 0=Monday
    WEEKLY_REPORT_HOUR: int = int(os.getenv("WEEKLY_REPORT_HOUR", "9"))
    MONTHLY_REPORT_DAY: int = int(os.getenv("MONTHLY_REPORT_DAY", "1"))
    MONTHLY_REPORT_HOUR: int = int(os.getenv("MONTHLY_REPORT_HOUR", "9"))

    # Scoring weights (must sum to 1.0)
    WEIGHT_OPPORTUNITY: float = float(os.getenv("WEIGHT_OPPORTUNITY", "0.25"))
    WEIGHT_DURABILITY: float = float(os.getenv("WEIGHT_DURABILITY", "0.25"))
    WEIGHT_FREQUENCY: float = float(os.getenv("WEIGHT_FREQUENCY", "0.20"))
    WEIGHT_ALTERNATIVE: float = float(os.getenv("WEIGHT_ALTERNATIVE", "0.20"))
    WEIGHT_EXIT_COST: float = float(os.getenv("WEIGHT_EXIT_COST", "0.10"))

    @property
    def weights(self) -> dict[str, float]:
        return {
            "opportunity": self.WEIGHT_OPPORTUNITY,
            "durability": self.WEIGHT_DURABILITY,
            "frequency": self.WEIGHT_FREQUENCY,
            "alternative": self.WEIGHT_ALTERNATIVE,
            "exit_cost": self.WEIGHT_EXIT_COST,
        }

    def validate(self) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")


config = Config()
config.validate()
