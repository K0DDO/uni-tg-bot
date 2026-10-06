from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message
from asyncpg import Pool

from app.config import Settings
from app.llm.client import (
    LLMClient,
    LLMEmptyResponseError,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.llm.prompts import system_prompt_for
from app.services.history import HistoryService
from app.services.messaging import split_telegram_text
from app.services.users import UserService

router = Router(name="chat")

USER_ERROR_TIMEOUT = (
    "Не удалось получить ответ: сервис модели не ответил вовремя. Попробуйте позже."
)
USER_ERROR_UNAVAILABLE = (
    "Не удалось получить ответ: сервис модели временно недоступен. Попробуйте позже."
)
USER_ERROR_EMPTY = "Модель вернула пустой ответ. Переформулируйте запрос или попробуйте снова."
USER_ERROR_GENERIC = "Не удалось обработать запрос. Попробуйте позже."


@router.message(F.chat.type == "private", F.text)
async def handle_private_text(
    message: Message,
    db: Pool,
    settings: Settings,
    llm: LLMClient,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    if text.startswith("/"):
        # Неизвестные команды не отправляем в модель.
        await message.answer(
            "Неизвестная команда. Доступны: /start /study /translate /exam /settings /reset",
            parse_mode=None,
        )
        return

    users = UserService(db)
    history = HistoryService(
        db,
        max_messages=settings.history_max_messages,
        max_chars=settings.history_max_chars,
    )
    user = await users.get_or_create(message.chat.id)
    context = await history.context_for_llm(message.chat.id, text)
    system = system_prompt_for(user.mode)

    status = await message.answer("Готовлю ответ…", parse_mode=None)
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    await history.add_message(message.chat.id, "user", text)

    try:
        answer = await llm.complete(
            system=system,
            history=context,
            user_text=text,
            temperature=user.temperature,
        )
    except LLMTimeoutError:
        await status.edit_text(USER_ERROR_TIMEOUT, parse_mode=None)
        return
    except LLMEmptyResponseError:
        await status.edit_text(USER_ERROR_EMPTY, parse_mode=None)
        return
    except LLMUnavailableError:
        await status.edit_text(USER_ERROR_UNAVAILABLE, parse_mode=None)
        return
    except LLMError:
        await status.edit_text(USER_ERROR_GENERIC, parse_mode=None)
        return

    await history.add_message(message.chat.id, "assistant", answer)

    parts = split_telegram_text(answer)
    if not parts:
        await status.edit_text(USER_ERROR_EMPTY, parse_mode=None)
        return

    await status.edit_text(parts[0], parse_mode=None)
    for part in parts[1:]:
        await message.answer(part, parse_mode=None)
