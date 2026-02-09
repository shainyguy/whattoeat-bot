# gigachat_service.py (обновлённый — добавлены методы для фото)
import json
import uuid
import time
import base64
import ssl
import logging
import httpx
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

# ─── Системные промпты ───

PRODUCT_RECOGNITION_PROMPT = """Ты — AI-помощник кулинарного бота WhatToEat. 
Пользователь описывает содержимое холодильника текстом.
Твоя задача — извлечь список продуктов из текста.

Верни ТОЛЬКО JSON-массив строк с названиями продуктов на русском языке.
Пример: ["курица", "картофель", "лук", "морковь", "сметана"]

Если текст не содержит продуктов, верни пустой массив: []
Не добавляй никаких пояснений, только JSON."""

PHOTO_RECOGNITION_PROMPT = """Ты — AI-помощник кулинарного бота WhatToEat.
Пользователь отправил фото содержимого холодильника или продуктов.
Твоя задача — определить все видимые продукты на фото.

Внимательно рассмотри изображение и перечисли ВСЕ продукты, которые можешь распознать.
Если не уверен — всё равно предположи, пользователь потом скорректирует.

Верни ТОЛЬКО JSON-массив строк с названиями продуктов на русском языке.
Пример: ["молоко", "яйца", "сыр", "помидоры", "огурцы"]

Не добавляй никаких пояснений, только JSON."""

VOICE_PRODUCTS_PROMPT = """Ты — AI-помощник кулинарного бота WhatToEat.
Пользователь ГОЛОСОМ продиктовал содержимое холодильника.
Текст распознан автоматически, поэтому могут быть ошибки распознавания.

Вот распознанный текст: "{text}"

Твоя задача — извлечь список продуктов, исправив возможные ошибки распознавания.
Например: "кАрица" → "курица", "кАртошка" → "картошка", "смИтана" → "сметана"

Верни ТОЛЬКО JSON-массив строк с названиями продуктов на русском языке.
Если текст не содержит продуктов, верни пустой массив: []
Не добавляй никаких пояснений, только JSON."""

RECIPE_PROMPT_TEMPLATE = """Ты — профессиональный шеф-повар и диетолог бота WhatToEat.

У пользователя есть следующие продукты: {products}

{diet_info}
{allergy_info}
{excluded_info}

Предложи {count} рецепта(ов), которые можно приготовить из этих продуктов (допускается использование базовых специй, соли, масла, воды).

Для каждого рецепта верни JSON-объект в массиве со следующей структурой:
{{
  "title": "Название блюда",
  "cooking_time": число_минут,
  "ingredients": [
    {{"name": "продукт", "amount": "количество", "have": true/false}}
  ],
  "instructions": "Пошаговая инструкция",
  "calories": число_ккал_на_порцию,
  "proteins": граммы_белков,
  "fats": граммы_жиров,
  "carbs": граммы_углеводов,
  "estimated_cost": стоимость_в_рублях,
  "portions": количество_порций
}}

Поле "have" = true если продукт есть у пользователя, false если нужно докупить.
Считай калории и БЖУ на 1 порцию.
Стоимость — примерная в рублях за все ингредиенты.

Верни ТОЛЬКО валидный JSON-массив без пояснений."""

MEAL_PLAN_PROMPT = """Ты — профессиональный диетолог бота WhatToEat.

Составь план питания на 7 дней (понедельник-воскресенье).

Параметры пользователя:
- Дневная норма калорий: {calories_goal} ккал
- Тип диеты: {diet_type}
- Аллергии: {allergies}
- Исключённые продукты: {excluded}

Для каждого дня укажи 3 приёма пищи (завтрак, обед, ужин).

Верни JSON:
{{
  "monday": {{
    "breakfast": {{"title": "...", "calories": число, "ingredients": ["..."], "instructions": "..."}},
    "lunch": {{"title": "...", "calories": число, "ingredients": ["..."], "instructions": "..."}},
    "dinner": {{"title": "...", "calories": число, "ingredients": ["..."], "instructions": "..."}}
  }},
  ...остальные дни...
  "shopping_list": ["продукт 1 — количество", "продукт 2 — количество"],
  "total_weekly_calories": число,
  "total_weekly_cost": число_рублей
}}

Верни ТОЛЬКО валидный JSON без пояснений."""

SHOPPING_LIST_PROMPT = """На основе рецепта определи, какие ингредиенты нужно докупить.

Рецепт: {recipe_title}
Ингредиенты рецепта: {all_ingredients}
У пользователя есть: {available_products}

Верни JSON-массив с недостающими продуктами:
[
  {{"name": "продукт", "amount": "количество", "estimated_price": цена_рублей}}
]

Верни ТОЛЬКО валидный JSON."""


