# handlers/payment.py
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery

from config import config
from keyboards import premium_keyboard, main_menu_keyboard
from payment_service import payment_service
from models import User

router = Router()


@router.message(F.text == "⭐️ Premium")
async def premium_info(message: Message, db_user: User):
    if db_user.has_active_premium:
        until = db_user.premium_until.strftime('%d.%m.%Y') if db_user.premium_until else "?"
        await message.answer(
            f"⭐️ <b>У тебя Premium!</b>\n\n"
            f"Активен до: {until}\n\n"
            f"Твои возможности:\n"
            f"✅ Безлимитные рецепты\n"
            f"✅ План питания на неделю\n"
            f"✅ Учёт диет и аллергий\n"
            f"✅ Расширенный анализ калорий\n\n"
            f"Спасибо за поддержку! ❤️",
            parse_mode="HTML"
        )
        return

    await message.answer(
        "⭐️ <b>WhatToEat Premium</b>\n\n"
        "<b>Бесплатная версия:</b>\n"
        f"• {config.FREE_RECIPES_PER_DAY} рецепта в день\n"
        "• Базовый подсчёт калорий\n"
        "• Список покупок\n\n"
        "<b>Premium включает:</b>\n"
        "✅ Безлимитные рецепты\n"
        "✅ 🗓 Персональный план питания на неделю\n"
        "✅ 🥗 Учёт диет (кето, веган, и др.)\n"
        "✅ ⚠️ Учёт аллергий\n"
        "✅ 📊 Подробный анализ БЖУ\n"
        "✅ 🛒 Автоформирование списка покупок\n"
        "✅ 🆕 Ранний доступ к новым функциям\n\n"
        "💰 <b>Стоимость:</b>\n"
        "• 1 месяц — 490 ₽\n"
        "• 3 месяца — 1 290 ₽ (430 ₽/мес)\n"
        "• 12 месяцев — 3 990 ₽ (333 ₽/мес)\n",
        parse_mode="HTML",
        reply_markup=premium_keyboard()
    )


@router.callback_query(F.data.startswith("buy_premium_"))
async def buy_premium(callback: CallbackQuery, db_user: User):
    months = int(callback.data.split("_")[-1])

    # Расчёт стоимости
    prices = {1: 490, 3: 1290, 12: 3990}
    amount = prices.get(months, 490)

    await callback.message.edit_text("💳 Создаю платёж...")

    try:
        payment_data = await payment_service.create_premium_payment(
            telegram_id=db_user.telegram_id,
            months=months
        )

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"💳 Оплатить {amount} ₽",
            url=payment_data["confirmation_url"]
        )
        builder.button(
            text="🔄 Проверить оплату",
            callback_data=f"check_payment_{payment_data['payment_id']}"
        )
        builder.adjust(1)

        await callback.message.edit_text(
            f"💳 <b>Оплата Premium ({months} мес.)</b>\n\n"
            f"Сумма: <b>{amount} ₽</b>\n\n"
            f"Нажми кнопку ниже для перехода к оплате.\n"
            f"После оплаты нажми «🔄 Проверить оплату».",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка создания платежа. Попробуй позже.\n"
            f"Если проблема повторяется — напиши в поддержку."
        )

    await callback.answer()


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery, db_user: User, bot: Bot):
    payment_id = callback.data.replace("check_payment_", "")

    try:
        status = await payment_service.check_payment_status(payment_id)
    except Exception:
        await callback.answer("❌ Ошибка проверки", show_alert=True)
        return

    if status == "succeeded":
        # Обновляем пользователя в БД
        from database import UserDB
        updated_user = await UserDB.get_by_telegram_id(db_user.telegram_id)

        await callback.message.edit_text(
            "🎉 <b>Оплата прошла успешно!</b>\n\n"
            "⭐️ Premium активирован!\n\n"
            "Теперь тебе доступны:\n"
            "✅ Безлимитные рецепты\n"
            "✅ План питания на неделю\n"
            "✅ Учёт диет и аллергий\n\n"
            "Приятного использования! 🍽",
            parse_mode="HTML"
        )
        await callback.message.answer(
            "🏠 Главное меню",
            reply_markup=main_menu_keyboard()
        )
    elif status == "pending":
        await callback.answer(
            "⏳ Оплата ещё обрабатывается. Подожди 1-2 минуты и проверь снова.",
            show_alert=True
        )
    elif status == "canceled":
        await callback.message.edit_text(
            "❌ <b>Платёж отменён</b>\n\n"
            "Можешь попробовать ещё раз:",
            parse_mode="HTML",
            reply_markup=premium_keyboard()
        )
    else:
        await callback.answer(f"Статус: {status}", show_alert=True)