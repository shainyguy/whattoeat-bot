import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config
from keyboards import premium_keyboard, main_menu_keyboard
from payment_service import payment_service
from database import UserDB
from models import User

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "⭐️ Premium")
async def premium_info(message: Message, db_user: User):
    if db_user.has_active_premium:
        until = db_user.premium_until.strftime('%d.%m.%Y') if db_user.premium_until else "?"
        await message.answer(
            f"⭐️ <b>Premium активен до {until}</b>\n\nСпасибо за поддержку! ❤️",
            parse_mode="HTML"
        )
        return

    await message.answer(
        "⭐️ <b>WhatToEat Premium</b>\n\n"
        f"<b>Free:</b> {config.FREE_RECIPES_PER_DAY} рецепта/день\n\n"
        "<b>Premium:</b>\n"
        "✅ Безлимитные рецепты\n"
        "✅ 🗓 План на неделю\n"
        "✅ 🥗 Учёт диет/аллергий\n"
        "✅ 📊 Подробный БЖУ\n\n"
        "💰 1 мес — 490 ₽\n"
        "💰 3 мес — 1 290 ₽\n"
        "💰 12 мес — 3 990 ₽",
        parse_mode="HTML",
        reply_markup=premium_keyboard()
    )


@router.callback_query(F.data.startswith("buy_premium_"))
async def buy_premium(callback: CallbackQuery, db_user: User):
    months = int(callback.data.split("_")[-1])
    prices = {1: 490, 3: 1290, 12: 3990}
    amount = prices.get(months, 490)

    await callback.message.edit_text("💳 Создаю платёж...")

    try:
        payment_data = await payment_service.create_premium_payment(
            telegram_id=db_user.telegram_id,
            months=months
        )

        builder = InlineKeyboardBuilder()
        builder.button(text=f"💳 Оплатить {amount} ₽", url=payment_data["confirmation_url"])
        builder.button(
            text="🔄 Проверить оплату",
            callback_data=f"check_payment_{payment_data['payment_id']}"
        )
        builder.adjust(1)

        await callback.message.edit_text(
            f"💳 <b>Оплата Premium ({months} мес.)</b>\n\n"
            f"Сумма: <b>{amount} ₽</b>\n\n"
            f"Нажми кнопку → оплати → проверь оплату.",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.error(f"Payment error: {e}")
        await callback.message.edit_text("❌ Ошибка платежа. Попробуй позже.")

    await callback.answer()


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery, db_user: User):
    payment_id = callback.data.replace("check_payment_", "")

    try:
        status = await payment_service.check_payment_status(payment_id)
    except Exception:
        await callback.answer("❌ Ошибка проверки", show_alert=True)
        return

    if status == "succeeded":
        await callback.message.edit_text(
            "🎉 <b>Оплата прошла!</b>\n⭐️ Premium активирован!",
            parse_mode="HTML"
        )
        await callback.message.answer("🏠 Меню", reply_markup=main_menu_keyboard())
    elif status == "pending":
        await callback.answer("⏳ Обрабатывается. Подожди 1-2 мин.", show_alert=True)
    elif status == "canceled":
        await callback.message.edit_text(
            "❌ Платёж отменён.", reply_markup=premium_keyboard()
        )
    else:
        await callback.answer(f"Статус: {status}", show_alert=True)
