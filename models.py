# models.py
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean,
    DateTime, Date, Text, Float, ForeignKey, JSON
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)

    # Подписка
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)

    # Профиль питания
    diet_type = Column(String(50), nullable=True)  # keto, vegan, vegetarian, etc.
    allergies = Column(JSON, default=list)  # ["глютен", "лактоза", "орехи"]
    calories_goal = Column(Integer, nullable=True)  # дневная норма ккал
    excluded_products = Column(JSON, default=list)  # исключенные продукты

    # Статистика
    recipes_today = Column(Integer, default=0)
    last_recipe_date = Column(Date, nullable=True)
    total_recipes = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    recipes = relationship("SavedRecipe", back_populates="user", cascade="all, delete")
    meal_plans = relationship("MealPlan", back_populates="user", cascade="all, delete")
    payments = relationship("Payment", back_populates="user", cascade="all, delete")

    @property
    def has_active_premium(self) -> bool:
        if not self.is_premium:
            return False
        if self.premium_until and self.premium_until < datetime.utcnow():
            return False
        return True

    def can_get_recipe(self, free_limit: int) -> bool:
        if self.has_active_premium:
            return True
        today = date.today()
        if self.last_recipe_date != today:
            return True
        return self.recipes_today < free_limit

    def increment_recipe_count(self):
        today = date.today()
        if self.last_recipe_date != today:
            self.recipes_today = 1
            self.last_recipe_date = today
        else:
            self.recipes_today += 1
        self.total_recipes += 1


class SavedRecipe(Base):
    __tablename__ = "saved_recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False)
    ingredients = Column(JSON, nullable=False)  # [{"name": "...", "amount": "...", "have": True}]
    instructions = Column(Text, nullable=False)
    calories = Column(Integer, nullable=True)
    proteins = Column(Float, nullable=True)
    fats = Column(Float, nullable=True)
    carbs = Column(Float, nullable=True)
    estimated_cost = Column(Float, nullable=True)  # рублей
    cooking_time = Column(Integer, nullable=True)  # минут
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="recipes")


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    week_start = Column(Date, nullable=False)
    plan_data = Column(JSON, nullable=False)
    # {
    #   "monday": {"breakfast": {...}, "lunch": {...}, "dinner": {...}},
    #   ...
    # }
    total_calories = Column(Integer, nullable=True)
    total_cost = Column(Float, nullable=True)
    shopping_list = Column(JSON, nullable=True)  # сводный список покупок
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="meal_plans")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    yukassa_payment_id = Column(String(255), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")
    status = Column(String(50), default="pending")  # pending, succeeded, canceled
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="payments")