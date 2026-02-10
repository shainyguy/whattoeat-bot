# handlers/shopping.py
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from gigachat_service import gigachat
from models import User

router = Router()
logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Нормализация названия продукта для сравнения"""
    import re
    text = text.lower().strip()
    # Убираем всё кроме букв и пробелов
    text = re.sub(r'[^а-яёa-z\s]', '', text)
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _product_matches(ingredient_name: str, user_products: list[str]) -> bool:
    """
    Проверяет есть ли ингредиент в списке продуктов пользователя.
    Умное сравнение: 'куриная грудка' найдётся если у пользователя 'курица'
    """
    ing = _normalize(ingredient_name)

    if not ing:
        return False

    for product in user_products:
        prod = _normalize(product)
        if not prod:
            continue

        # Точное совпадение
        if ing == prod:
            return True

        # Один содержит другой
        if ing in prod or prod in ing:
            return True

        # Совпадение по корню (первые 4+ букв)
        ing_words = ing.split()
        prod_words = prod.split()

        for iw in ing_words:
            for pw in prod_words:
                # Берём минимум 4 символа для корня
                min_len = min(len(iw), len(pw))
                if min_len >= 4:
                    root_len = max(4, min_len - 2)
                    if iw[:root_len] == pw[:root_len]:
                        return True

    return False


def _find_missing_ingredients(recipe: dict, user_products: list[str]) -> list[dict]:
    """
    Определяем недостающие ингредиенты САМОСТОЯТЕЛЬНО,
    не доверяя полю have от GigaChat.
    """
    # Базовые продукты которые есть у всех
    basic_products = {
        "соль", "перец", "вода", "сахар", "масло растительное",
        "масло подсолнечное", "масло оливковое", "чёрный перец",
        "перец чёрный молотый", "лавровый лист", "уксус",
        "растительное масло", "подсолнечное масло"
    }

    ingredients = recipe.get("ingredients", [])
    missing = []

    logger.info(f"User products: {user_products}")
    logger.info(f"Recipe ingredients: {[i.get('name', '') for i in ingredients]}")

    for ing in ingredients:
        name = ing.get("name", "")
        amount = ing.get("amount", "")

        if not name:
            continue

        normalized = _normalize(name)

        # Пропускаем базовые
        if normalized in basic_products:
            continue

        # Проверяем есть ли у пользователя
        has_it = _product_matches(name, user_products)

        logger.info(f"  '{name}' -> {'ЕСТЬ' if has_it else 'НЕТ'}")

        if not has_it:
            missing.append({
                "name": name,
                "amount": amount,
                "substitute": ing.get("substitute", "")
            })

    return missing


@router.callback_query(F.data.startswith("shopping_"))
async def shopping_list(callback: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data()
    recipes = data.get("recipes", [])
    products = data.get("products", [])  # Продукты пользователя
    idx = int(callback.data.split("_")[-1])

    if idx >= len(recipes):
        await callback.answer("❌ Рецепт не найден", show_alert=True)
        return

    recipe = recipes[idx]

    # Сами определяем что нужно докупить
    missing = _find_missing_ingredients(recipe, products)

    if not missing:
        await callback.answer(
            "✅ Похоже, все основные ингредиенты у тебя есть!",
            show_alert=True
        )
        return

    processing = await callback.message.answer("🛒 Считаю стоимость покупок...")

    # Спрашиваем GigaChat цены
    try:
        shopping = await gigachat.get_shopping_list_with_prices(missing)
    except Exception as e:
        logger.error(f"Price estimation error: {e}")
        # Фоллбэк без цен
        shopping = [
            {
                "name": m["name"],
                "amount": m["amount"],
                "estimated_price": 0,
                "where_to_buy": ""
            }
            for m in missing
        ]

    # Форматируем
    title = recipe.get("title", "Рецепт")
    text = f"🛒 <b>Нужно купить для «{title}»:</b>\n\n"

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
            text += f" 📍{where}"
        text += "\n"

    # Подстановки
    subs = [m for m in missing if m.get("substitute")]
    if subs:
        text += "\n💡 <b>Возможные замены:</b>\n"
        for s in subs:
            text += f"  • {s['name']} → {s['substitute']}\n"

    text += "\n"
    if total:
        text += f"💰 <b>Итого: ~{total} ₽</b>\n"

    text += (
        f"\n✅ <b>У тебя уже есть:</b> {', '.join(products)}\n"
        f"\n<i>Цены приблизительные</i>"
    )

    # Проверяем длину
    if len(text) > 4000:
        text = text[:3950] + "\n\n...(обрезано)"

    await processing.edit_text(text, parse_mode="HTML")
    await callback.answer()


@router.message(F.text == "🛒 Список покупок")
async def shopping_menu(message: Message, db_user: User):
    await message.answer(
        "🛒 <b>Список покупок</b>\n\n"
        "1. Найди рецепт → «🍳 Что приготовить?»\n"
        "2. Нажми «🛒 Список покупок» под рецептом\n\n"
        "Я сравню ингредиенты с твоими продуктами\n"
        "и покажу что нужно докупить! 🧠",
        parse_mode="HTML"
    )
