from pathlib import Path
from html import escape
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message

from config import ADMIN_ID, ADMIN_IDS
from handlers.client_portal import (
    get_admin_keyboard_with_portal,
    send_client_menu,
    sync_client_login_from_panel,
)
from services.clients_db import (
    ensure_client_registered,
    has_manual_user_access,
    is_admin_user,
    mark_access_notified,
    sync_client_profile_from_tg,
)
from services.panel_tg_access import has_panel_access

router = Router()


async def notify_admin_new_user(bot, message: Message, is_new: bool) -> None:
    if not ADMIN_IDS or not message.from_user:
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
        for admin_chat_id in ADMIN_IDS:
            await bot.send_message(chat_id=int(admin_chat_id), text=text, parse_mode="HTML")
    except Exception:
        pass



BASE_DIR = Path(__file__).resolve().parent.parent
ADMIN_START_IMAGE = BASE_DIR / "images" / "05.png"
CLIENT_START_IMAGE = BASE_DIR / "images" / "06.png"


async def _send_start_message(
    message: Message,
    text: str,
    reply_markup,
    image_path: Path,
) -> None:
    if image_path.is_file():
        try:
            await message.answer_photo(
                photo=FSInputFile(str(image_path)),
                caption=text,
                reply_markup=reply_markup,
            )
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=reply_markup)


@router.message(CommandStart())
async def cmd_start(message: Message):
    if not message.from_user:
        return
    uid = message.from_user.id

    if is_admin_user(uid):
        await _send_start_message(
            message,
            "Добро Пожаловать\nSLK Remastered",
            reply_markup=get_admin_keyboard_with_portal(),
            image_path=ADMIN_START_IMAGE,
        )
        return

    client_row, is_new = ensure_client_registered(
        telegram_id=uid,
        name=message.from_user.full_name,
        username=message.from_user.username,
    )
    synced = sync_client_profile_from_tg(
        telegram_id=uid,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
    )
    if synced:
        client_row = synced
    client_name = str((client_row or {}).get("name") or message.from_user.full_name or "Клиент").strip()

    client_row = await sync_client_login_from_panel(client_row) or client_row
    client_name = str((client_row or {}).get("name") or message.from_user.full_name or "Клиент").strip()

    if has_manual_user_access(uid) or await has_panel_access(uid, force_refresh=False):
        mark_access_notified(uid, notified=True)
        if CLIENT_START_IMAGE.is_file():
            try:
                await message.answer_photo(photo=FSInputFile(str(CLIENT_START_IMAGE)))
            except Exception:
                pass
        await send_client_menu(message, client_name=client_name, is_preview=False)
        return

    await notify_admin_new_user(message.bot, message, is_new=is_new)
    await _send_start_message(
        message,
        "⏳ <b>ОЖИДАНИЕ ДОСТУПА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Ваш Telegram ID: <code>{uid}</code>\n"
        "Вы добавлены в базу. Как только администратор привяжет ваш ID в панели, "
        "вам придёт уведомление и откроется меню клиента.",
        parse_mode="HTML",
        image_path=CLIENT_START_IMAGE,
    )