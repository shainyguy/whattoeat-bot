# handlers/shopping.py
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from gigachat_service import gigachat
from models import User

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("shopping_"))
async def shopping_list(callback: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data()
    recipes = data.get("recipes", [])
    products = data.get("products", [])
    idx = int(callback.data.split("_")[-1])

    if idx >= len(recipes):
        await callback.answer("❌ Рецепт не найден", show_alert=True)
        return

    recipe = recipes[idx]
    ingredients = recipe.get("ingredients", [])

    # Проверяем есть ли недостающие
    missing = [i for i in ingredients if not i.get("have", True)]
    if not missing:
        await callback.answer("✅ Всё есть!", show_alert=True)
        return

    processing = await callback.message.answer("🛒 Составляю список покупок...")

    try:
        shopping = await gigachat.get_shopping_list(
            recipe_title=recipe.get("title", ""),
            all_ingredients=ingredients,  # Передаём полные dict'ы
            available_products=products
        )
    except Exception as e:
        logger.error(f"Shopping list error: {e}")
        # Фоллбэк — делаем список из данных рецепта
        shopping = []
        for ing in missing:
            shopping.append({
                "name": ing.get("name", ""),
                "amount": ing.get("amount", ""),
                "estimated_price": 0,
                "where_to_buy": ""
            })

    if not shopping:
        # Ещё один фоллбэк
        shopping = [
            {"name": i.get("name", ""), "amount": i.get("amount", ""), "estimated_price": 0}
            for i in missing
        ]

    # Форматируем
    title = recipe.get("title", "Рецепт")
    text = f"🛒 <b>Список покупок для «{title}»:</b>\n\n"

    total = 0
    for i, item in enumerate(shopping, 1):
        name = item.get("name", "?")
        amount = item.get("amount", "")
        price = item.get("estimated_price", 0) or 0
        where = item.get("where_to_buy", "")
        total += price

        text += f"<b>{i}.</b> {name}"
        if amount:
            text += f" — {amount}"
        if price:
            text += f" (~{price} ₽)"
        if where:
            text += f" 📍 {where}"
        text += "\n"

    text += "\n"
    if total:
        text += f"💰 <b>Итого: ~{total} ₽</b>\n"
    text += "\n💡 <i>Цены приблизительные (средние по рынку)</i>"

    await processing.edit_text(text, parse_mode="HTML")
    await callback.answer()


@router.message(F.text == "🛒 Список покупок")
async def shopping_menu(message: Message, db_user: User):
    await message.answer(
        "🛒 <b>Список покупок</b>\n\n"
        "Чтобы получить список:\n"
        "1. Найди рецепт → «🍳 Что приготовить?»\n"
        "2. Нажми «🛒 Список покупок» под рецептом\n\n"
        "Я определю что нужно докупить и посчитаю стоимость!",
        parse_mode="HTML"
    )
