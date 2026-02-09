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
    title = recipe.get("title", "Без названия")
    cooking_time = recipe.get("cooking_time", "?")
    portions = recipe.get("portions", 1)
    calories = recipe.get("calories", "?")
    proteins = recipe.get("proteins", "?")
    fats = recipe.get("fats", "?")
    carbs = recipe.get("carbs", "?")
    cost = recipe.get("estimated_cost", "?")
    instructions = recipe.get("instructions", "Инструкция отсутствует")

    ingredients_text = ""
    ingredients = recipe.get("ingredients", [])
    for ing in ingredients:
        name = ing.get("name", "")
        amount = ing.get("amount", "")
        have = ing.get("have", True)
        emoji = "✅" if have else "❌"
        ingredients_text += f"  {emoji} {name} — {amount}\n"

    missing = [ing for ing in ingredients if not ing.get("have", True)]
    missing_text = ""
    if missing:
        missing_text = f"\n🛒 <b>Нужно докупить:</b> {len(missing)} продукт(ов)"

    return (
        f"{'─' * 30}\n"
        f"🍽️ <b>Рецепт #{index + 1}: {title}</b>\n"
        f"{'─' * 30}\n\n"
        f"⏱ Время: {cooking_time} мин | 🍽 Порций: {portions}\n"
        f"💰 Стоимость: ~{cost} ₽\n\n"
        f"📊 <b>Пищевая ценность (на порцию):</b>\n"
        f"  🔥 Калории: {calories} ккал\n"
        f"  🥩 Белки: {proteins} г\n"
        f"  🧈 Жиры: {fats} г\n"
        f"  🍞 Углеводы: {carbs} г\n\n"
        f"📝 <b>Ингредиенты:</b>\n{ingredients_text}"
        f"{missing_text}\n\n"
        f"👨‍🍳 <b>Приготовление:</b>\n{instructions}\n"
    )


async def _show_product_confirmation(msg: Message, products: list[str],
                                      recognized_text: str = None):
    products_list = "\n".join([f"  • {p}" for p in products])

    voice_info = ""
    if recognized_text:
        voice_info = f'🎤 <i>«{recognized_text}»</i>\n\n'

    try:
        await msg.edit_text(
            f"{voice_info}"
            f"✅ <b>Найдено {len(products)} продуктов:</b>\n\n"
            f"{products_list}\n\n"
            f"Всё верно?",
            parse_mode="HTML",
            reply_markup=confirm_products_keyboard()
        )
    except Exception:
        await msg.answer(
            f"{voice_info}"
            f"✅ <b>Найдено {len(products)} продуктов:</b>\n\n"
            f"{products_list}\n\n"
            f"Всё верно?",
            parse_mode="HTML",
            reply_markup=confirm_products_keyboard()
        )


# ─── Начало ───

@router.message(F.text == "🍳 Что приготовить?")
async def start_recipe_search(message: Message, state: FSMContext, db_user: User):
    if not db_user.can_get_recipe(config.FREE_RECIPES_PER_DAY):
        await message.answer(
            f"⚠️ <b>Дневной лимит исчерпан!</b>\n\n"
            f"Ты использовал все {config.FREE_RECIPES_PER_DAY} бесплатных рецепта сегодня.\n\n"
            f"⭐️ С <b>Premium</b> (490 ₽/мес) — безлимитные рецепты!",
            parse_mode="HTML",
            reply_markup=premium_keyboard()
        )
        return

    used = db_user.recipes_today if db_user.last_recipe_date else 0
    remaining = config.FREE_RECIPES_PER_DAY - used
    limit_text = (
        f"📊 Осталось: {remaining}/{config.FREE_RECIPES_PER_DAY}"
        if not db_user.has_active_premium
        else "⭐️ Premium — безлимит"
    )

    await message.answer(
        f"🧊 <b>Что у тебя в холодильнике?</b>\n\n"
        f"Расскажи мне любым способом:\n\n"
        f"📝 <b>Текстом:</b> «курица, рис, лук, морковь»\n"
        f"🎤 <b>Голосовым:</b> просто надиктуй продукты\n"
        f"📸 <b>Фото:</b> сфоткай холодильник\n\n"
        f"{limit_text}",
        parse_mode="HTML"
    )
    await state.set_state(RecipeStates.waiting_for_products)


