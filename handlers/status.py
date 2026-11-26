import logging
from aiogram import Router, F
from aiogram.types import Message
from config import ADMIN_ID
from services.status_service import get_server_status_report

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "Статус")
async def handle_status(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    wait_msg = await message.answer("⏳ Запрашиваю статус сервера панели...")
    try:
        report = await get_server_status_report()
        await wait_msg.edit_text(report, parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка при получении статуса сервера")
        await wait_msg.edit_text(f"❌ Ошибка при запросе статуса:\n<code>{e}</code>", parse_mode="HTML")
