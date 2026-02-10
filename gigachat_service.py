# gigachat_service.py
import json
import uuid
import time
import ssl
import logging
import httpx
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════
# ПРОМПТЫ
# ═══════════════════════════════════════

PRODUCT_RECOGNITION_PROMPT = """Ты — AI-помощник кулинарного бота WhatToEat.
Пользователь описывает содержимое холодильника.
Извлеки список продуктов из текста.

ПРАВИЛА:
- Верни ТОЛЬКО JSON-массив строк
- Названия на русском языке
- Без пояснений, только JSON

Пример: ["курица", "картофель", "лук", "морковь", "сметана"]
Если продуктов нет: []"""

VOICE_PRODUCTS_PROMPT = """Пользователь ГОЛОСОМ продиктовал продукты. Текст распознан автоматически, могут быть ошибки.

Распознанный текст: "{text}"

Извлеки продукты, исправив ошибки распознавания.
Например: "кАрица" → "курица", "кАртошка" → "картошка"

Верни ТОЛЬКО JSON-массив: ["продукт1", "продукт2"]
Если продуктов нет: []"""

PHOTO_RECOGNITION_PROMPT = """На фото — содержимое холодильника или продукты.
Определи ВСЕ видимые продукты.
Если не уверен — предположи.

Верни ТОЛЬКО JSON-массив: ["продукт1", "продукт2"]"""

RECIPE_PROMPT = """Ты — опытный шеф-повар и диетолог.

ПРОДУКТЫ ПОЛЬЗОВАТЕЛЯ: {products}

{diet_info}
{allergy_info}
{excluded_info}

Предложи {count} подробных рецепта. Допускается использование базовых специй, соли, перца, масла, воды, муки, сахара.

Для КАЖДОГО рецепта дай:
1. Подробное пошаговое приготовление (каждый шаг отдельно, с указанием времени и температуры)
2. Точные пропорции ингредиентов
3. Советы по подаче
4. Чем можно заменить недостающие ингредиенты

Верни JSON-массив:
[
  {{
    "title": "Название блюда",
    "description": "Краткое описание блюда в 1-2 предложения",
    "cooking_time": число_минут,
    "difficulty": "легко/средне/сложно",
    "portions": число_порций,
    "ingredients": [
      {{"name": "продукт", "amount": "200 г", "have": true, "substitute": "чем заменить если нет"}}
    ],
    "steps": [
      {{"step": 1, "text": "Подробное описание шага", "time": "5 минут"}},
      {{"step": 2, "text": "Следующий шаг", "time": "10 минут"}}
    ],
    "tips": "Советы по подаче и хранению",
    "calories": число_ккал_на_порцию,
    "proteins": граммы_белков,
    "fats": граммы_жиров,
    "carbs": граммы_углеводов,
    "estimated_cost": стоимость_рублей_всех_ингредиентов
  }}
]

"have" = true если продукт есть у пользователя, false если нужно докупить.
Калории и БЖУ на 1 порцию.

Верни ТОЛЬКО валидный JSON без пояснений."""

SHOPPING_LIST_PROMPT = """Ты — помощник по покупкам.

Рецепт: {recipe_title}

ВСЕ ингредиенты рецепта:
{all_ingredients}

У пользователя УЖЕ ЕСТЬ:
{available_products}

Определи, что нужно ДОКУПИТЬ. Учти:
- Если продукт есть у пользователя — НЕ включай
- Базовые специи, соль, перец, вода — НЕ включай
- Укажи точное количество
- Укажи примерную цену в российских магазинах (2024-2025 год)

Верни JSON-массив:
[
  {{"name": "куриная грудка", "amount": "500 г", "estimated_price": 250, "where_to_buy": "мясной отдел"}},
  {{"name": "сливки 20%", "amount": "200 мл", "estimated_price": 120, "where_to_buy": "молочный отдел"}}
]

Если всё есть — верни пустой массив: []
Верни ТОЛЬКО JSON."""

MEAL_PLAN_PROMPT = """Ты — профессиональный диетолог.

Составь план питания на 7 дней.

Параметры:
- Норма: {calories_goal} ккал/день
- Диета: {diet_type}
- Аллергии: {allergies}
- Исключить: {excluded}

Для каждого дня — 3 приёма пищи (завтрак, обед, ужин).

Верни JSON:
{{
  "monday": {{
    "breakfast": {{"title": "...", "calories": число, "ingredients": ["..."], "instructions": "..."}},
    "lunch": {{"title": "...", "calories": число, "ingredients": ["..."], "instructions": "..."}},
    "dinner": {{"title": "...", "calories": число, "ingredients": ["..."], "instructions": "..."}}
  }},
  "tuesday": {{...}},
  "wednesday": {{...}},
  "thursday": {{...}},
  "friday": {{...}},
  "saturday": {{...}},
  "sunday": {{...}},
  "shopping_list": ["продукт — количество", ...],
  "total_weekly_calories": число,
  "total_weekly_cost": число_рублей
}}

Верни ТОЛЬКО JSON."""


