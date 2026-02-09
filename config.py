# config.py
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # GigaChat
    GIGACHAT_AUTH_KEY: str = os.getenv("GIGACHAT_AUTH_KEY", "")

    # SaluteSpeech (тот же auth key от Sber, но другой scope)
    SALUTE_SPEECH_AUTH_KEY: str = os.getenv("SALUTE_SPEECH_AUTH_KEY", "")

    # Если SaluteSpeech auth key не указан — используем тот же что и GigaChat
    def get_speech_auth_key(self) -> str:
        return self.SALUTE_SPEECH_AUTH_KEY or self.GIGACHAT_AUTH_KEY

    # ЮKassa
    YUKASSA_SHOP_ID: str = os.getenv("YUKASSA_SHOP_ID", "")
    YUKASSA_SECRET_KEY: str = os.getenv("YUKASSA_SECRET_KEY", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///whattoeat.db")

    # Limits
    FREE_RECIPES_PER_DAY: int = 3
    PREMIUM_PRICE_RUB: int = 490

    # Voice settings
    MAX_VOICE_DURATION: int = 60  # секунд
    MAX_PHOTO_SIZE: int = 20  # МБ

    # Webhook (Railway)
    WEBHOOK_HOST: str = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
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