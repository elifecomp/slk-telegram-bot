"""Уведомления и режимы"""
import requests, json, subprocess
import logging
logger = logging.getLogger(__name__)
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState, XUI_PANEL_URL, XUI_API_TOKEN
from keyboards import create_admin_keyboard, create_user_keyboard
from panel_manager import get_active_panel
from database import db
from xui_api import get_inbounds_list
from server_info import get_server_status, format_traffic
from handlers_modules.common import is_admin
HTML = "HTML"

async def toggle_notifications_handler(update: Update, context: CallbackContext) -> None:
    """Включает/выключает уведомления о подключениях"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа</b>", parse_mode=HTML)
        return

    from connection_notifier import toggle_notifications, get_notifications_status

    status = toggle_notifications()

    if status:
        await update.message.reply_text(
            "🔔 <b>Уведомления ВКЛЮЧЕНЫ</b>\n\n"
            "Вы будете получать уведомления о подключении/отключении клиентов.",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
    else:
        await update.message.reply_text(
            "🔕 <b>Уведомления ВЫКЛЮЧЕНЫ</b>\n\n"
            "Уведомления о подключении/отключении клиентов отключены.",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )

    context.user_data['state'] = BotState.MAIN_MENU

async def switch_to_admin_mode(update: Update, context: CallbackContext) -> None:
    """Возвращает администратора из клиентского режима в админ-панель"""
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой функции</b>", parse_mode=HTML)
        return

    context.user_data.pop('is_admin_in_client_mode', None)
    context.user_data['state'] = BotState.MAIN_MENU

    await update.message.reply_text(
        "⚙️ <b>Панель администратора</b>\n\n"
        "<i>Выберите действие:</i>",
        reply_markup=create_admin_keyboard(),
        parse_mode=HTML
    )
    logger.info(f"Администратор {user_id} вернулся в админ-панель")
async def admin_panel_command(update: Update, context: CallbackContext) -> None:
    """Команда /admin для возврата в админ-панель"""
    await switch_to_admin_mode(update, context)
async def client_mode_command(update: Update, context: CallbackContext) -> None:
    """Команда /client для перехода в режим клиента"""
    await switch_to_client_mode(update, context)
# ==================== АДМИНСКИЕ ФУНКЦИИ ====================

async def status(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return

    await update.message.reply_text("🔍 <b>Проверяю подключение к панели 3x-ui...</b>", parse_mode=HTML)

    def check_connection():
        try:
            inbounds = get_inbounds_list()
            return len(inbounds) > 0
        except:
            return False

    with ThreadPoolExecutor() as executor:
        future = executor.submit(check_connection)
        is_connected = future.result()

    if is_connected:
        await update.message.reply_text("✅ <b>Успешно подключено к панели 3x-ui</b>", parse_mode=HTML)
    else:
        await update.message.reply_text(
            "❌ <b>Не удалось подключиться к панели 3x-ui</b>\n\n"
            "🔧 <b>Проверьте:</b>\n"
            "• Доступность панели\n"
            "• Настройки в .env файле\n"
            "• Логины и пароли",
            parse_mode=HTML
        )
async def server_status(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return

    await update.message.reply_text("🔄 <b>Получаю информацию о сервере...</b>", parse_mode=HTML)

    def get_server_data():
        return get_server_status()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_server_data)
        server_info = future.result()

    if server_info:
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="server_refresh")]]
        await update.message.reply_text(server_info, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=HTML)
    else:
        await update.message.reply_text("❌ <b>Не удалось получить информацию о сервере</b>", parse_mode=HTML)

async def routing_view(update: Update, context: CallbackContext) -> None:
    """Показывает правила маршрутизации Xray с меню управления"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа", parse_mode=HTML)
        return

    await update.message.reply_text("🔄 <b>Получаю правила маршрутизации...</b>", parse_mode=HTML)

    def get_rules():
        from routing_view import get_routing_rules, format_rules
        rules, error = get_routing_rules()
        if error:
            return f"❌ <b>Ошибка:</b> {error}"
        return format_rules(rules)

    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_rules)
        result = future.result()

    # Inline-кнопки управления
    keyboard = [
        [InlineKeyboardButton("➕ Добавить правило", callback_data="routing_add"),
         InlineKeyboardButton("🗑️ Удалить правило", callback_data="routing_del")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="routing_refresh"),
         InlineKeyboardButton("⬅️ Закрыть", callback_data="routing_close")]
    ]

    await update.message.reply_text(
        result,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

