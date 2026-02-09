from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import UserDB
from keyboards import diet_keyboard, allergies_keyboard, calories_keyboard
from models import User

router = Router()


class ProfileStates(StatesGroup):
    entering_calories = State()
    entering_excluded = State()


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message, db_user: User):
    diet_names = {
        "normal": "🥩 Обычная", "vegetarian": "🥬 Вегетарианская",
        "vegan": "🌱 Веганская", "keto": "🥓 Кето",
        "highprotein": "🍗 Высокобелковая", "lowcal": "🥗 Низкокалорийная"
    }

    diet = diet_names.get(db_user.diet_type, "Не указана")
    allergies = ", ".join(db_user.allergies) if db_user.allergies else "Нет"
    excluded = ", ".join(db_user.excluded_products) if db_user.excluded_products else "Нет"
    calories = db_user.calories_goal or "Не указана"
    premium_status = "⭐️ Активен" if db_user.has_active_premium else "❌ Не активен"
    premium_until = ""
    if db_user.premium_until:
        premium_until = f" (до {db_user.premium_until.strftime('%d.%m.%Y')})"

    builder = InlineKeyboardBuilder()
    builder.button(text="🍽 Диета", callback_data="change_diet")
    builder.button(text="⚠️ Аллергии", callback_data="change_allergies")
    builder.button(text="🔥 Калории", callback_data="change_calories")
    builder.button(text="🚫 Исключить", callback_data="change_excluded")
    builder.adjust(2)

    await message.answer(
        f"👤 <b>Профиль</b>\n\n"
        f"🍽 Диета: {diet}\n"
        f"⚠️ Аллергии: {allergies}\n"
        f"🚫 Исключено: {excluded}\n"
        f"🔥 Норма: {calories} ккал\n"
        f"⭐️ Premium: {premium_status}{premium_until}\n\n"
        f"📊 Рецептов всего: {db_user.total_recipes}\n"
        f"📊 Сегодня: {db_user.recipes_today}",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "change_diet")
async def change_diet(callback: CallbackQuery, db_user: User):
    await callback.message.edit_text("🍽 Выбери диету:", reply_markup=diet_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("diet_"))
async def set_diet(callback: CallbackQuery, db_user: User):
    diet_type = callback.data.replace("diet_", "")
    await UserDB.update_profile(db_user.telegram_id, diet_type=diet_type)
    names = {
        "normal": "обычная", "vegetarian": "вегетарианская",
        "vegan": "веганская", "keto": "кето",
        "highprotein": "высокобелковая", "lowcal": "низкокалорийная"
    }
    await callback.message.edit_text(
        f"✅ Диета: <b>{names.get(diet_type, diet_type)}</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "change_allergies")
async def change_allergies(callback: CallbackQuery, db_user: User):
    await callback.message.edit_text(
        "⚠️ Отметь аллергии:",
        reply_markup=allergies_keyboard(db_user.allergies or [])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("allergy_") & ~F.data.endswith("done"))
async def toggle_allergy(callback: CallbackQuery, db_user: User):
    allergen = callback.data.replace("allergy_", "")
    current = list(db_user.allergies or [])

    if allergen in current:
        current.remove(allergen)
    else:
        current.append(allergen)

    await UserDB.update_profile(db_user.telegram_id, allergies=current)
    db_user.allergies = current

    await callback.message.edit_reply_markup(reply_markup=allergies_keyboard(current))
    await callback.answer(f"{'✅' if allergen in current else '❌'} {allergen}")


@router.callback_query(F.data == "allergy_done")
async def allergies_done(callback: CallbackQuery, db_user: User):
    text = ", ".join(db_user.allergies) if db_user.allergies else "нет"
    await callback.message.edit_text(
        f"✅ Аллергии: <b>{text}</b>", parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "change_calories")
async def change_calories(callback: CallbackQuery, db_user: User):
    await callback.message.edit_text("🔥 Норма калорий:", reply_markup=calories_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("calories_") & ~F.data.endswith("custom"))
async def set_calories(callback: CallbackQuery, db_user: User):
    calories = int(callback.data.replace("calories_", ""))
    await UserDB.update_profile(db_user.telegram_id, calories_goal=calories)
    await callback.message.edit_text(f"✅ Норма: <b>{calories} ккал/день</b>", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "calories_custom")
async def custom_calories(callback: CallbackQuery, state: FSMContext, db_user: User):
    await callback.message.edit_text("🔢 Введи норму калорий (число):")
    await state.set_state(ProfileStates.entering_calories)
    await callback.answer()


@router.message(ProfileStates.entering_calories)
async def save_custom_calories(message: Message, state: FSMContext, db_user: User):
    try:
        calories = int(message.text.strip())
        if calories < 800 or calories > 10000:
            raise ValueError
    except ValueError:
        await message.answer("❌ Число от 800 до 10000")
        return

    await UserDB.update_profile(db_user.telegram_id, calories_goal=calories)
    await state.clear()
    await message.answer(f"✅ Норма: <b>{calories} ккал/день</b>", parse_mode="HTML")


@router.callback_query(F.data == "change_excluded")
async def change_excluded(callback: CallbackQuery, state: FSMContext, db_user: User):
    current = ", ".join(db_user.excluded_products) if db_user.excluded_products else "нет"
    await callback.message.edit_text(
        f"🚫 Исключено: {current}\n\nНапиши продукты через запятую:"
    )
    await state.set_state(ProfileStates.entering_excluded)
    await callback.answer()


@router.message(ProfileStates.entering_excluded)
async def save_excluded(message: Message, state: FSMContext, db_user: User):
    excluded = [p.strip().lower() for p in message.text.split(",") if p.strip()]
    await UserDB.update_profile(db_user.telegram_id, excluded_products=excluded)
    await state.clear()
    await message.answer(
        f"✅ Исключены: <b>{', '.join(excluded)}</b>", parse_mode="HTML"
    )
