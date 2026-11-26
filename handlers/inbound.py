import logging
from aiogram import Router, F
from aiogram.types import Message
from config import ADMIN_ID
from services.inbounds_service import get_inbounds_report

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "Инбаунд")
async def handle_inbound(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    wait_msg = await message.answer("⏳ Запрашиваю список инбаундов...")
    try:
        report = await get_inbounds_report()
        await wait_msg.edit_text(report, parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка при получении списка инбаундов")
        await wait_msg.edit_text(f"❌ Ошибка при запросе инбаундов:\n<code>{e}</code>", parse_mode="HTML")