# ─── Текст ───

@router.message(RecipeStates.waiting_for_products, F.text)
async def process_text_products(message: Message, state: FSMContext, db_user: User):
    menu_buttons = {
        "🍳 Что приготовить?", "📋 Мои рецепты", "🗓 План на неделю",
        "🛒 Список покупок", "👤 Профиль", "⭐️ Premium"
    }
    if message.text in menu_buttons:
        return

    processing_msg = await message.answer("🔍 Определяю продукты из текста...")

    try:
        products = await gigachat.recognize_products(message.text)
    except Exception as e:
        logger.error(f"Product recognition error: {e}")
        await processing_msg.edit_text(
            "❌ Ошибка при анализе. Попробуй ещё раз.\n"
            "Совет: перечисли продукты через запятую."
        )
        return

    if not products:
        await processing_msg.edit_text(
            "🤔 Не удалось распознать продукты.\n"
            "Попробуй: «курица, картофель, лук, сметана»"
        )
        return

    await state.update_data(products=products, input_method="text")
    await _show_product_confirmation(processing_msg, products)


# ─── Голос ───

@router.message(RecipeStates.waiting_for_products, F.voice)
async def process_voice_products(message: Message, state: FSMContext,
                                  db_user: User, bot: Bot):
    voice = message.voice

    if voice.duration > config.MAX_VOICE_DURATION:
        await message.answer(
            f"⚠️ Слишком длинное (макс. {config.MAX_VOICE_DURATION} сек).\n"
            f"Просто перечисли продукты!"
        )
        return

    processing_msg = await message.answer("🎤 Распознаю голосовое сообщение...")

    try:
        voice_file = await bot.get_file(voice.file_id)
        voice_data = BytesIO()
        await bot.download_file(voice_file.file_path, voice_data)
        voice_bytes = voice_data.getvalue()

        logger.info(f"Voice: {voice.duration}s, {len(voice_bytes)} bytes")

        await processing_msg.edit_text("🎤 Распознаю речь...")
        recognized_text = await salute_speech.recognize_from_telegram_voice(voice_bytes)

        if not recognized_text:
            await processing_msg.edit_text(
                "😕 Не удалось распознать речь.\n\n"
                "Попробуй:\n"
                "• Говорить чётче\n"
                "• Уменьшить шум\n"
                "• Или напиши текстом 📝"
            )
            return

        await processing_msg.edit_text(
            f"🎤 <b>Распознано:</b>\n«{recognized_text}»\n\n"
            f"🔍 Извлекаю продукты...",
            parse_mode="HTML"
        )

        products = await gigachat.recognize_products_from_voice(recognized_text)

        if not products:
            await processing_msg.edit_text(
                f"🎤 Распознано: «{recognized_text}»\n\n"
                f"🤔 Продукты не найдены. Попробуй ещё раз."
            )
            return

        await state.update_data(
            products=products,
            input_method="voice",
            recognized_text=recognized_text
        )
        await _show_product_confirmation(processing_msg, products, recognized_text)

    except Exception as e:
        logger.error(f"Voice error: {e}", exc_info=True)
        await processing_msg.edit_text(
            "❌ Ошибка обработки голоса. Попробуй текстом 📝"
        )


# ─── Аудиофайл ───

