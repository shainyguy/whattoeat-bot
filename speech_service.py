# speech_service.py
import uuid
import time
import logging
import ssl
import httpx
from typing import Optional

from config import config

logger = logging.getLogger(__name__)


class SaluteSpeechService:
    """
    SaluteSpeech API для распознавания голосовых сообщений.
    Поддерживает OGG Opus (формат голосовых Telegram).
    """

    AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    RECOGNIZE_URL = "https://smartspeech.sber.ru/rest/v1/speech:recognize"

    def __init__(self):
        self.auth_key = config.get_speech_auth_key()
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

        logger.info("Getting SaluteSpeech token...")

        async with httpx.AsyncClient(verify=self._ssl(), timeout=15.0) as client:
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

            logger.info(f"Token response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Token error: {response.text}")
                raise Exception(f"SaluteSpeech auth failed: {response.status_code} {response.text}")

            data = response.json()
            self.access_token = data["access_token"]
            self.token_expires = time.time() + 1740
            logger.info("SaluteSpeech token OK")
            return self.access_token

    async def recognize_from_telegram_voice(self, voice_bytes: bytes) -> str:
        """
        Распознавание голосового сообщения Telegram (OGG Opus).
        Возвращает распознанный текст или пустую строку.
        """
        if not voice_bytes:
            logger.warning("Empty voice data")
            return ""

        logger.info(f"Recognizing voice: {len(voice_bytes)} bytes")

        try:
            token = await self._get_token()
        except Exception as e:
            logger.error(f"Failed to get token: {e}")
            # Fallback: пробуем без SaluteSpeech
            return ""

        try:
            async with httpx.AsyncClient(verify=self._ssl(), timeout=30.0) as client:
                response = await client.post(
                    self.RECOGNIZE_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "audio/ogg;codecs=opus"
                    },
                    content=voice_bytes
                )

                logger.info(f"Recognize response: {response.status_code}")

                if response.status_code != 200:
                    logger.error(f"Recognize error: {response.text}")
                    return ""

                data = response.json()
                logger.info(f"Recognize result: {data}")

                # Извлекаем текст
                results = data.get("result", [])
                if not results:
                    # Пробуем альтернативный формат ответа
                    text = data.get("text", "")
                    if text:
                        return text
                    logger.warning("Empty result from SaluteSpeech")
                    return ""

                text_parts = []
                for r in results:
                    text = r.get("normalized_text") or r.get("text", "")
                    if text:
                        text_parts.append(text)

                result = " ".join(text_parts).strip()
                logger.info(f"Recognized: '{result}'")
                return result

        except httpx.TimeoutException:
            logger.error("SaluteSpeech timeout")
            return ""
        except Exception as e:
            logger.error(f"SaluteSpeech error: {e}", exc_info=True)
            return ""

    async def recognize_from_telegram_audio(self, audio_bytes: bytes,
                                             mime_type: str = "audio/mpeg") -> str:
        """Распознавание аудиофайлов (mp3, wav)"""
        if not audio_bytes:
            return ""

        mime_map = {
            "audio/mpeg": "audio/mpeg",
            "audio/mp3": "audio/mpeg",
            "audio/ogg": "audio/ogg;codecs=opus",
            "audio/wav": "audio/wav",
            "audio/x-wav": "audio/wav",
        }
        content_type = mime_map.get(mime_type, "audio/mpeg")

        try:
            token = await self._get_token()
        except Exception as e:
            logger.error(f"Token error: {e}")
            return ""

        try:
            async with httpx.AsyncClient(verify=self._ssl(), timeout=30.0) as client:
                response = await client.post(
                    self.RECOGNIZE_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": content_type
                    },
                    content=audio_bytes
                )

                if response.status_code != 200:
                    logger.error(f"Audio recognize error: {response.text}")
                    return ""

                data = response.json()
                results = data.get("result", [])
                parts = []
                for r in results:
                    t = r.get("normalized_text") or r.get("text", "")
                    if t:
                        parts.append(t)

                return " ".join(parts).strip()

        except Exception as e:
            logger.error(f"Audio recognize error: {e}")
            return ""


salute_speech = SaluteSpeechService()
