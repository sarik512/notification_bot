"""Middlewares applied to every message and callback handled by the router"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, types

from config import Config
from keyboards import MENU_TEXTS
from logger import logger


class AuthMiddleware(BaseMiddleware):
    """Reject users outside ALLOWED_USERS.

    Registered for callback queries as well as messages: inline buttons live on
    in old chats, and a callback handler that skips the check is a way around
    the allow-list.
    """

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        allowed = Config.is_user_allowed(user.id) if user else not Config.ALLOWED_USERS
        if allowed:
            return await handler(event, data)

        if user:
            logger.warning(f"Unauthorized access attempt from user {user.id} (@{user.username})")

        if isinstance(event, types.CallbackQuery):
            await event.answer("⛔ Доступ запрещен", show_alert=True)
        elif isinstance(event, types.Message) and user:
            await event.answer(
                "⛔ <b>Доступ запрещен</b>\n\n"
                "У вас нет прав для использования этого бота.\n"
                f"Ваш ID: <code>{user.id}</code>\n\n"
                "Обратитесь к администратору бота для получения доступа."
            )
        return None


class MenuResetMiddleware(BaseMiddleware):
    """Pressing a main-menu button abandons the dialog in progress.

    Handlers for dialog steps are registered before the menu handlers and match
    any text, so without this "📋 Список клиентов" typed mid-dialog would be
    saved as a client name.
    """

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        state = data.get("state")
        if state is not None and getattr(event, "text", None) in MENU_TEXTS and data.get("raw_state"):
            await state.clear()
            # Filters read the state that was loaded before this middleware ran
            data["raw_state"] = None
        return await handler(event, data)
