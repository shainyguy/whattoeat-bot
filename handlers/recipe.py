# handlers/recipe.py
import logging
from io import BytesIO

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import config
from database import UserDB, RecipeDB
from gigachat_service import gigachat
from speech_service import salute_speech
from keyboards import (
    confirm_products_keyboard, recipe_actions_keyboard,
    recipe_count_keyboard, premium_keyboard
)
from models import User

router = Router()
logger = logging.getLogger(__name__)


class RecipeStates(StatesGroup):
    waiting_for_products = State()
    waiting_for_additional_products = State()
    waiting_for_photo_correction = State()
    choosing_recipe_count = State()
    viewing_recipes = State()


def format_recipe(recipe: dict, index: int) -> str:
    """Подробное форматирование рецепта"""
    title = recipe.get("title", "Без названия")
    desc = recipe.get("description", "")
    cooking_time = recipe.get("cooking_time", "?")
    difficulty = recipe.get("difficulty", "средне")
    portions = recipe.get("portions", 1)
    calories = recipe.get("calories", "?")
    proteins = recipe.get("proteins", "?")
    fats = recipe.get("fats", "?")
    carbs = recipe.get("carbs", "?")
    cost = recipe.get("estimated_cost", "?")
    tips = recipe.get("tips", "")

    # Заголовок
    text = (
        f"{'═' * 30}\n"
        f"🍽 <b>Рецепт #{index + 1}: {title}</b>\n"
        f"{'═' * 30}\n"
    )

    if desc:
        text += f"\n📖 <i>{desc}</i>\n"

    # Инфо
    diff_emoji = {"легко": "🟢", "средне": "🟡", "сложно": "🔴"}.get(difficulty, "🟡")
    text += (
        f"\n⏱ <b>Время:</b> {cooking_time} мин\n"
        f"{diff_emoji} <b>Сложность:</b> {difficulty}\n"
        f"🍽 <b>Порций:</b> {portions}\n"
        f"💰 <b>Стоимость:</b> ~{cost} ₽\n"
    )

    # БЖУ
    text += (
        f"\n📊 <b>Пищевая ценность (1 порция):</b>\n"
        f"  🔥 Калории: {calories} ккал\n"
        f"  🥩 Белки: {proteins} г\n"
        f"  🧈 Жиры: {fats} г\n"
        f"  🍞 Углеводы: {carbs} г\n"
    )

    # Ингредиенты
    ingredients = recipe.get("ingredients", [])
    text += f"\n📝 <b>Ингредиенты:</b>\n"

    have_list = []
    need_list = []
    for ing in ingredients:
        name = ing.get("name", "")
        amount = ing.get("amount", "")
        have = ing.get("have", True)
        substitute = ing.get("substitute", "")

        line = f"{name} — {amount}"
        if substitute and not have:
            line += f" (замена: {substitute})"

        if have:
            have_list.append(f"  ✅ {line}")
        else:
            need_list.append(f"  ❌ {line}")

    for line in have_list:
        text += line + "\n"
    for line in need_list:
        text += line + "\n"

    if need_list:
        text += f"\n🛒 <b>Нужно докупить: {len(need_list)} продукт(ов)</b>\n"

    # Пошаговое приготовление
    steps = recipe.get("steps", [])
    if steps:
        text += f"\n👨‍🍳 <b>Приготовление:</b>\n\n"
        for s in steps:
            step_num = s.get("step", "")
            step_text = s.get("text", "")
            step_time = s.get("time", "")
            time_str = f" ⏱ {step_time}" if step_time else ""
            text += f"<b>{step_num}.</b> {step_text}{time_str}\n\n"
    else:
        # Фоллбэк на старый формат
        instructions = recipe.get("instructions", "")
        if instructions:
            text += f"\n👨‍🍳 <b>Приготовление:</b>\n{instructions}\n"

    # Советы
    if tips:
        text += f"💡 <b>Совет:</b> {tips}\n"

    return text