class GigaChatService:

    AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    API_URL = "https://gigachat.devices.sberbank.ru/api/v1"

    def __init__(self):
        self.auth_key = config.GIGACHAT_AUTH_KEY
        self.access_token: Optional[str] = None
        self.token_expires: float = 0

    def _ssl(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def _get_token(self) -> str:
        if self.access_token and time.time() < self.token_expires:
            return self.access_token

        logger.info("Getting GigaChat token...")

        async with httpx.AsyncClient(verify=self._ssl(), timeout=15.0) as client:
            response = await client.post(
                self.AUTH_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "RqUID": str(uuid.uuid4()),
                    "Authorization": f"Basic {self.auth_key}"
                },
                data={"scope": "GIGACHAT_API_PERS"}
            )

            if response.status_code != 200:
                logger.error(f"GigaChat auth error: {response.status_code} {response.text}")
                raise Exception(f"GigaChat auth failed: {response.text}")

            data = response.json()
            self.access_token = data["access_token"]
            self.token_expires = time.time() + 1740
            logger.info("GigaChat token OK")
            return self.access_token

    async def _request(self, messages: list[dict], temperature: float = 0.7,
                       max_tokens: int = 4000) -> str:
        token = await self._get_token()

        async with httpx.AsyncClient(verify=self._ssl(), timeout=120.0) as client:
            response = await client.post(
                f"{self.API_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                json={
                    "model": "GigaChat",
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )

            if response.status_code != 200:
                logger.error(f"GigaChat error: {response.status_code} {response.text}")
                raise Exception(f"GigaChat request failed: {response.text}")

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(f"GigaChat response length: {len(content)}")
            return content

    def _extract_json(self, text: str):
        text = text.strip()

        # Убираем markdown
        if "```json" in text:
            text = text.split("```json")[1]
        if "```" in text:
            text = text.split("```")[0]
        text = text.strip()

        # Пробуем напрямую
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Ищем JSON в тексте
        for start_c, end_c in [('[', ']'), ('{', '}')]:
            start = text.find(start_c)
            end = text.rfind(end_c)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue

        logger.error(f"Failed to extract JSON from: {text[:300]}")
        raise ValueError(f"Cannot parse JSON: {text[:200]}")

    # ═══════════════════════════════════════
    # ОСНОВНЫЕ МЕТОДЫ
    # ═══════════════════════════════════════

    async def recognize_products(self, user_text: str) -> list[str]:
        messages = [
            {"role": "system", "content": PRODUCT_RECOGNITION_PROMPT},
            {"role": "user", "content": user_text}
        ]
        response = await self._request(messages, temperature=0.3)
        products = self._extract_json(response)
        if isinstance(products, list):
            return [str(p).strip().lower() for p in products if p]
        return []

    async def recognize_products_from_voice(self, recognized_text: str) -> list[str]:
        prompt = VOICE_PRODUCTS_PROMPT.format(text=recognized_text)
        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.3)
        products = self._extract_json(response)
        if isinstance(products, list):
            return [str(p).strip().lower() for p in products if p]
        return []

    async def recognize_products_from_photo(self, image_data: bytes,
                                              mime_type: str = "image/jpeg") -> list[str]:
        try:
            # Загружаем файл
            token = await self._get_token()
            async with httpx.AsyncClient(verify=self._ssl(), timeout=30.0) as client:
                resp = await client.post(
                    f"{self.API_URL}/files",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("photo.jpg", image_data, mime_type)},
                    data={"purpose": "general"}
                )
                if resp.status_code != 200:
                    logger.warning(f"File upload failed: {resp.text}")
                    return []
                file_id = resp.json().get("id", "")

            messages = [
                {"role": "user", "content": PHOTO_RECOGNITION_PROMPT, "attachments": [file_id]}
            ]
            response = await self._request(messages, temperature=0.3, model="GigaChat-Pro")
            products = self._extract_json(response)
            if isinstance(products, list):
                return [str(p).strip().lower() for p in products if p]
            return []
        except Exception as e:
            logger.warning(f"Photo recognition failed: {e}")
            return []

    async def recognize_products_from_photo_fallback(
        self, image_data: bytes, mime_type: str = "image/jpeg"
    ) -> tuple[list[str], bool]:
        products = await self.recognize_products_from_photo(image_data, mime_type)
        return products, len(products) >= 2

    async def get_recipes(self, products: list[str], count: int = 3,
                          diet_type: str = None, allergies: list[str] = None,
                          excluded: list[str] = None) -> list[dict]:

        diet_info = f"Диета: {diet_type}" if diet_type else "Без ограничений по диете"
        allergy_info = f"АЛЛЕРГИИ (ИСКЛЮЧИТЬ!): {', '.join(allergies)}" if allergies else ""
        excluded_info = f"Исключить продукты: {', '.join(excluded)}" if excluded else ""

        prompt = RECIPE_PROMPT.format(
            products=", ".join(products),
            count=count,
            diet_info=diet_info,
            allergy_info=allergy_info,
            excluded_info=excluded_info
        )

        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.8, max_tokens=8000)
        recipes = self._extract_json(response)

        if isinstance(recipes, dict):
            recipes = [recipes]
        return recipes if isinstance(recipes, list) else []

    async def get_shopping_list(self, recipe_title: str, all_ingredients: list[dict],
                                available_products: list[str]) -> list[dict]:
        """Генерация списка покупок"""
        # Форматируем ингредиенты подробно
        ing_text = ""
        for ing in all_ingredients:
            if isinstance(ing, dict):
                name = ing.get("name", "")
                amount = ing.get("amount", "")
                have = "✅ есть" if ing.get("have", False) else "❌ нет"
                ing_text += f"- {name} ({amount}) — {have}\n"
            else:
                ing_text += f"- {ing}\n"

        prompt = SHOPPING_LIST_PROMPT.format(
            recipe_title=recipe_title,
            all_ingredients=ing_text,
            available_products=", ".join(available_products) if available_products else "ничего"
        )

        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.3)
        result = self._extract_json(response)

        if isinstance(result, list):
            return result
        return []

    async def generate_meal_plan(self, calories_goal: int = 2000,
                                  diet_type: str = None,
                                  allergies: list[str] = None,
                                  excluded: list[str] = None) -> dict:
        prompt = MEAL_PLAN_PROMPT.format(
            calories_goal=calories_goal or 2000,
            diet_type=diet_type or "обычная",
            allergies=", ".join(allergies) if allergies else "нет",
            excluded=", ".join(excluded) if excluded else "нет"
        )
        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.7, max_tokens=8000)
        return self._extract_json(response)

    async def get_shopping_list(self, recipe_title: str, all_ingredients: list[dict],
                                available_products: list[str]) -> list[dict]:
        """СТАРЫЙ метод — оставляем для совместимости но не используем"""
        ing_text = ""
        for ing in all_ingredients:
            if isinstance(ing, dict):
                name = ing.get("name", "")
                amount = ing.get("amount", "")
                ing_text += f"- {name} ({amount})\n"
            else:
                ing_text += f"- {ing}\n"

        prompt = SHOPPING_LIST_PROMPT.format(
            recipe_title=recipe_title,
            all_ingredients=ing_text,
            available_products=", ".join(available_products) if available_products else "ничего"
        )
        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.3)
        result = self._extract_json(response)
        return result if isinstance(result, list) else []

    async def get_shopping_list_with_prices(self, missing_items: list[dict]) -> list[dict]:
        """Оценка цен для списка покупок"""
        items_text = ""
        for item in missing_items:
            items_text += f"- {item['name']} ({item.get('amount', '')})\n"

        prompt = f"""Оцени стоимость продуктов в российских магазинах (2024-2025).

Продукты:
{items_text}

Верни JSON:
[
  {{"name": "название", "amount": "количество", "estimated_price": цена_рублей, "where_to_buy": "отдел"}}
]

Цены реалистичные для супермаркета. ТОЛЬКО JSON."""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self._request(messages, temperature=0.3, max_tokens=2000)
            result = self._extract_json(response)

            if isinstance(result, list) and len(result) > 0:
                for i, item in enumerate(result):
                    if i < len(missing_items):
                        if not item.get("name"):
                            item["name"] = missing_items[i]["name"]
                        if not item.get("amount"):
                            item["amount"] = missing_items[i].get("amount", "")
                return result
        except Exception as e:
            logger.error(f"Price estimation error: {e}")

        return [
            {"name": m["name"], "amount": m.get("amount", ""), "estimated_price": 0, "where_to_buy": ""}
            for m in missing_items
        ]

    async def generate_meal_plan(self, calories_goal: int = 2000,
                                  diet_type: str = None,
                                  allergies: list[str] = None,
                                  excluded: list[str] = None) -> dict:
        prompt = MEAL_PLAN_PROMPT.format(
            calories_goal=calories_goal or 2000,
            diet_type=diet_type or "обычная",
            allergies=", ".join(allergies) if allergies else "нет",
            excluded=", ".join(excluded) if excluded else "нет"
        )
        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.7, max_tokens=8000)
        return self._extract_json(response)


gigachat = GigaChatService()
