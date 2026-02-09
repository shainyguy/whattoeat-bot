# handlers/__init__.py
from aiogram import Router

from .start import router as start_router
from .recipe import router as recipe_router
from .shopping import router as shopping_router
from .meal_plan import router as meal_plan_router
from .profile import router as profile_router
from .payment import router as payment_router


def setup_routers() -> Router:
    main_router = Router()
    main_router.include_router(start_router)
    main_router.include_router(recipe_router)
    main_router.include_router(shopping_router)
    main_router.include_router(meal_plan_router)
    main_router.include_router(profile_router)
    main_router.include_router(payment_router)
    return main_router