async def _show_products(msg, products, recognized_text=None):
    products_list = "\n".join([f"  • {p}" for p in products])
    voice_info = f'🎤 <i>«{recognized_text}»</i>\n\n' if recognized_text else ""

    text = (
        f"{voice_info}"
        f"✅ <b>Найдено {len(products)} продуктов:</b>\n\n"
        f"{products_list}\n\n"
        f"Всё верно?"
    )

    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=confirm_products_keyboard())
    except Exception:
        await msg.answer(text, parse_mode="HTML", reply_markup=confirm_products_keyboard())


# ═══════════════════════════════════════
# НАЧАЛО
# ═══════════════════════════════════════

@router.message(F.text == "🍳 Что приготовить?")
async def start_recipe(message: Message, state: FSMContext, db_user: User):
    if not db_user.can_get_recipe(config.FREE_RECIPES_PER_DAY):
        await message.answer(
            f"⚠️ Лимит {config.FREE_RECIPES_PER_DAY} рецепта/день исчерпан!\n\n"
            f"⭐️ Premium — 490 ₽/мес — безлимит!",
            parse_mode="HTML",
            reply_markup=premium_keyboard()
        )
        return

    used = db_user.recipes_today if db_user.last_recipe_date else 0
    remaining = config.FREE_RECIPES_PER_DAY - used
    limit = f"📊 Осталось: {remaining}/{config.FREE_RECIPES_PER_DAY}" \
        if not db_user.has_active_premium else "⭐️ Безлимит"

    await message.answer(
        f"🧊 <b>Что в холодильнике?</b>\n\n"
        f"📝 Напиши текстом\n"
        f"🎤 Отправь голосовое\n"
        f"📸 Сфоткай продукты\n\n"
        f"{limit}",
        parse_mode="HTML"
    )
    await state.set_state(RecipeStates.waiting_for_products)


# ═══════════════════════════════════════
# ТЕКСТ
# ═══════════════════════════════════════

@router.message(RecipeStates.waiting_for_products, F.text)
async def text_input(message: Message, state: FSMContext, db_user: User):
    skip = {"🍳 Что приготовить?", "📋 Мои рецепты", "🗓 План на неделю",
            "🛒 Список покупок", "👤 Профиль", "⭐️ Premium"}
    if message.text in skip:
        return

    msg = await message.answer("🔍 Анализирую...")

    try:
        products = await gigachat.recognize_products(message.text)
    except Exception as e:
        logger.error(f"Recognize error: {e}")
        await msg.edit_text("❌ Ошибка. Попробуй: «курица, лук, картошка»")
        return

    if not products:
        await msg.edit_text("🤔 Не нашёл продукты. Попробуй перечислить через запятую.")
        return

    await state.update_data(products=products, input_method="text")
    await _show_products(msg, products)


# ═══════════════════════════════════════
# ГОЛОС
# ═══════════════════════════════════════

@router.message(RecipeStates.waiting_for_products, F.voice)
async def voice_input(message: Message, state: FSMContext, db_user: User, bot: Bot):
    voice = message.voice

    if voice.duration > config.MAX_VOICE_DURATION:
        await message.answer(f"⚠️ Макс. {config.MAX_VOICE_DURATION} сек.")
        return

    msg = await message.answer("🎤 Слушаю...")

    try:
        # Скачиваем
        file = await bot.get_file(voice.file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, buf)
        voice_bytes = buf.getvalue()

        logger.info(f"Voice: {voice.duration}s, {len(voice_bytes)} bytes")

        if len(voice_bytes) < 100:
            await msg.edit_text("😕 Пустое сообщение. Попробуй ещё.")
            return

        # Распознаём речь
        await msg.edit_text("🎤 Распознаю речь...")
        recognized = await salute_speech.recognize_from_telegram_voice(voice_bytes)

        if not recognized:
            await msg.edit_text(
                "😕 Не удалось распознать.\n\n"
                "Попробуй:\n"
                "• Говори чётче\n"
                "• Меньше шума\n"
                "• Или напиши текстом 📝"
            )
            return

        logger.info(f"Recognized: {recognized}")
        await msg.edit_text(f"🎤 <b>Услышал:</b> «{recognized}»\n\n🔍 Ищу продукты...", parse_mode="HTML")

        # Извлекаем продукты
        products = await gigachat.recognize_products_from_voice(recognized)

        if not products:
            await msg.edit_text(
                f"🎤 Распознано: «{recognized}»\n\n"
                f"🤔 Продукты не найдены. Попробуй ещё раз."
            )
            return

        await state.update_data(products=products, input_method="voice", recognized_text=recognized)
        await _show_products(msg, products, recognized)

    except Exception as e:
        logger.error(f"Voice error: {e}", exc_info=True)
        await msg.edit_text("❌ Ошибка обработки голоса.\n\nНапиши текстом 📝")


