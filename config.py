# config.py — проверь что домен считывается правильно

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    GIGACHAT_AUTH_KEY: str = os.getenv("GIGACHAT_AUTH_KEY", "")
    SALUTE_SPEECH_AUTH_KEY: str = os.getenv("SALUTE_SPEECH_AUTH_KEY", "")

    def get_speech_auth_key(self) -> str:
        return self.SALUTE_SPEECH_AUTH_KEY or self.GIGACHAT_AUTH_KEY

    YUKASSA_SHOP_ID: str = os.getenv("YUKASSA_SHOP_ID", "")
    YUKASSA_SECRET_KEY: str = os.getenv("YUKASSA_SECRET_KEY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///whattoeat.db")

    FREE_RECIPES_PER_DAY: int = 3
    PREMIUM_PRICE_RUB: int = 490
    MAX_VOICE_DURATION: int = 60
    MAX_PHOTO_SIZE: int = 20

    # ─── ВАЖНО: Railway автоматически задаёт RAILWAY_PUBLIC_DOMAIN ───
    # Но иногда нужно задать вручную
    WEBHOOK_HOST: str = os.getenv(
        "RAILWAY_PUBLIC_DOMAIN",
        os.getenv("WEBHOOK_HOST", "")
    )
    WEBHOOK_PATH: str = "/webhook"
    WEBAPP_HOST: str = "0.0.0.0"
    WEBAPP_PORT: int = int(os.getenv("PORT", 8080))
    PAYMENT_CALLBACK_PATH: str = "/payment/callback"

    @property
    def webhook_url(self) -> str:
        return f"https://{self.WEBHOOK_HOST}{self.WEBHOOK_PATH}"

    @property
    def payment_callback_url(self) -> str:
        return f"https://{self.WEBHOOK_HOST}{self.PAYMENT_CALLBACK_PATH}"


config = Config()

# Логируем при импорте для отладки
import logging
_logger = logging.getLogger(__name__)
_logger.info(f"Config loaded: WEBHOOK_HOST='{config.WEBHOOK_HOST}'")
_logger.info(f"Config loaded: webhook_url='{config.webhook_url}'")
_logger.info(f"Config loaded: PORT={config.WEBAPP_PORT}")
_logger.info(f"Config loaded: BOT_TOKEN={'SET' if config.BOT_TOKEN else 'EMPTY'}")
