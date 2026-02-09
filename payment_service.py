# payment_service.py
import uuid
from yookassa import Configuration, Payment as YooPayment
from yookassa.domain.notification import WebhookNotificationEventType, WebhookNotification

from config import config
from database import UserDB, PaymentDB

# Настройка ЮKassa
Configuration.account_id = config.YUKASSA_SHOP_ID
Configuration.secret_key = config.YUKASSA_SECRET_KEY


class PaymentService:
    """Сервис оплаты через ЮKassa"""

    @staticmethod
    async def create_premium_payment(telegram_id: int, months: int = 1) -> dict:
        """Создание платежа за Premium подписку"""
        amount = config.PREMIUM_PRICE_RUB * months
        description = f"WhatToEat Premium — {months} мес."

        idempotence_key = str(uuid.uuid4())

        payment = YooPayment.create({
            "amount": {
                "value": f"{amount}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{await _get_bot_username()}"
            },
            "capture": True,
            "description": description,
            "metadata": {
                "telegram_id": str(telegram_id),
                "months": str(months),
                "type": "premium_subscription"
            }
        }, idempotence_key)

        # Сохраняем в БД
        await PaymentDB.create(
            user_telegram_id=telegram_id,
            yukassa_payment_id=payment.id,
            amount=amount,
            description=description
        )

        return {
            "payment_id": payment.id,
            "confirmation_url": payment.confirmation.confirmation_url,
            "amount": amount
        }

    @staticmethod
    async def process_webhook(event_json: dict) -> dict:
        """Обработка вебхука от ЮKassa"""
        notification = WebhookNotification(event_json)
        payment = notification.object

        payment_id = payment.id
        status = payment.status

        # Обновляем статус в БД
        await PaymentDB.update_status(payment_id, status)

        result = {"payment_id": payment_id, "status": status}

        if status == "succeeded":
            metadata = payment.metadata or {}
            telegram_id = int(metadata.get("telegram_id", 0))
            months = int(metadata.get("months", 1))

            if telegram_id:
                await UserDB.activate_premium(telegram_id, months)
                result["telegram_id"] = telegram_id
                result["months"] = months

        return result

    @staticmethod
    async def check_payment_status(payment_id: str) -> str:
        """Проверка статуса платежа"""
        payment = YooPayment.find_one(payment_id)
        return payment.status


# Вспомогательная функция
_bot_username_cache = None


async def _get_bot_username():
    global _bot_username_cache
    if not _bot_username_cache:
        _bot_username_cache = "WhatToEatBot"  # Заменится при запуске
    return _bot_username_cache


payment_service = PaymentService()