# ═══════════════════════════════════════
# АУДИОФАЙЛ
# ═══════════════════════════════════════

@router.message(RecipeStates.waiting_for_products, F.audio)
async def audio_input(message: Message, state: FSMContext, db_user: User, bot: Bot):
    audio = message.audio
    if audio.duration and audio.duration > config.MAX_VOICE_DURATION:
        await message.answer(f"⚠️ Макс. {config.MAX_VOICE_DURATION} сек.")
        return

    msg = await message.answer("🎵 Обрабатываю...")

    try:
        file = await bot.get_file(audio.file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, buf)

        mime = audio.mime_type or "audio/mpeg"
        recognized = await salute_speech.recognize_from_telegram_audio(buf.getvalue(), mime)

        if not recognized:
            await msg.edit_text("😕 Не распознано. Отправь голосовое 🎤")
            return

        await msg.edit_text(f"🎵 «{recognized}»\n\n🔍 Ищу продукты...", parse_mode="HTML")
        products = await gigachat.recognize_products_from_voice(recognized)

        if not products:
            await msg.edit_text("Продукты не найдены.")
            return

        await state.update_data(products=products, input_method="audio", recognized_text=recognized)
        await _show_products(msg, products, recognized)

    except Exception as e:
        logger.error(f"Audio error: {e}")
        await msg.edit_text("❌ Ошибка. Попробуй голосовое 🎤")


# ═══════════════════════════════════════
# ФОТО
# ═══════════════════════════════════════

@router.message(RecipeStates.waiting_for_products, F.photo)
async def photo_input(message: Message, state: FSMContext, db_user: User, bot: Bot):
    photo = message.photo[-1]
    msg = await message.answer("📸 Анализирую фото... ⏳\n\n💡 <i>Экспериментальная функция</i>", parse_mode="HTML")

    try:
        file = await bot.get_file(photo.file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, buf)

        products, confident = await gigachat.recognize_products_from_photo_fallback(buf.getvalue())

        if products:
            await state.update_data(products=products, input_method="photo")
            products_list = "\n".join([f"  • {p}" for p in products])
            warn = "" if confident else "\n⚠️ Маловато. Нажми «✏️ Дополнить»."
            await msg.edit_text(
                f"📸 <b>Распознано {len(products)}:</b>\n\n{products_list}\n{warn}\n\nВсё верно?",
                parse_mode="HTML",
                reply_markup=confirm_products_keyboard()
            )
        else:
            await state.set_state(RecipeStates.waiting_for_photo_correction)
            await msg.edit_text("📸 Не распознано 😕\n\nНапиши текстом 📝 или отправь 🎤")

    except Exception as e:
        logger.error(f"Photo error: {e}")
        await msg.edit_text("❌ Ошибка. Напиши текстом.")


@router.message(RecipeStates.waiting_for_products, F.video_note)
async def video_note(message: Message, state: FSMContext, db_user: User):
    await message.answer("🎥 Кружочки не поддерживаются.\nОтправь 🎤 голосовое или 📝 текст.")


@router.message(RecipeStates.waiting_for_photo_correction, F.text)
async def photo_fix_text(message: Message, state: FSMContext, db_user: User):
    await state.set_state(RecipeStates.waiting_for_products)
    await text_input(message, state, db_user)