class GigaChatService:
    """Сервис интеграции с GigaChat API"""

    AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    API_URL = "https://gigachat.devices.sberbank.ru/api/v1"
    FILES_URL = "https://gigachat.devices.sberbank.ru/api/v1/files"

    def __init__(self):
        self.auth_key = config.GIGACHAT_AUTH_KEY
        self.access_token: Optional[str] = None
        self.token_expires: float = 0

    def _get_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def _get_token(self) -> str:
        if self.access_token and time.time() < self.token_expires:
            return self.access_token

        async with httpx.AsyncClient(verify=self._get_ssl_context()) as client:
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
            response.raise_for_status()
            data = response.json()

            self.access_token = data["access_token"]
            self.token_expires = time.time() + 1740
            return self.access_token

    async def _request(self, messages: list[dict], temperature: float = 0.7,
                       max_tokens: int = 4000, model: str = "GigaChat") -> str:
        token = await self._get_token()

        async with httpx.AsyncClient(
            verify=self._get_ssl_context(),
            timeout=60.0
        ) as client:
            response = await client.post(
                f"{self.API_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def _upload_image(self, image_data: bytes,
                             filename: str = "photo.jpg",
                             mime_type: str = "image/jpeg") -> str:
        """
        Загрузка изображения в GigaChat Files API.
        Возвращает file_id для использования в сообщениях.
        """
        token = await self._get_token()

        async with httpx.AsyncClient(
            verify=self._get_ssl_context(),
            timeout=30.0
        ) as client:
            response = await client.post(
                self.FILES_URL,
                headers={
                    "Authorization": f"Bearer {token}"
                },
                files={
                    "file": (filename, image_data, mime_type)
                },
                data={
                    "purpose": "general"
                }
            )
            response.raise_for_status()
            data = response.json()

            file_id = data.get("id", "")
            logger.info(f"Uploaded image to GigaChat, file_id: {file_id}")
            return file_id

    def _extract_json(self, text: str):
        """Извлечение JSON из ответа"""
        text = text.strip()

        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            for start_char, end_char in [('[', ']'), ('{', '}')]:
                start = text.find(start_char)
                end = text.rfind(end_char)
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(text[start:end + 1])
                    except json.JSONDecodeError:
                        continue
            raise ValueError(f"Не удалось извлечь JSON: {text[:200]}")

    # ─── Основные методы ───

    async def recognize_products(self, user_text: str) -> list[str]:
        """Распознавание продуктов из текста"""
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
        """
        Извлечение продуктов из текста, распознанного из голоса.
        Использует специальный промпт, учитывающий ошибки STT.
        """
        prompt = VOICE_PRODUCTS_PROMPT.format(text=recognized_text)
        messages = [
            {"role": "user", "content": prompt}
        ]
        response = await self._request(messages, temperature=0.3)
        products = self._extract_json(response)

        if isinstance(products, list):
            return [str(p).strip().lower() for p in products if p]
        return []

    async def recognize_products_from_photo(self, image_data: bytes,
                                              mime_type: str = "image/jpeg") -> list[str]:
        """
        Попытка распознать продукты на фото через GigaChat Vision.
        
        ВАЖНО: GigaChat может не идеально справляться с фото,
        поэтому результат предлагается пользователю для корректировки.
        """
        try:
            # Загружаем изображение
            file_id = await self._upload_image(image_data, mime_type=mime_type)

            # Формируем сообщение с изображением
            messages = [
                {
                    "role": "user",
                    "content": PHOTO_RECOGNITION_PROMPT,
                    "attachments": [file_id]
                }
            ]

            # Используем модель с поддержкой vision
            response = await self._request(
                messages,
                temperature=0.3,
                model="GigaChat-Pro"  # Pro лучше работает с изображениями
            )
            products = self._extract_json(response)

            if isinstance(products, list):
                return [str(p).strip().lower() for p in products if p]
            return []

        except Exception as e:
            logger.warning(
                f"GigaChat photo recognition failed: {e}. "
                f"This is expected — GigaChat Vision is not perfect for food photos."
            )
            return []

    async def recognize_products_from_photo_fallback(
        self, image_data: bytes, mime_type: str = "image/jpeg"
    ) -> tuple[list[str], bool]:
        """
        Попытка распознать продукты на фото с fallback.
        
        Returns:
            tuple: (список продуктов, успешно ли распознано)
        """
        products = await self.recognize_products_from_photo(image_data, mime_type)

        if products and len(products) >= 2:
            # Считаем результат условно успешным
            return products, True
        else:
            # Распознавание не удалось или слишком мало продуктов
            return products, False

    async def get_recipes(self, products: list[str], count: int = 3,
                          diet_type: str = None, allergies: list[str] = None,
                          excluded: list[str] = None) -> list[dict]:
        """Генерация рецептов по продуктам"""
        diet_info = f"Тип диеты: {diet_type}" if diet_type else "Без ограничений по диете"
        allergy_info = (
            f"Аллергии (ИСКЛЮЧИТЬ): {', '.join(allergies)}" if allergies else ""
        )
        excluded_info = (
            f"Исключённые продукты: {', '.join(excluded)}" if excluded else ""
        )

        prompt = RECIPE_PROMPT_TEMPLATE.format(
            products=", ".join(products),
            count=count,
            diet_info=diet_info,
            allergy_info=allergy_info,
            excluded_info=excluded_info
        )

        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.8, max_tokens=6000)
        recipes = self._extract_json(response)

        if isinstance(recipes, dict):
            recipes = [recipes]
        return recipes if isinstance(recipes, list) else []

    async def get_shopping_list(self, recipe_title: str, all_ingredients: list[str],
                                available_products: list[str]) -> list[dict]:
        """Генерация списка покупок"""
        prompt = SHOPPING_LIST_PROMPT.format(
            recipe_title=recipe_title,
            all_ingredients=", ".join(all_ingredients),
            available_products=", ".join(available_products)
        )
        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.3)
        return self._extract_json(response)

    async def generate_meal_plan(self, calories_goal: int = 2000,
                                  diet_type: str = None,
                                  allergies: list[str] = None,
                                  excluded: list[str] = None) -> dict:
        """Генерация плана питания на неделю (Premium)"""
        prompt = MEAL_PLAN_PROMPT.format(
            calories_goal=calories_goal or 2000,
            diet_type=diet_type or "обычная",
            allergies=", ".join(allergies) if allergies else "нет",
            excluded=", ".join(excluded) if excluded else "нет"
        )
        messages = [{"role": "user", "content": prompt}]
        response = await self._request(messages, temperature=0.7, max_tokens=8000)
        return self._extract_json(response)


# Singleton
gigachat = GigaChatService()