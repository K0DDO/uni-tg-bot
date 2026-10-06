from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class HistoryMessage:
    role: str
    content: str


def trim_history(
    messages: list[HistoryMessage],
    *,
    max_messages: int,
    max_chars: int,
    reserved_chars: int = 0,
) -> list[HistoryMessage]:
    """Оставляет новейшие сообщения в пределах лимитов, сохраняя порядок."""
    if max_messages < 1 or max_chars < 1:
        return []
    budget = max(0, max_chars - max(0, reserved_chars))
    selected: list[HistoryMessage] = []
    used_chars = 0
    for message in reversed(messages):
        length = len(message.content)
        if selected and (len(selected) >= max_messages or used_chars + length > budget):
            break
        if not selected and length > budget:
            # Даже одно сообщение не влезает — берём его целиком, лимит уже нарушен источником.
            selected.append(message)
            break
        selected.append(message)
        used_chars += length
    selected.reverse()
    return selected


class HistoryService:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        max_messages: int,
        max_chars: int,
    ) -> None:
        self._pool = pool
        self._max_messages = max_messages
        self._max_chars = max_chars

    async def list_messages(self, chat_id: int) -> list[HistoryMessage]:
        rows = await self._pool.fetch(
            """
            SELECT role, content
            FROM dialog_messages
            WHERE chat_id = $1
            ORDER BY created_at ASC, id ASC
            """,
            chat_id,
        )
        return [HistoryMessage(role=row["role"], content=row["content"]) for row in rows]

    async def context_for_llm(self, chat_id: int, current_user_text: str) -> list[dict[str, str]]:
        history = await self.list_messages(chat_id)
        trimmed = trim_history(
            history,
            max_messages=self._max_messages,
            max_chars=self._max_chars,
            reserved_chars=len(current_user_text),
        )
        return [{"role": item.role, "content": item.content} for item in trimmed]

    async def add_message(self, chat_id: int, role: str, content: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO dialog_messages (chat_id, role, content)
            VALUES ($1, $2, $3)
            """,
            chat_id,
            role,
            content,
        )

    async def clear(self, chat_id: int) -> None:
        await self._pool.execute("DELETE FROM dialog_messages WHERE chat_id = $1", chat_id)
