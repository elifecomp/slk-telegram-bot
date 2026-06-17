"""Панель и переключение режимов"""
import subprocess, re, os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_admin_keyboard, create_user_keyboard, create_panel_switch_keyboard
from panel_manager import get_panels_list, set_active_panel, get_active_panel
from database import db
from handlers_modules.common import is_admin
import logging
logger = logging.getLogger(__name__)
HTML = "HTML"

async def switch_to_client_mode(update: Update, context: CallbackContext) -> None:
    """Переключает администратора в режим клиента"""
    user_id = update.effective_user.id
    user = update.effective_user

    if not is_admin(user_id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой функции</b>", parse_mode=HTML)
        return

    client = db.get_client_by_telegram_id(user_id)

    if not client:
        await update.message.reply_text(
            "⚠️ <b>Вы не зарегистрированы как клиент.</b>\n\n"
            "Для использования клиентских функций необходимо иметь учетную запись в базе данных.\n\n"
            "🔧 <i>Используйте раздел \"👤 Пользователи\" для добавления себя как клиента, "
            "либо обратитесь к другому администратору.</i>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return

    context.user_data['is_admin_in_client_mode'] = True
    context.user_data['state'] = BotState.MAIN_MENU

    await update.message.reply_text(
        f"👤 <b>Режим клиента активирован</b>\n\n"
        f"📝 <b>Логин:</b> <code>{client['login']}</code>\n"
        f"👨‍💼 <b>Имя:</b> {client['name']}\n\n"
        f"<i>Выберите действие из меню ниже:</i>",
        reply_markup=create_user_keyboard(is_admin=True),
        parse_mode=HTML
    )
    logger.info(f"Администратор {user_id} переключился в режим клиента")


async def panel_switch(update: Update, context: CallbackContext) -> None:
    """Inline-меню выбора панели"""
    if not is_admin(update.effective_user.id):
        return

    from panel_manager import _active_panel_id, get_panels_list
    panels = get_panels_list()
    active = next((p for p in panels if p['id'] == _active_panel_id), panels[0])

    keyboard = []
    for panel in panels:
        emoji = "✅ " if panel['id'] == _active_panel_id else ""
        keyboard.append([InlineKeyboardButton(
            f"{emoji}{panel['emoji']} {panel['name']}",
            callback_data=f"panel_switch_{panel['id']}"
        )])

    message = f"🔄 <b>Выбор панели</b>\n\n"
    message += f"Активная: {active['emoji']} <b>{active['name']}</b>\n"
    message += f"🔗 <code>{active['url'][:60]}...</code>"

    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )


async def handle_panel_switch(update: Update, context: CallbackContext) -> None:
    """Обрабатывает переключение панели"""
    query = update.callback_query
    panel_id = int(query.data.replace("panel_switch_", ""))

    from panel_manager import set_active_panel, get_panels_list
    set_active_panel(panel_id)

    panels = get_panels_list()
    panel = next((p for p in panels if p['id'] == panel_id), None)

    if panel:
        await query.answer(f"✅ {panel['emoji']} {panel['name']}")
        await query.edit_message_text(
            f"✅ <b>Переключено:</b> {panel['emoji']} {panel['name']}\n"
            f"🔗 <code>{panel['url'][:60]}...</code>",
            parse_mode=HTML
        )


async def panel_switch_old(update: Update, context: CallbackContext) -> None:
    """Обрабатывает выбор панели"""
    if not is_admin(update.effective_user.id):
        return

    message_text = update.message.text

    if "⬅️ Назад" in message_text or message_text == "⬅️ Назад в меню":
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "🏠 <b>Главное меню:</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return

    from panel_manager import get_panels_list, set_active_panel

    panels = get_panels_list()
    for panel in panels:
        if panel['name'] in message_text:
            set_active_panel(panel['id'])
            await update.message.reply_text(
                f"✅ <b>Переключено на панель:</b> {panel['emoji']} {panel['name']}\n"
                f"🔗 <code>{panel['url']}</code>",
                reply_markup=create_admin_keyboard(),
                parse_mode=HTML
            )
            context.user_data['state'] = BotState.MAIN_MENU
            return

    await update.message.reply_text("❌ <b>Панель не найдена</b>", parse_mode=HTML)


async def server_speed_test(update: Update, context: CallbackContext) -> None:
    """Проверка скорости сервера через Speedtest CLI"""
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🚀 <b>Запускаю Speedtest...</b>\n⏳ Подождите ~30 секунд", parse_mode='HTML')

    import subprocess
    try:
        result = subprocess.run(
            "speedtest-cli --simple --secure 2>/dev/null || speedtest-cli --simple",
            shell=True, capture_output=True, text=True, timeout=60
        )
        output = result.stdout

        if output:
            ping_match = re.search(r'Ping:\s+([\d.]+)', output)
            dl_match = re.search(r'Download:\s+([\d.]+)', output)
            ul_match = re.search(r'Upload:\s+([\d.]+)', output)

            ping = ping_match.group(1) if ping_match else "?"
            dl_speed = dl_match.group(1) if dl_match else "?"
            ul_speed = ul_match.group(1) if ul_match else "?"

            # Информация о провайдере
            isp = ""
            server = ""
            try:
                result2 = subprocess.run(
                    "speedtest-cli 2>/dev/null | grep -E 'Hosted by|Testing from'",
                    shell=True, capture_output=True, text=True, timeout=60
                )
                for line in result2.stdout.split('\n'):
                    if 'Hosted by' in line:
                        server = line.strip()
                    if 'Testing from' in line:
                        isp = line.split('(')[1].split(')')[0] if '(' in line else line.strip()
            except:
                pass

            msg = f"🚀 <b>SPEEDTEST СЕРВЕРА</b>\n\n"
            msg += f"📡 Пинг: <b>{ping} ms</b>\n"
            msg += f"📥 Загрузка: <b>{dl_speed} Mbps</b>\n"
            msg += f"📤 Отдача: <b>{ul_speed} Mbps</b>\n"
            if isp:
                msg += f"🖥 Провайдер: <b>{isp}</b>\n"
            if server:
                msg += f"📍 Сервер: <b>{server}</b>\n"
            msg += "\n"

            try:
                dl_val = float(dl_speed) if dl_speed != "?" else 0
                ul_val = float(ul_speed) if ul_speed != "?" else 0
                avg = (dl_val + ul_val) / 2
                if avg > 80:
                    emoji, comment = "🟢", "Отличная скорость!"
                elif avg > 30:
                    emoji, comment = "🟡", "Хорошая скорость"
                else:
                    emoji, comment = "🔴", "Низкая скорость"
                msg += f"{emoji} {comment}"
            except:
                pass
        else:
            msg = "❌ Не удалось измерить скорость"
    except Exception as e:
        msg = f"❌ Ошибка: {e}"

    await update.message.reply_text(msg, parse_mode='HTML')