import logging
from aiogram import Router, F
from aiogram.types import Message
from config import ADMIN_ID, ADMIN_IDS
from services.nodes_service import get_nodes_report

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "Узлы")
async def handle_nodes(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    wait_msg = await message.answer("⏳ Запрашиваю список узлов из панели...")
    try:
        report = await get_nodes_report()
        await wait_msg.edit_text(report, parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка при получении списка узлов")
        await wait_msg.edit_text(f"❌ Ошибка при запросе узлов:\n<code>{e}</code>", parse_mode="HTML")