@router.message(RecipeStates.waiting_for_products, F.audio)
async def process_audio_products(message: Message, state: FSMContext,
                                  db_user: User, bot: Bot):
    audio = message.audio

    if audio.duration and audio.duration > config.MAX_VOICE_DURATION:
        await message.answer(f"⚠️ Слишком длинное (макс. {config.MAX_VOICE_DURATION} сек).")
        return

    processing_msg = await message.answer("🎵 Распознаю аудио...")

    try:
        audio_file = await bot.get_file(audio.file_id)
        audio_data = BytesIO()
        await bot.download_file(audio_file.file_path, audio_data)

        mime_type = audio.mime_type or "audio/mpeg"
        recognized_text = await salute_speech.recognize_from_telegram_audio(
            audio_data.getvalue(), mime_type
        )

        if not recognized_text:
            await processing_msg.edit_text("😕 Не удалось распознать. Попробуй голосовое.")
            return

        await processing_msg.edit_text(
            f"🎵 <b>Распознано:</b> «{recognized_text}»\n\n🔍 Извлекаю продукты...",
            parse_mode="HTML"
        )

        products = await gigachat.recognize_products_from_voice(recognized_text)

        if not products:
            await processing_msg.edit_text(f"Распознано: «{recognized_text}»\n\nПродукты не найдены.")
            return

        await state.update_data(products=products, input_method="audio", recognized_text=recognized_text)
        await _show_product_confirmation(processing_msg, products, recognized_text)

    except Exception as e:
        logger.error(f"Audio error: {e}", exc_info=True)
        await processing_msg.edit_text("❌ Ошибка. Попробуй текстом 📝")


# ─── Фото ───

