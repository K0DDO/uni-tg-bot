from aiogram import Router

from app.handlers import chat, commands

# Команды регистрируются раньше общего текстового обработчика.
router = Router(name="lab1")
router.include_router(commands.router)
router.include_router(chat.router)
