"""Колбэки и обработчики"""
import json, os, subprocess, requests, re
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_admin_keyboard
from database import db
from handlers_modules.common import is_admin
from handlers_modules.groups import groups_menu, group_detail, send_group_message, handle_group_message, add_client_to_group_handler, handle_add_to_group
from handlers_modules.registration import start, start_registration, write_to_admin
# handle_client_message в handlers.py
from handlers_modules.settings import settings_menu, bot_status, restart_bot, check_errors, auto_reset_status, create_backup, show_changelog
from handlers_modules.servers import server_monitor, monitor_callback, add_server, del_server
from handlers_modules.notifications import toggle_notifications_handler, switch_to_admin_mode, status, server_status, routing_view
from handlers_modules.routing import inbounds, inbound_detail, all_clients, handle_client_button, handle_inbound_select
from handlers_modules.clients import clients_list, client_detail, handle_backup_delete, list_backups, delete_client, reset_client_traffic, show_client_ips, handle_delete_confirmation, refresh_client_status
from handlers_modules.bind_tg import bind_telegram_id, handle_tg_id_input, back_to_clients
from handlers_modules.users import users_list, user_detail, edit_user_city, edit_user_hwid, edit_user_birthday, edit_user_login, edit_user_phone, edit_user_name, toggle_user_active, delete_user, confirm_user_delete, add_user_start, handle_add_user_input, back_to_users_list, handle_user_edit_input, get_telegram_id, commands
from handlers_modules.online_stats import online, handle_server_refresh, handle_online_refresh, handle_online_info, statistics, direct_keys
from handlers_modules.links_qr import link, qr_code, handle_qr_callback, vpn_status, app_info, android_app, iphone_app, open_web_app, show_direct_keys_handler
from handlers_modules.ai_helper import ai_help, ai_answer
from handlers_modules.confirmations import confirm_edit, cancel_edit
from handlers_modules.panel_modes import panel_switch, handle_panel_switch, switch_to_client_mode, server_speed_test
import logging
logger = logging.getLogger(__name__)
HTML = "HTML"

async def ai_exit_handler(update: Update, context: CallbackContext) -> None:
    """Обработчик кнопки выхода из AI"""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('asking_ai', None)
    await query.edit_message_text("✅ <b>Вы вышли из AI-помощника.</b> Используйте кнопки меню.", parse_mode='HTML')

async def handle_copy_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    from config import BOT_NAME, SUBSCRIPTION_URL, SUBSCRIPTION_JSON_PATH, SUBSCRIPTION_EXTRA_PATH
    if "copy_sub_" in data:
        sub_id = data.replace("copy_sub_", "")
        link = SUBSCRIPTION_URL + "/sub/" + SUBSCRIPTION_EXTRA_PATH + "/" + sub_id
        await query.message.reply_text("📋 <b>Ссылка подписки:</b>\n<code>" + link + "</code>", parse_mode=HTML)
    elif "copy_json_" in data:
        sub_id = data.replace("copy_json_", "")
        link = SUBSCRIPTION_URL + "/json/" + SUBSCRIPTION_JSON_PATH + "/" + sub_id
        await query.message.reply_text("📋 <b>JSON подписка:</b>\n<code>" + link + "</code>", parse_mode=HTML)
    elif "copy_id_" in data:
        tg_id = data.replace("copy_id_", "")
        await query.message.reply_text("🆔 <b>Telegram ID:</b>\n<code>" + tg_id + "</code>", parse_mode=HTML)

async def button_callback(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатия на inline-кнопки"""
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_menu":
        from keyboards import create_user_keyboard
        await query.edit_message_text(
            "🏠 <b>Главное меню</b>\n\nВыберите действие:",
            reply_markup=create_user_keyboard(),
            parse_mode=HTML
        )
# ==================== ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ====================

async def error_handler(update: Update, context: CallbackContext) -> None:
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке сообщения: {context.error}")

    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ <b>Произошла ошибка при обработке запроса. Попробуйте позже.</b>",
                parse_mode=HTML
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")
