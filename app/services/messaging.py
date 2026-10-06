TELEGRAM_MESSAGE_LIMIT = 4096


def split_telegram_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Разбивает текст на непустые части длиной не более limit символов."""
    if not text:
        return []
    if limit < 1:
        raise ValueError("limit must be >= 1")
    return [text[index : index + limit] for index in range(0, len(text), limit)]