@router.message(RecipeStates.waiting_for_photo_correction, F.voice)
async def photo_fix_voice(message: Message, state: FSMContext, db_user: User, bot: Bot):
    await state.set_state(RecipeStates.waiting_for_products)
    await voice_input(message, state, db_user, bot)


# ═══════════════════════════════════════
# ДОПОЛНЕНИЕ
# ═══════════════════════════════════════

@router.callback_query(F.data == "edit_products")
async def edit_products(callback: CallbackQuery, state: FSMContext, db_user: User):
    await callback.message.answer("✏️ Дополни: 📝 текстом, 🎤 голосом или 📸 фото")
    await state.set_state(RecipeStates.waiting_for_additional_products)
    await callback.answer()


@router.message(RecipeStates.waiting_for_additional_products, F.text)
async def add_text(message: Message, state: FSMContext, db_user: User):
    data = await state.get_data()
    existing = data.get("products", [])
    try:
        new = await gigachat.recognize_products(message.text)
    except Exception:
        await message.answer("❌ Ошибка.")
        return
    all_p = list(set(existing + new))
    await state.update_data(products=all_p)
    await state.set_state(RecipeStates.waiting_for_products)
    await _show_products(message, all_p)


@router.message(RecipeStates.waiting_for_additional_products, F.voice)
async def add_voice(message: Message, state: FSMContext, db_user: User, bot: Bot):
    data = await state.get_data()
    existing = data.get("products", [])
    msg = await message.answer("🎤 Слушаю...")
    try:
        file = await bot.get_file(message.voice.file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, buf)
        recognized = await salute_speech.recognize_from_telegram_voice(buf.getvalue())
        if not recognized:
            await msg.edit_text("😕 Не распознано.")
            return
        new = await gigachat.recognize_products_from_voice(recognized)
        all_p = list(set(existing + new))
        await state.update_data(products=all_p)
        await state.set_state(RecipeStates.waiting_for_products)
        await _show_products(msg, all_p, recognized)
    except Exception as e:
        logger.error(f"Add voice error: {e}")
        await msg.edit_text("❌ Ошибка.")


@router.message(RecipeStates.waiting_for_additional_products, F.photo)
async def add_photo(message: Message, state: FSMContext, db_user: User, bot: Bot):
    data = await state.get_data()
    existing = data.get("products", [])
    msg = await message.answer("📸 Анализирую...")
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, buf)
        new, _ = await gigachat.recognize_products_from_photo_fallback(buf.getvalue())
        all_p = list(set(existing + new))
        await state.update_data(products=all_p)
        await state.set_state(RecipeStates.waiting_for_products)
        if new:
            await _show_products(msg, all_p)
        else:
            await msg.edit_text("📸 Не распознано. Допиши текстом.")
    except Exception as e:
        logger.error(f"Add photo error: {e}")
        await msg.edit_text("❌ Ошибка.")


# ═══════════════════════════════════════
# ПОДТВЕРЖДЕНИЕ + ГЕНЕРАЦИЯ
# ═══════════════════════════════════════

@router.callback_query(F.data == "confirm_products")
async def confirm(callback: CallbackQuery, state: FSMContext, db_user: User):
    await callback.message.edit_text("🔢 Сколько рецептов?", reply_markup=recipe_count_keyboard())
    await state.set_state(RecipeStates.choosing_recipe_count)
    await callback.answer()