@router.message(RecipeStates.waiting_for_products, F.photo)
async def process_photo_products(message: Message, state: FSMContext,
                                  db_user: User, bot: Bot):
    photo = message.photo[-1]

    processing_msg = await message.answer(
        "📸 Анализирую фото...\n⏳ 10-15 секунд\n\n"
        "💡 <i>Распознавание фото — экспериментальная функция.</i>",
        parse_mode="HTML"
    )

    try:
        photo_file = await bot.get_file(photo.file_id)
        photo_data = BytesIO()
        await bot.download_file(photo_file.file_path, photo_data)
        photo_bytes = photo_data.getvalue()

        products, is_confident = await gigachat.recognize_products_from_photo_fallback(
            photo_bytes, mime_type="image/jpeg"
        )

        if products and is_confident:
            await state.update_data(products=products, input_method="photo")
            products_list = "\n".join([f"  • {p}" for p in products])
            await processing_msg.edit_text(
                f"📸 <b>Распознано {len(products)} продуктов:</b>\n\n"
                f"{products_list}\n\n"
                f"⚠️ <i>Проверь список и скорректируй!</i>",
                parse_mode="HTML",
                reply_markup=confirm_products_keyboard()
            )
        elif products:
            await state.update_data(products=products, input_method="photo")
            products_list = "\n".join([f"  • {p}" for p in products])
            await processing_msg.edit_text(
                f"📸 <b>Распознано только {len(products)}:</b>\n\n"
                f"{products_list}\n\n"
                f"Нажми «✏️ Дополнить» и допиши остальное.",
                parse_mode="HTML",
                reply_markup=confirm_products_keyboard()
            )
        else:
            await state.set_state(RecipeStates.waiting_for_photo_correction)
            await processing_msg.edit_text(
                "📸 <b>Не удалось распознать продукты</b> 😕\n\n"
                "Попробуй:\n"
                "📝 Напиши текстом\n"
                "🎤 Отправь голосовое",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Photo error: {e}", exc_info=True)
        await processing_msg.edit_text("❌ Ошибка. Попробуй текстом или голосом.")


# ─── Видеокружочки ───

@router.message(RecipeStates.waiting_for_products, F.video_note)
async def process_video_note(message: Message, state: FSMContext, db_user: User):
    await message.answer(
        "🎥 Видеокружочки не поддерживаются.\n\n"
        "Используй:\n🎤 Голосовое\n📝 Текст\n📸 Фото"
    )


# ─── Фоллбэк после неудачного фото ───

@router.message(RecipeStates.waiting_for_photo_correction, F.text)
async def photo_correction_text(message: Message, state: FSMContext, db_user: User):
    await state.set_state(RecipeStates.waiting_for_products)
    await process_text_products(message, state, db_user)


@router.message(RecipeStates.waiting_for_photo_correction, F.voice)
async def photo_correction_voice(message: Message, state: FSMContext,
                                  db_user: User, bot: Bot):
    await state.set_state(RecipeStates.waiting_for_products)
    await process_voice_products(message, state, db_user, bot)


# ─── Дополнение списка ───

@router.callback_query(F.data == "edit_products")
async def edit_products(callback: CallbackQuery, state: FSMContext, db_user: User):
    await callback.message.answer(
        "✏️ <b>Дополни список!</b>\n\n📝 Текстом\n🎤 Голосом\n📸 Фото",
        parse_mode="HTML"
    )
    await state.set_state(RecipeStates.waiting_for_additional_products)
    await callback.answer()


@router.message(RecipeStates.waiting_for_additional_products, F.text)
async def add_products_text(message: Message, state: FSMContext, db_user: User):
    data = await state.get_data()
    existing = data.get("products", [])

    try:
        new_products = await gigachat.recognize_products(message.text)
    except Exception:
        await message.answer("❌ Ошибка. Попробуй ещё.")
        return

    all_products = list(set(existing + new_products))
    await state.update_data(products=all_products)
    await state.set_state(RecipeStates.waiting_for_products)

    products_list = "\n".join([f"  • {p}" for p in all_products])
    await message.answer(
        f"✅ <b>Список ({len(all_products)}):</b>\n\n{products_list}\n\nВсё верно?",
        parse_mode="HTML",
        reply_markup=confirm_products_keyboard()
    )


@router.message(RecipeStates.waiting_for_additional_products, F.voice)
async def add_products_voice(message: Message, state: FSMContext,
                              db_user: User, bot: Bot):
    data = await state.get_data()
    existing = data.get("products", [])

    processing_msg = await message.answer("🎤 Распознаю...")

    try:
        voice_file = await bot.get_file(message.voice.file_id)
        voice_data = BytesIO()
        await bot.download_file(voice_file.file_path, voice_data)

        recognized = await salute_speech.recognize_from_telegram_voice(voice_data.getvalue())

        if not recognized:
            await processing_msg.edit_text("😕 Не распознано. Попробуй ещё.")
            return

        new_products = await gigachat.recognize_products_from_voice(recognized)
        all_products = list(set(existing + new_products))
        await state.update_data(products=all_products)
        await state.set_state(RecipeStates.waiting_for_products)

        products_list = "\n".join([f"  • {p}" for p in all_products])
        await processing_msg.edit_text(
            f"🎤 «{recognized}»\n\n"
            f"✅ <b>Список ({len(all_products)}):</b>\n\n{products_list}\n\nВсё верно?",
            parse_mode="HTML",
            reply_markup=confirm_products_keyboard()
        )

    except Exception as e:
        logger.error(f"Voice addition error: {e}")
        await processing_msg.edit_text("❌ Ошибка. Попробуй текстом.")


@router.message(RecipeStates.waiting_for_additional_products, F.photo)
async def add_products_photo(message: Message, state: FSMContext,
                              db_user: User, bot: Bot):
    data = await state.get_data()
    existing = data.get("products", [])

    processing_msg = await message.answer("📸 Анализирую...")

    try:
        photo = message.photo[-1]
        photo_file = await bot.get_file(photo.file_id)
        photo_data = BytesIO()
        await bot.download_file(photo_file.file_path, photo_data)

        new_products, _ = await gigachat.recognize_products_from_photo_fallback(
            photo_data.getvalue()
        )
        all_products = list(set(existing + new_products))
        await state.update_data(products=all_products)
        await state.set_state(RecipeStates.waiting_for_products)

        if new_products:
            products_list = "\n".join([f"  • {p}" for p in all_products])
            await processing_msg.edit_text(
                f"📸 Добавлено: {', '.join(new_products)}\n\n"
                f"✅ <b>Список ({len(all_products)}):</b>\n\n{products_list}\n\nВсё верно?",
                parse_mode="HTML",
                reply_markup=confirm_products_keyboard()
            )
        else:
            await processing_msg.edit_text("📸 Ничего не распознано. Допиши текстом.")

    except Exception as e:
        logger.error(f"Photo addition error: {e}")
        await processing_msg.edit_text("❌ Ошибка. Попробуй текстом.")


# ─── Подтверждение ───

@router.callback_query(F.data == "confirm_products")
async def confirm_products(callback: CallbackQuery, state: FSMContext, db_user: User):
    await callback.message.edit_text(
        "🔢 Сколько рецептов предложить?",
        reply_markup=recipe_count_keyboard()
    )
    await state.set_state(RecipeStates.choosing_recipe_count)
    await callback.answer()


@router.callback_query(F.data == "restart_products")
async def restart_products(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    await callback.message.edit_text(
        "🔄 Заново!\n\nОтправь продукты:\n📝 Текстом\n🎤 Голосом\n📸 Фото"
    )
    await state.set_state(RecipeStates.waiting_for_products)
    await callback.answer()


# ─── Генерация рецептов ───

@router.callback_query(F.data.startswith("recipes_count_"))
async def generate_recipes(callback: CallbackQuery, state: FSMContext, db_user: User):
    count = int(callback.data.split("_")[-1])

    if not db_user.can_get_recipe(config.FREE_RECIPES_PER_DAY):
        await callback.message.edit_text(
            "⚠️ Лимит исчерпан!",
            reply_markup=premium_keyboard()
        )
        await callback.answer()
        return

    data = await state.get_data()
    products = data.get("products", [])

    await callback.message.edit_text("👨‍🍳 Готовлю рецепты... ⏳ 10-20 сек")

    try:
        recipes = await gigachat.get_recipes(
            products=products,
            count=count,
            diet_type=db_user.diet_type,
            allergies=db_user.allergies or [],
            excluded=db_user.excluded_products or []
        )
    except Exception as e:
        logger.error(f"Recipe generation error: {e}")
        await callback.message.edit_text("❌ Ошибка генерации. Попробуй ещё раз.")
        await callback.answer()
        return

    if not recipes:
        await callback.message.edit_text("😕 Не удалось подобрать. Добавь больше продуктов.")
        await callback.answer()
        return

    await state.update_data(recipes=recipes, current_recipe=0)
    await state.set_state(RecipeStates.viewing_recipes)
    await UserDB.increment_recipe(db_user.telegram_id)

    recipe_text = format_recipe(recipes[0], 0)
    if len(recipe_text) > 4000:
        recipe_text = recipe_text[:3950] + "\n\n... (обрезано)"

    await callback.message.edit_text(
        f"🎉 <b>Найдено {len(recipes)} рецепт(ов)!</b>\n\n{recipe_text}",
        parse_mode="HTML",
        reply_markup=recipe_actions_keyboard(0)
    )
    await callback.answer()


# ─── Навигация ───

@router.callback_query(F.data == "next_recipe")
async def next_recipe(callback: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data()
    recipes = data.get("recipes", [])
    current = data.get("current_recipe", 0)

    next_idx = (current + 1) % len(recipes)
    await state.update_data(current_recipe=next_idx)

    recipe_text = format_recipe(recipes[next_idx], next_idx)
    if len(recipe_text) > 4000:
        recipe_text = recipe_text[:3950] + "\n\n... (обрезано)"

    await callback.message.edit_text(
        recipe_text,
        parse_mode="HTML",
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
        await message.answer("📋 Нет сохранённых рецептов.\nНажми «🍳 Что приготовить?»")
        return

    text = "📋 <b>Твои рецепты:</b>\n\n"
    for i, recipe in enumerate(recipes, 1):
        text += (
            f"{i}. <b>{recipe.title}</b>\n"
            f"   🔥 {recipe.calories or '?'} ккал | "
            f"💰 ~{recipe.estimated_cost or '?'} ₽\n\n"
        )
    await message.answer(text, parse_mode="HTML")
