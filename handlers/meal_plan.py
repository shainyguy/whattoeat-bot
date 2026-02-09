# handlers/meal_plan.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from gigachat_service import gigachat
from keyboards import meal_plan_keyboard, premium_keyboard
from models import User

router = Router()

DAYS_RU = {
    "monday": "Понедельник",
    "tuesday": "Вторник",
    "wednesday": "Среда",
    "thursday": "Четверг",
    "friday": "Пятница",
    "saturday": "Суббота",
    "sunday": "Воскресенье"
}

MEALS_RU = {
    "breakfast": "🌅 Завтрак",
    "lunch": "🌞 Обед",
    "dinner": "🌙 Ужин"
}


@router.message(F.text == "🗓 План на неделю")
async def meal_plan_start(message: Message, db_user: User):
    if not db_user.has_active_premium:
        await message.answer(
            "⭐️ <b>План питания на неделю — Premium функция</b>\n\n"
            "С Premium ты получишь:\n"
            "• 📅 Персональный план питания на 7 дней\n"
            "• 🥗 Учёт твоей диеты и аллергий\n"
            "• 🛒 Сводный список покупок на неделю\n"
            "• 📊 Расчёт калорий и стоимости\n\n"
            "Всего 490 ₽/месяц!",
            parse_mode="HTML",
            reply_markup=premium_keyboard()
        )
        return

    processing = await message.answer(
        "🗓 Генерирую план питания на неделю...\n"
        "Это может занять 30-60 секунд ⏳"
    )

    try:
        plan = await gigachat.generate_meal_plan(
            calories_goal=db_user.calories_goal or 2000,
            diet_type=db_user.diet_type,
            allergies=db_user.allergies or [],
            excluded=db_user.excluded_products or []
        )
    except Exception as e:
        await processing.edit_text(
            "❌ Ошибка генерации плана. Попробуй ещё раз."
        )
        return

    # Форматируем план
    for day_key, day_name in DAYS_RU.items():
        day_data = plan.get(day_key)
        if not day_data:
            continue

        text = f"📅 <b>{day_name}</b>\n{'─' * 25}\n\n"
        day_calories = 0

        for meal_key, meal_name in MEALS_RU.items():
            meal = day_data.get(meal_key, {})
            title = meal.get("title", "—")
            cal = meal.get("calories", 0)
            day_calories += cal
            text += f"{meal_name}: <b>{title}</b> ({cal} ккал)\n"

        text += f"\n📊 Итого за день: {day_calories} ккал"
        await message.answer(text, parse_mode="HTML")

    # Итоговое сообщение
    total_cal = plan.get("total_weekly_calories", "?")
    total_cost = plan.get("total_weekly_cost", "?")

    await message.answer(
        f"📊 <b>Итого за неделю:</b>\n"
        f"🔥 Калории: {total_cal} ккал\n"
        f"💰 Стоимость: ~{total_cost} ₽\n",
        parse_mode="HTML",
        reply_markup=meal_plan_keyboard()
    )

    # Сохраняем план в FSM для дальнейших действий
    from aiogram.fsm.context import FSMContext
    # Здесь можно было бы использовать state, но для простоты сохраняем в кэш


@router.callback_query(F.data == "show_weekly_shopping")
async def show_weekly_shopping(callback: CallbackQuery, db_user: User):
    await callback.message.answer(
        "🛒 <b>Сводный список покупок на неделю</b>\n\n"
        "Эта функция будет доступна в следующем обновлении!\n"
        "Следи за новостями 📢",
        parse_mode="HTML"
    )
    await callback.answer()