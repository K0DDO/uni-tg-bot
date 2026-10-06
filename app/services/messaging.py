"""Подготовка ответов модели к отправке в Telegram."""

from __future__ import annotations

import html
import re

TELEGRAM_MESSAGE_LIMIT = 4096

_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*)\n?(.*?)```", re.DOTALL)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`\n]+)`")
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"\x00(PRE|CODE)(\d+)\x00")


def markdown_to_telegram_html(text: str) -> str:
    """Конвертирует типичный GitHub-Markdown в HTML для Telegram parse_mode=HTML."""
    if not text:
        return ""

    blocks: list[str] = []

    def stash_pre(match: re.Match[str]) -> str:
        code = match.group(1).strip("\n")
        blocks.append(f"<pre>{html.escape(code)}</pre>")
        return f"\x00PRE{len(blocks) - 1}\x00"

    converted = _FENCE_RE.sub(stash_pre, text)
    converted = _HEADING_RE.sub("", converted)

    inlines: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        inlines.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00CODE{len(inlines) - 1}\x00"

    converted = _CODE_RE.sub(stash_code, converted)
    converted = html.escape(converted)
    converted = _BOLD_RE.sub(r"<b>\1</b>", converted)
    converted = _ITALIC_RE.sub(r"<i>\1</i>", converted)

    def restore(match: re.Match[str]) -> str:
        kind, index_text = match.group(1), match.group(2)
        index = int(index_text)
        if kind == "PRE":
            return blocks[index]
        return inlines[index]

    return _PLACEHOLDER_RE.sub(restore, converted).strip()


def strip_markdown(text: str) -> str:
    """Убирает Markdown-разметку, оставляя читаемый обычный текст."""
    if not text:
        return ""
    plain = _FENCE_RE.sub(lambda m: m.group(1).strip("\n"), text)
    plain = _HEADING_RE.sub("", plain)
    plain = _BOLD_RE.sub(r"\1", plain)
    plain = _ITALIC_RE.sub(r"\1", plain)
    plain = _CODE_RE.sub(r"\1", plain)
    return plain.strip()


def split_telegram_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Разбивает текст на непустые части длиной не более limit символов."""
    if not text:
        return []
    if limit < 1:
        raise ValueError("limit must be >= 1")
    return [text[index : index + limit] for index in range(0, len(text), limit)]


def prepare_telegram_parts(
    text: str, limit: int = TELEGRAM_MESSAGE_LIMIT
) -> list[tuple[str, str | None]]:
    """Возвращает части ответа и parse_mode (HTML или None)."""
    if not text.strip():
        return []
    html_text = markdown_to_telegram_html(text)
    if len(html_text) <= limit:
        return [(html_text, "HTML")]
    return [(strip_markdown(part), None) for part in split_telegram_text(text, limit=limit)]
