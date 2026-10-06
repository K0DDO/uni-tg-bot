"""Клиент OpenRouter (OpenAI-совместимый Chat Completions)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import aiohttp

from app.config import Settings

logger = logging.getLogger("app.llm")


class LLMError(Exception):
    """Базовая ошибка обращения к языковой модели."""


class LLMTimeoutError(LLMError):
    """Истёк таймаут обращения к модели."""


class LLMUnavailableError(LLMError):
    """Сервис недоступен или вернул ошибку."""


class LLMEmptyResponseError(LLMError):
    """Ответ модели пуст или без ожидаемого текста."""


class LLMClient:
    def __init__(self, settings: Settings, session: aiohttp.ClientSession | None = None) -> None:
        self._settings = settings
        self._session = session
        self._owns_session = session is None

    async def aclose(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._settings.llm_timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owns_session = True
        return self._session

    async def complete(
        self,
        *,
        system: str,
        history: list[dict[str, str]],
        user_text: str,
        temperature: float,
        request_id: str | None = None,
    ) -> str:
        request_id = request_id or uuid.uuid4().hex[:12]
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        url = f"{self._settings.openrouter_base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self._settings.openrouter_model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "LLM start request_id=%s model=%s messages=%s",
            request_id,
            self._settings.openrouter_model,
            len(messages),
        )
        started = time.perf_counter()
        session = await self._get_session()
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                body = await response.json(content_type=None)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                if response.status >= 400:
                    logger.info(
                        "LLM error request_id=%s status=%s elapsed_ms=%s",
                        request_id,
                        response.status,
                        elapsed_ms,
                    )
                    raise LLMUnavailableError(f"HTTP {response.status}")
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("LLM timeout request_id=%s elapsed_ms=%s", request_id, elapsed_ms)
            raise LLMTimeoutError("timeout") from exc
        except aiohttp.ClientError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("LLM unavailable request_id=%s elapsed_ms=%s", request_id, elapsed_ms)
            raise LLMUnavailableError("client error") from exc

        text = _extract_text(body)
        if not text:
            logger.info("LLM empty request_id=%s elapsed_ms=%s", request_id, elapsed_ms)
            raise LLMEmptyResponseError("empty")
        logger.info("LLM ok request_id=%s elapsed_ms=%s", request_id, elapsed_ms)
        return text


def _extract_text(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
    text = first.get("text")
    if isinstance(text, str):
        return text.strip()
    return ""
