# speech_service.py
import uuid
import time
import logging
import ssl
import httpx
from typing import Optional
from io import BytesIO

from config import config

logger = logging.getLogger(__name__)


class SaluteSpeechService:
    """
    Интеграция с SaluteSpeech API (Сбер) для распознавания голосовых сообщений.
    
    Документация: https://developers.sber.ru/docs/ru/salutespeech/overview
    
    Используется синхронное распознавание (до 60 секунд аудио).
    Формат: OGG/Opus (именно так Telegram отправляет голосовые).
    """

    AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    RECOGNIZE_URL = "https://smartspeech.sber.ru/rest/v1/speech:recognize"

    def __init__(self):
        self.auth_key = config.get_speech_auth_key()
        self.access_token: Optional[str] = None
        self.token_expires: float = 0

    def _get_ssl_context(self) -> ssl.SSLContext:
        """SSL-контекст без верификации (требование API Сбера)"""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def _get_token(self) -> str:
        """Получение OAuth-токена для SaluteSpeech"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token

        logger.info("Requesting new SaluteSpeech token...")

        async with httpx.AsyncClient(verify=self._get_ssl_context()) as client:
            response = await client.post(
                self.AUTH_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "RqUID": str(uuid.uuid4()),
                    "Authorization": f"Basic {self.auth_key}"
                },
                data={"scope": "SALUTE_SPEECH_PERS"}
            )
            response.raise_for_status()
            data = response.json()

            self.access_token = data["access_token"]
            self.token_expires = time.time() + 1740  # ~29 минут
            logger.info("SaluteSpeech token obtained successfully")
            return self.access_token

    async def recognize(self, audio_data: bytes,
                        content_type: str = "audio/ogg;codecs=opus",
                        language: str = "ru-RU") -> str:
        """
        Распознавание аудио в текст.
        
        Args:
            audio_data: Бинарные данные аудиофайла
            content_type: MIME-тип аудио
                - "audio/ogg;codecs=opus" — голосовые Telegram
                - "audio/mpeg" — MP3
                - "audio/wav" — WAV
                - "audio/x-pcm;bit=16;rate=16000" — PCM
            language: Язык распознавания
        
        Returns:
            Распознанный текст
        """
        token = await self._get_token()

        async with httpx.AsyncClient(
            verify=self._get_ssl_context(),
            timeout=30.0
        ) as client:
            response = await client.post(
                self.RECOGNIZE_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": content_type
                },
                params={
                    "language": language,
                    "model": "general",
                    # Дополнительные параметры для лучшего распознавания еды
                    "hypotheses_count": 1,
                    "enable_profanity_filter": False,
                    "no_speech_timeout": "7",
                },
                content=audio_data
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"SaluteSpeech response status: {data.get('status')}")

            # Извлекаем результат
            results = data.get("result", [])
            if not results:
                logger.warning(f"Empty recognition result: {data}")
                return ""

            # Собираем текст из всех гипотез (берём лучшую)
            text_parts = []
            for result in results:
                normalized = result.get("normalized_text", "")
                if normalized:
                    text_parts.append(normalized)
                else:
                    # Fallback на обычный текст
                    raw = result.get("text", "")
                    if raw:
                        text_parts.append(raw)

            full_text = " ".join(text_parts).strip()
            logger.info(f"Recognized text: '{full_text}'")
            return full_text

    async def recognize_from_telegram_voice(self, voice_data: bytes) -> str:
        """
        Специализированный метод для голосовых из Telegram.
        Telegram отправляет голосовые в формате OGG Opus.
        """
        return await self.recognize(
            audio_data=voice_data,
            content_type="audio/ogg;codecs=opus"
        )

    async def recognize_from_telegram_audio(self, audio_data: bytes,
                                             mime_type: str = "audio/mpeg") -> str:
        """
        Метод для аудиофайлов из Telegram (не голосовые, а файлы).
        """
        # Маппинг MIME-типов Telegram → SaluteSpeech
        mime_mapping = {
            "audio/mpeg": "audio/mpeg",
            "audio/mp3": "audio/mpeg",
            "audio/ogg": "audio/ogg;codecs=opus",
            "audio/wav": "audio/wav",
            "audio/x-wav": "audio/wav",
        }
        content_type = mime_mapping.get(mime_type, mime_type)

        return await self.recognize(
            audio_data=audio_data,
            content_type=content_type
        )


# Singleton
salute_speech = SaluteSpeechService()