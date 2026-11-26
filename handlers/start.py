from html import escape
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import ADMIN_ID
from handlers.client_portal import (
    get_admin_keyboard_with_portal,
    send_client_menu,
)
from services.clients_db import (
    ensure_client_registered,
    is_admin_user,
    mark_access_notified,
)
from services.panel_tg_access import has_panel_access

router = Router()


async def notify_admin_new_user(bot, message: Message, is_new: bool) -> None:
    if not ADMIN_ID or not message.from_user:
        return
    uid = message.from_user.id
    full_name = escape(message.from_user.full_name or "—")
    username = escape(f"@{message.from_user.username}" if message.from_user.username else "—")
    status_line = "Зарегистрирован новый пользователь" if is_new else "Пользователь запросил доступ"
    text = (
        f"🆕 <b>{status_line}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• Имя: <b>{full_name}</b>\n"
        f"• Username: <code>{username}</code>\n"
        f"• Telegram ID: <code>{uid}</code>\n\n"
        "В панели 3X-UI <code>tgId</code> пока не найден. "
        "Добавьте его в настройках клиента — доступ откроется автоматически."
    )
    try:
        await bot.send_message(chat_id=int(ADMIN_ID), text=text, parse_mode="HTML")
    except Exception:
        pass


@router.message(CommandStart())
async def cmd_start(message: Message):
    if not message.from_user:
        return
    uid = message.from_user.id

    if is_admin_user(uid):
        await message.answer(
            "Добро Пожаловать\nSLK Remastered",
            reply_markup=get_admin_keyboard_with_portal(),
        )
        return

    client_row, is_new = ensure_client_registered(
        telegram_id=uid,
        name=message.from_user.full_name,
        username=message.from_user.username,
    )
    client_name = str((client_row or {}).get("name") or message.from_user.full_name or "Клиент").strip()

    if await has_panel_access(uid, force_refresh=True):
        mark_access_notified(uid, notified=True)
        await send_client_menu(message, client_name=client_name, is_preview=False)
        return

    await notify_admin_new_user(message.bot, message, is_new=is_new)
    await message.answer(
        "⏳ <b>ОЖИДАНИЕ ДОСТУПА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Ваш Telegram ID: <code>{uid}</code>\n"
        "Вы добавлены в базу. Как только администратор привяжет ваш ID в панели, "
        "вам придёт уведомление и откроется меню клиента.",
        parse_mode="HTML",
    )