@router.callback_query(F.data == "restart_products")
async def restart(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    await state.set_state(RecipeStates.waiting_for_products)
    await callback.message.edit_text("🔄 Заново! Отправь продукты 📝🎤📸")
    await callback.answer()


@router.callback_query(F.data.startswith("recipes_count_"))
async def generate(callback: CallbackQuery, state: FSMContext, db_user: User):
    count = int(callback.data.split("_")[-1])

    if not db_user.can_get_recipe(config.FREE_RECIPES_PER_DAY):
        await callback.message.edit_text("⚠️ Лимит!", reply_markup=premium_keyboard())
        await callback.answer()
        return

    data = await state.get_data()
    products = data.get("products", [])

    await callback.message.edit_text(f"👨‍🍳 Готовлю {count} подробных рецептов...\n⏳ 15-30 секунд")

    try:
        recipes = await gigachat.get_recipes(
            products=products, count=count,
            diet_type=db_user.diet_type,
            allergies=db_user.allergies or [],
            excluded=db_user.excluded_products or []
        )
    except Exception as e:
        logger.error(f"Recipe error: {e}")
        await callback.message.edit_text("❌ Ошибка. Попробуй ещё.")
        await callback.answer()
        return

    if not recipes:
        await callback.message.edit_text("😕 Не получилось. Добавь больше продуктов.")
        await callback.answer()
        return

    await state.update_data(recipes=recipes, current_recipe=0)
    await state.set_state(RecipeStates.viewing_recipes)
    await UserDB.increment_recipe(db_user.telegram_id)

    # Показываем первый рецепт
    recipe_text = format_recipe(recipes[0], 0)

    # Telegram лимит 4096 символов — разбиваем если нужно
    if len(recipe_text) > 4000:
        # Отправляем в 2 сообщения
        mid = len(recipe_text) // 2
        # Ищем ближайший перенос строки
        split_pos = recipe_text.rfind("\n", 0, mid + 500)
        if split_pos == -1:
            split_pos = mid

        await callback.message.edit_text(
            f"🎉 <b>Найдено {len(recipes)} рецепт(ов)!</b>\n\n" + recipe_text[:split_pos],
            parse_mode="HTML"
        )
        await callback.message.answer(
            recipe_text[split_pos:],
            parse_mode="HTML",
            reply_markup=recipe_actions_keyboard(0)
        )
    else:
        await callback.message.edit_text(
            f"🎉 <b>Найдено {len(recipes)}!</b>\n\n{recipe_text}",
            parse_mode="HTML",
            reply_markup=recipe_actions_keyboard(0)
        )

    await callback.answer()


# ═══════════════════════════════════════
# НАВИГАЦИЯ
# ═══════════════════════════════════════

@router.callback_query(F.data == "next_recipe")
async def next_recipe(callback: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data()
    recipes = data.get("recipes", [])
    current = data.get("current_recipe", 0)
    next_idx = (current + 1) % len(recipes)
    await state.update_data(current_recipe=next_idx)

    recipe_text = format_recipe(recipes[next_idx], next_idx)

    if len(recipe_text) > 4000:
        split_pos = recipe_text.rfind("\n", 0, 2000)
        if split_pos == -1:
            split_pos = 2000
        await callback.message.edit_text(recipe_text[:split_pos], parse_mode="HTML")
        await callback.message.answer(
            recipe_text[split_pos:],
            parse_mode="HTML",
            reply_markup=recipe_actions_keyboard(next_idx)
        )
    else:
        await callback.message.edit_text(
            recipe_text, parse_mode="HTML",
            reply_markup=recipe_actions_keyboard(next_idx)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("save_recipe_"))
async def save_recipe(callback: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data()
    recipes = data.get("recipes", [])
    idx = int(callback.data.split("_")[-1])
    if idx < len(recipes):
        try:
            await RecipeDB.save(db_user.telegram_id, recipes[idx])
            await callback.answer("✅ Сохранено!", show_alert=True)
        except Exception:
            await callback.answer("❌ Ошибка", show_alert=True)
    else:
        await callback.answer("❌ Не найден", show_alert=True)


@router.message(F.text == "📋 Мои рецепты")
async def my_recipes(message: Message, db_user: User):
    recipes = await RecipeDB.get_user_recipes(db_user.telegram_id, limit=10)
    if not recipes:
        await message.answer("📋 Пусто. Нажми «🍳 Что приготовить?»")
        return
    text = "📋 <b>Сохранённые рецепты:</b>\n\n"
    for i, r in enumerate(recipes, 1):
        text += f"{i}. <b>{r.title}</b> — 🔥{r.calories or '?'} ккал, 💰~{r.estimated_cost or '?'}₽\n"
    await message.answer(text, parse_mode="HTML")
