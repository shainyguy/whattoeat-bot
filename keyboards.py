# keyboards.py
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🍳 Что приготовить?"),
        KeyboardButton(text="📋 Мои рецепты")
    )
    builder.row(
        KeyboardButton(text="🗓 План на неделю"),
        KeyboardButton(text="🛒 Список покупок")
    )
    builder.row(
        KeyboardButton(text="👤 Профиль"),
        KeyboardButton(text="⭐️ Premium")
    )
    return builder.as_markup(resize_keyboard=True)


def diet_keyboard() -> InlineKeyboardMarkup:
    """Выбор типа диеты"""
    builder = InlineKeyboardBuilder()
    diets = [
        ("🥩 Обычная", "diet_normal"),
        ("🥬 Вегетарианская", "diet_vegetarian"),
        ("🌱 Веганская", "diet_vegan"),
        ("🥓 Кето", "diet_keto"),
        ("🍗 Высокобелковая", "diet_highprotein"),
        ("🥗 Низкокалорийная", "diet_lowcal"),
    ]
    for text, callback in diets:
        builder.button(text=text, callback_data=callback)
    builder.adjust(2)
    return builder.as_markup()


def allergies_keyboard(selected: list[str] = None) -> InlineKeyboardMarkup:
    """Выбор аллергий"""
    selected = selected or []
    builder = InlineKeyboardBuilder()
    allergies = [
        ("Глютен", "allergy_глютен"),
        ("Лактоза", "allergy_лактоза"),
        ("Орехи", "allergy_орехи"),
        ("Яйца", "allergy_яйца"),
        ("Морепродукты", "allergy_морепродукты"),
        ("Соя", "allergy_соя"),
    ]
    for text, callback in allergies:
        allergen = callback.replace("allergy_", "")
        mark = "✅ " if allergen in selected else ""
        builder.button(text=f"{mark}{text}", callback_data=callback)

    builder.button(text="✔️ Готово", callback_data="allergy_done")
    builder.adjust(2)
    return builder.as_markup()


def recipe_actions_keyboard(recipe_index: int) -> InlineKeyboardMarkup:
    """Действия с рецептом"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💾 Сохранить", callback_data=f"save_recipe_{recipe_index}")
    builder.button(text="🛒 Список покупок", callback_data=f"shopping_{recipe_index}")
    builder.button(text="➡️ Другой рецепт", callback_data="next_recipe")
    builder.adjust(2)
    return builder.as_markup()


def premium_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура покупки Premium"""
    builder = InlineKeyboardBuilder()
    builder.button(text="��� Подписка — 1 мес (490 ₽)", callback_data="buy_premium_1")
    builder.button(text="💳 Подписка — 3 мес (1290 ₽)", callback_data="buy_premium_3")
    builder.button(text="💳 Подписка — 12 мес (3990 ₽)", callback_data="buy_premium_12")
    builder.adjust(1)
    return builder.as_markup()


def confirm_products_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение списка продуктов"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Всё верно, ищи рецепты!", callback_data="confirm_products")
    builder.button(text="✏️ Дополнить список", callback_data="edit_products")
    builder.button(text="🔄 Начать заново", callback_data="restart_products")
    builder.adjust(1)
    return builder.as_markup()


def recipe_count_keyboard() -> InlineKeyboardMarkup:
    """Сколько рецептов предложить"""
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣ Один", callback_data="recipes_count_1")
    builder.button(text="3️⃣ Три", callback_data="recipes_count_3")
    builder.button(text="5️⃣ Пять", callback_data="recipes_count_5")
    builder.adjust(3)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 В меню", callback_data="back_to_menu")
    return builder.as_markup()


def meal_plan_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Показать список покупок", callback_data="show_weekly_shopping")
    builder.button(text="💾 Сохранить план", callback_data="save_meal_plan")
    builder.button(text="🔄 Сгенерировать заново", callback_data="regenerate_plan")
    builder.adjust(1)
    return builder.as_markup()


def calories_keyboard() -> InlineKeyboardMarkup:
    """Выбор дневной нормы калорий"""
    builder = InlineKeyboardBuilder()
    options = [
        ("1500 ккал (похудение)", "calories_1500"),
        ("2000 ккал (поддержание)", "calories_2000"),
        ("2500 ккал (набор массы)", "calories_2500"),
        ("3000 ккал (интенсив)", "calories_3000"),
    ]
    for text, callback in options:
        builder.button(text=text, callback_data=callback)
    builder.button(text="Ввести своё значение", callback_data="calories_custom")
    builder.adjust(1)
    return builder.as_markup()


def input_method_keyboard() -> InlineKeyboardMarkup:
    """Выбор способа ввода продуктов"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Написать текстом", callback_data="input_text")
    builder.button(text="🎤 Голосовое сообщение", callback_data="input_voice")
    builder.button(text="📸 Отправить фото", callback_data="input_photo")
    builder.adjust(1)
    return builder.as_markup()    