import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from gigachat_service import gigachat
from models import User

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("shopping_"))
async def generate_shopping_list(callback: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data()
    recipes = data.get("recipes", [])
    products = data.get("products", [])
    idx = int(callback.data.split("_")[-1])

    if idx >= len(recipes):
        await callback.answer("❌ Рецепт не найден", show_alert=True)
        return

    recipe = recipes[idx]
    ingredients = recipe.get("ingredients", [])
    missing = [ing for ing in ingredients if not ing.get("have", True)]

    if not missing:
        await callback.answer("✅ Все продукты уже есть!", show_alert=True)
        return

    await callback.message.answer("🛒 Формирую список покупок...")

    try:
        all_names = [ing.get("name", "") for ing in ingredients]
        shopping = await gigachat.get_shopping_list(
            recipe_title=recipe.get("title", ""),
            all_ingredients=all_names,
            available_products=products
        )
    except Exception:
        shopping = [
            {"name": ing.get("name", ""), "amount": ing.get("amount", ""), "estimated_price": 0}
            for ing in missing
        ]

    text = f"🛒 <b>Список покупок для «{recipe.get('title', '')}»:</b>\n\n"
    total_cost = 0

    for i, item in enumerate(shopping, 1):
        name = item.get("name", "?")
        amount = item.get("amount", "")
        price = item.get("estimated_price", 0)
        total_cost += price
        text += f"{i}. {name} — {amount}"
        if price:
            text += f" (~{price} ₽)"
        text += "\n"

    if total_cost:
        text += f"\n💰 <b>Итого: ~{total_cost} ₽</b>"
    text += "\n\n💡 Цены приблизительные"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.message(F.text == "🛒 Список покупок")
async def shopping_list_menu(message: Message, db_user: User):
    await message.answer(
        "🛒 <b>Список покупок</b>\n\n"
        "Чтобы получить список:\n"
        "1. Найди рецепт через «🍳 Что приготовить?»\n"
        "2. Нажми «🛒 Список покупок» под рецептом",
        parse_mode="HTML"
    )
