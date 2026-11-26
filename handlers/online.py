import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from config import ADMIN_ID
from keyboards.online_kb import build_client_detail_keyboard
from services.online_cache import get_cached_client
from services.online_client_details import get_online_client_detail_report
from services.online_clients import get_online_clients_report

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "Онлайн")
async def handle_online(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    wait_msg = await message.answer("⏳ Запрашиваю онлайн-клиентов из панели...")
    try:
        report, keyboard = await get_online_clients_report()
        await wait_msg.edit_text(report, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        logger.exception("Ошибка при получении онлайн-клиентов")
        await wait_msg.edit_text(
            f"❌ Не удалось связаться с панелью 3X-UI:\n<code>{e}</code>",
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("onl_ref:"))
async def handle_online_refresh(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await callback.answer("Обновляю...")
    try:
        report, keyboard = await get_online_clients_report()
        if callback.message:
            await callback.message.edit_text(report, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        logger.exception("Ошибка при обновлении списка онлайн-клиентов")
        if callback.message:
            await callback.message.answer(
                f"❌ Ошибка при обновлении списка:\n<code>{e}</code>",
                parse_mode="HTML",
            )


@router.callback_query(F.data.startswith("onl_c:"))
async def handle_online_client_click(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные кнопки", show_alert=True)
        return

    _, batch_id, slot_id = parts
    entry = get_cached_client(batch_id, slot_id)
    if not entry:
        await callback.answer("Список устарел, нажмите «Онлайн» или «Обновить»", show_alert=True)
        return

    await callback.answer(f"Открываю {entry.email}...")
    try:
        detail_text = await get_online_client_detail_report(entry)
        detail_kb = build_client_detail_keyboard(batch_id)
        if callback.message:
            await callback.message.edit_text(detail_text, parse_mode="HTML", reply_markup=detail_kb)
    except Exception as e:
        logger.exception("Ошибка при получении карточки клиента %s", entry.email)
        if callback.message:
            await callback.message.edit_text(
                f"❌ Ошибка при загрузке данных клиента <b>{entry.email}</b>:\n<code>{e}</code>",
                parse_mode="HTML",
                reply_markup=build_client_detail_keyboard(batch_id),
            )
