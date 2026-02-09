# database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta, date
from typing import Optional

from config import config
from models import Base, User, SavedRecipe, MealPlan, Payment


engine = create_async_engine(config.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


class UserDB:
    @staticmethod
    async def get_or_create(telegram_id: int, username: str = None,
                            full_name: str = None) -> User:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    full_name=full_name,
                    allergies=[],
                    excluded_products=[]
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            else:
                user.username = username
                user.full_name = full_name
                await session.commit()

            return user

    @staticmethod
    async def get_by_telegram_id(telegram_id: int) -> Optional[User]:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def update_profile(telegram_id: int, **kwargs):
        async with async_session() as session:
            await session.execute(
                update(User).where(User.telegram_id == telegram_id).values(**kwargs)
            )
            await session.commit()

    @staticmethod
    async def increment_recipe(telegram_id: int):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.increment_recipe_count()
                await session.commit()

    @staticmethod
    async def activate_premium(telegram_id: int, months: int = 1):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                now = datetime.utcnow()
                if user.premium_until and user.premium_until > now:
                    user.premium_until += timedelta(days=30 * months)
                else:
                    user.premium_until = now + timedelta(days=30 * months)
                user.is_premium = True
                await session.commit()

    @staticmethod
    async def check_expired_premiums():
        async with async_session() as session:
            now = datetime.utcnow()
            await session.execute(
                update(User)
                .where(User.is_premium == True, User.premium_until < now)
                .values(is_premium=False)
            )
            await session.commit()


class RecipeDB:
    @staticmethod
    async def save(user_telegram_id: int, recipe_data: dict) -> SavedRecipe:
        async with async_session() as session:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            )
            user = user_result.scalar_one()

            recipe = SavedRecipe(
                user_id=user.id,
                title=recipe_data.get("title", ""),
                ingredients=recipe_data.get("ingredients", []),
                instructions=recipe_data.get("instructions", ""),
                calories=recipe_data.get("calories"),
                proteins=recipe_data.get("proteins"),
                fats=recipe_data.get("fats"),
                carbs=recipe_data.get("carbs"),
                estimated_cost=recipe_data.get("estimated_cost"),
                cooking_time=recipe_data.get("cooking_time")
            )
            session.add(recipe)
            await session.commit()
            await session.refresh(recipe)
            return recipe

    @staticmethod
    async def get_user_recipes(telegram_id: int, limit: int = 20) -> list[SavedRecipe]:
        async with async_session() as session:
            result = await session.execute(
                select(SavedRecipe)
                .join(User)
                .where(User.telegram_id == telegram_id)
                .order_by(SavedRecipe.created_at.desc())
                .limit(limit)
            )
            return result.scalars().all()


class PaymentDB:
    @staticmethod
    async def create(user_telegram_id: int, yukassa_payment_id: str,
                     amount: float, description: str = "") -> Payment:
        async with async_session() as session:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            )
            user = user_result.scalar_one()

            payment = Payment(
                user_id=user.id,
                yukassa_payment_id=yukassa_payment_id,
                amount=amount,
                description=description
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)
            return payment

    @staticmethod
    async def update_status(yukassa_payment_id: str, status: str):
        async with async_session() as session:
            values = {"status": status}
            if status == "succeeded":
                values["confirmed_at"] = datetime.utcnow()

            await session.execute(
                update(Payment)
                .where(Payment.yukassa_payment_id == yukassa_payment_id)
                .values(**values)
            )
            await session.commit()

    @staticmethod
    async def get_by_yukassa_id(yukassa_payment_id: str) -> Optional[Payment]:
        async with async_session() as session:
            result = await session.execute(
                select(Payment).where(Payment.yukassa_payment_id == yukassa_payment_id)
            )
            return result.scalar_one_or_none()