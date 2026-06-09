HTML = 'HTML'
import logging
import json
import re
import base64
import os
from telegram import InputFile
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import asyncio
import subprocess

import qrcode
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from operators import get_operator
from config import WELCOME_AUDIO_PATH, ADMIN_IDS
from config import WELCOME_AUDIO_PATH
from config import ADMIN_IDS, BotState, SUBSCRIPTION_URL, SUBSCRIPTION_JSON_PATH, SUBSCRIPTION_EXTRA_PATH
from config import SUBSCRIPTION_EXTRA_PATH
from panel_manager import get_panels_list as get_all_panels, set_active_panel as switch_active_panel
from keyboards import (
    create_groups_keyboard, create_group_actions_keyboard,
    create_settings_keyboard,
    create_panel_switch_keyboard,
    create_admin_keyboard, create_user_keyboard, 
    create_inbounds_keyboard, create_clients_keyboard, create_client_detail_keyboard,
    create_users_list_keyboard, create_user_actions_keyboard, create_edit_confirmation_keyboard,
    create_cancel_keyboard, create_users_for_message_keyboard,
    create_delete_confirmation_keyboard
)
from panel_manager import get_active_panel, get_panel_name
from xui_api import (
    get_inbounds_list, get_client_online_status, get_client_last_seen, 
    get_client_connection_status, delete_client_by_email, reset_client_traffic,
    get_online_clients, get_last_online
)
from server_info import get_server_status, format_traffic
from database import db

logger = logging.getLogger(__name__)

def is_admin(user_id):
    return user_id in ADMIN_IDS
# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================

async def sync_logins(update: Update, context: CallbackContext) -> None:
    """Синхронизирует логины из панели в базу"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text("🔄 Синхронизирую логины из панели...")
    
    def do_sync():
        import sqlite3, json
        from xui_api import get_inbounds_list
        from panel_manager import get_panels_list, set_active_panel, get_active_panel
        
        original = get_active_panel()['id']
        updated = 0
        
        for panel in get_panels_list():
            set_active_panel(panel['id'])
            inbounds = get_inbounds_list()
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                for c in settings.get('clients', []):
                    email = c.get('email', '')
                    if email:
                        # Ищем клиента по имени в email
                        conn = sqlite3.connect('clients.db')
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, name, login FROM clients")
                        for row in cursor.fetchall():
                            cid, name, login = row
                            name_clean = name.lower().replace(' ', '')
                            email_clean = email.lower().replace(' ', '')
                            if (name_clean in email_clean or email_clean in name_clean) and login != email:
                                cursor.execute("UPDATE clients SET login = ? WHERE id = ?", (email, cid))
                                updated += 1
                        conn.commit()
                        conn.close()
        
        set_active_panel(original)
        return updated
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(do_sync)
        count = future.result()
    
    await update.message.reply_text(f"✅ Синхронизировано: {count} логинов")

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    
    # Сбрасываем состояние пользователя
    context.user_data.clear()
    
    # Отправляем стикер при старте
    try:
        sticker_file_id = "CAACAgIAAxkBAAI1kGohnJ35qnpyMFwhA4EfjgeEfI6TAAINDgACbTF5SQS2aZWlIIItOwQ"
        await update.message.reply_sticker(sticker_file_id)
    except Exception as e:
        logger.warning(f"Не удалось отправить стикер: {e}")
    
    # Небольшая задержка перед текстом
    await asyncio.sleep(0.5)
    
    if is_admin(user_id):
        welcome_text = f"""⚡ <b>Привет, {user.first_name}!</b>

🛡️ <b>🇷🇺 -SLK- 🇷🇺</b>
   <i>Админ-панель</i>

👇 <b>Выберите действие:</b>"""
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        context.user_data['state'] = BotState.MAIN_MENU
    else:
        # Проверяем, зарегистрирован ли пользователь
        if db.client_exists(user_id):
            client = db.get_client_by_telegram_id(user_id)
            welcome_text = f"⚡ <b>Здравствуйте, {user.first_name}!</b>"
            
            if client:
                bd = client.get("birthday", "")
                if bd:
                    try:
                        b_day, b_month, _ = bd.split(".")
                        zodiac = get_zodiac(int(b_day), int(b_month))
                        welcome_text += f"\n\n🎂 <b>День рождения:</b> {bd}\n   {zodiac}"
                    except: pass
            
            # IP, страна, город, оператор (DaData + ip-api)
            try:
                from xui_api import get_client_ips
                import requests as req
                ips = get_client_ips(client['login'])
                if ips and isinstance(ips, list) and len(ips) > 0 and ips[0] != "No IP Record":
                    ip = str(ips[0]).split(' ')[0].strip()
                    if ip and '.' in ip:
                        welcome_text += f"\n\n🌐 <b>IP:</b> <code>{ip}</code>"
                        
                        # Город и регион через DaData
                        try:
                            r = req.get(
                                f"https://suggestions.dadata.ru/suggestions/api/4_1/rs/detectAddressByIp?ip={ip}",
                                headers={"Authorization": "Token a20c77a8cc6393aee5070f10e0fc6e4116d3423c"},
                                timeout=3
                            )
                            if r.status_code == 200:
                                data = r.json()
                                loc = data.get('location', {}).get('data', {})
                                region = loc.get('region_with_type', '')
                                city = loc.get('city_with_type', '')
                                if region:
                                    welcome_text += f"\n🏙️ <b>Регион:</b> {region}"
                                if city and city != region:
                                    welcome_text += f"\n🏙️ <b>Город:</b> {city}"
                        except: pass
                        
                        # Страна и оператор через ip-api
                        try:
                            r = req.get(f"http://ip-api.com/json/{ip}?fields=country,isp", timeout=3)
                            if r.status_code == 200:
                                geo = r.json()
                                country = geo.get('country', '')
                                isp = geo.get('isp', '')
                                flags = {'Russia': '🇷🇺', 'Finland': '🇫🇮'}
                                flag = flags.get(country, '🌍')
                                welcome_text += f"\n🌍 <b>Страна:</b> {flag} {country}"
                                if isp:
                                    welcome_text += f"\n📡 <b>Оператор:</b> {isp}"
                        except: pass
            except: pass
            
            welcome_text += "\n\n👇 <b>Выберите действие:</b>"
            
            await update.message.reply_text(
                welcome_text,
                reply_markup=create_user_keyboard(),
                parse_mode='HTML'
            )
            context.user_data['state'] = BotState.MAIN_MENU
            return
        else:
            # Новый клиент — сразу регистрация
            await start_registration(update, context)
            return


async def play_welcome_audio(update: Update, context: CallbackContext) -> None:
    """Воспроизводит приветственное аудио перед регистрацией"""
    try:
        await update.message.reply_text("🎵 Загружаю приветственное сообщение...")
        
        audio_file_path = None
        possible_paths = [
            WELCOME_AUDIO_PATH,
            'welcome.mp3',
            './welcome.mp3',
            '/app/welcome.mp3',
            os.path.join(os.path.dirname(__file__), 'welcome.mp3'),
            os.path.join(os.getcwd(), 'welcome.mp3'),
            '/root/vpn_bot/welcome.mp3',
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                audio_file_path = path
                logger.info(f"✅ Найден аудиофайл: {path}")
                break
        
        if audio_file_path:
            try:
                with open(audio_file_path, 'rb') as audio_file:
                    await update.message.reply_audio(
                        audio=InputFile(audio_file, filename="welcome.mp3"),
                        caption="🎵 Добро пожаловать! Слушайте приветственное сообщение...",
                        duration=60,
                        performer="🇷🇺 -SLK- 🇷🇺",
                        title="Приветствие"
                    )
                logger.info(f"✅ Аудио успешно отправлено пользователю {update.effective_user.id}")
                return
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке аудио из {audio_file_path}: {e}")
        else:
            logger.error(f"❌ Аудиофайл не найден! Искали в: {possible_paths}")
            
            await update.message.reply_text(
                "🎵 Приветственное аудиосообщение временно недоступно.\n"
                "Пожалуйста, продолжайте регистрацию.",
                parse_mode=HTML
            )
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при отправке аудио: {e}")
        await update.message.reply_text(
            "🎵 Добро пожаловать! Приступаем к регистрации...",
            parse_mode=HTML
        )
async def start_registration(update: Update, context: CallbackContext) -> None:
    """Начало процесса регистрации"""
    await play_welcome_audio(update, context)
    welcome_text = """🌟 <b>Здравствуй, дорогой пользователь!</b>

👋 Давай мы с тобой познакомимся

💫 <b>Придумай Логин:</b>"""
    
    await update.message.reply_text(welcome_text, parse_mode=HTML)
    context.user_data['state'] = BotState.REGISTRATION_LOGIN
    context.user_data['registration_data'] = {}
async def handle_registration_login(update: Update, context: CallbackContext) -> None:
    """Обработка ввода логина"""
    login = update.message.text.strip()
    
    if len(login) < 2 or len(login) > 30:
        await update.message.reply_text(
            "❌ <b>Логин должен быть от 2 до 30 символов.</b>\n\n"
            "💫 Пожалуйста, введите логин еще раз:",
            parse_mode=HTML
        )
        return
    
    context.user_data['registration_data']['login'] = login
    context.user_data['state'] = BotState.REGISTRATION_PHONE
    
    await update.message.reply_text(
        "✅ <b>Отлично! Логин принят.</b>\n\n"
        "📱 <b>Теперь введи номер телефона в формате:</b>\n"
        "• <code>+79ххххххххх</code>\n"
        "• <code>+9936ххххххх</code>",
        parse_mode=HTML
    )
async def handle_registration_phone(update: Update, context: CallbackContext) -> None:
    """Обработка ввода телефона"""
    phone = update.message.text.strip()
    
    if not re.match(r'^(\+79\d{9}|\+9936\d{8})$', phone):
        await update.message.reply_text(
            "❌ <b>Неверный формат номера телефона.</b>\n\n"
            "📱 <b>Пожалуйста, введите номер в формате:</b>\n"
            "• <code>+79ххххххххх</code>\n"
            "• <code>+9936ххххххх</code>",
            parse_mode=HTML
        )
        return
    
    context.user_data['registration_data']['phone'] = phone
    context.user_data['state'] = BotState.REGISTRATION_NAME
    
    await update.message.reply_text(
        "✅ <b>Отлично! Номер телефона принят.</b>\n\n"
        "👤 <b>Теперь введи свое ИМЯ:</b>",
        parse_mode=HTML
    )
async def handle_registration_name(update: Update, context: CallbackContext) -> None:
    """Обработка ввода имени и завершение регистрации"""
    name = update.message.text.strip()
    
    if len(name) < 2 or len(name) > 50:
        await update.message.reply_text(
            "❌ <b>Имя должно быть от 2 до 50 символов.</b>\n\n"
            "👤 Пожалуйста, введите имя еще раз:",
            parse_mode=HTML
        )
        return
    
    user = update.effective_user
    registration_data = context.user_data.get('registration_data', {})
    
    success = db.add_client(
        telegram_id=user.id,
        login=registration_data.get('login'),
        phone=registration_data.get('phone'),
        name=name
    )
    
    if success:
        await notify_admins_about_registration(context.bot, user, registration_data, name)
        
        welcome_text = f"""🎉 <b>Регистрация завершена!</b>

✨ Добро пожаловать, <b>{name}</b>!
🔓 Теперь у тебя есть доступ к боту.

📋 <b>Твои данные:</b>
👤 <b>Логин:</b> <code>{registration_data.get('login')}</code>
📞 <b>Телефон:</b> <code>{registration_data.get('phone')}</code>

🚀 <b>Выберите действие:</b>"""
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=create_user_keyboard(),
            parse_mode=HTML
        )
        
        context.user_data['state'] = BotState.MAIN_MENU
        context.user_data.pop('registration_data', None)
    else:
        await update.message.reply_text(
            "❌ <b>Произошла ошибка при регистрации.</b>\n"
            "Возможно, такой логин уже существует.\n\n"
            "🔄 Пожалуйста, начните регистрацию заново командой /start",
            parse_mode=HTML
        )
        context.user_data.clear()
async def notify_admins_about_registration(bot, user, registration_data, name):
    """Уведомление администраторов о новой регистрации"""
    message_text = f"""🔔 <b>НОВАЯ РЕГИСТРАЦИЯ</b>

👤 <b>Пользователь:</b> {name}
📝 <b>Логин:</b> <code>{registration_data.get('login')}</code>
📞 <b>Телефон:</b> <code>{registration_data.get('phone')}</code>
🆔 <b>ID Телеграм:</b> <code>{user.id}</code>
👨‍💼 <b>Username:</b> @{user.username if user.username else 'нет'}
📛 <b>Имя в TG:</b> {user.first_name} {user.last_name or ''}"""

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message_text, parse_mode=HTML)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление администратору {admin_id}: {e}")
# ==================== ФУНКЦИИ ПЕРЕКЛЮЧЕНИЯ РЕЖИМОВ ====================


async def write_to_admin(update: Update, context: CallbackContext) -> None:
    """Клиент пишет сообщение администратору"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы</b>", parse_mode=HTML)
        return
    
    context.user_data['state'] = BotState.WRITING_TO_ADMIN
    context.user_data['client_writing'] = True
    
    await update.message.reply_sticker('CAACAgIAAxkBAAI1jGohma-WwrzzcMUL2eo3uKKtfP5NAAIDEAACFIrJSQy6GxfYgpcDOwQ')
    message = "💬 <b>Написать администратору</b>\n\n"
    message += "<b>Введите ваше сообщение:</b>\n"
    message += "<i>• Можно отправить текст\n"
    message += "• Фото с подписью\n"
    message += "• Голосовое сообщение</i>\n\n"
    message += "<i>Администратор ответит вам в ближайшее время</i>"
    
    await update.message.reply_text(
        message,
        reply_markup=create_cancel_keyboard(),
        parse_mode=HTML
    )

async def handle_client_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает сообщение от клиента и пересылает админу"""
    if not context.user_data.get('client_writing'):
        return
    
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    message_text = update.message.text
    
    # Отмена
    if message_text and message_text == "❌ Отменить":
        context.user_data.pop('client_writing', None)
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "❌ <b>Отправка отменена</b>",
            reply_markup=create_user_keyboard(),
            parse_mode=HTML
        )
        return
    
    context.user_data.pop('client_writing', None)
    context.user_data['state'] = BotState.MAIN_MENU
    
    # Формируем сообщение админу
    from datetime import datetime
    now = datetime.now()
    months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
             'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
    
    admin_msg = f"💌 <b>СООБЩЕНИЕ ОТ КЛИЕНТА</b>\n\n"
    admin_msg += f"👤 <b>Имя:</b> {client['name']}\n"
    admin_msg += f"📝 <b>Логин:</b> <code>{client['login']}</code>\n"
    admin_msg += f"📞 <b>Телефон:</b> <code>{client['phone']}</code>\n" + (f"📶 <b>Сим-карта:</b> {get_operator(client.get('phone', '')).replace(' | 📶 ', '')}\n" if get_operator(client.get('phone', '')) else "")
    admin_msg += f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
    admin_msg += f"📅 <b>Дата:</b> {now.day} {months[now.month-1]} {now.year}\n"
    admin_msg += f"🕐 <b>Время:</b> {now.strftime('%H:%M')}\n"
    admin_msg += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if update.message.photo:
        # Фото
        caption = update.message.caption or ""
        admin_msg += f"📸 <b>Фото</b>\n{caption}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_photo(admin_id, update.message.photo[-1].file_id,
                    caption=admin_msg, parse_mode=HTML)
            except: pass
    elif update.message.voice:
        # Голосовое
        admin_msg += "🎤 <b>Голосовое сообщение</b>"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, admin_msg, parse_mode=HTML)
                await context.bot.send_voice(admin_id, update.message.voice.file_id)
            except: pass
    elif message_text:
        admin_msg += f"{message_text}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, admin_msg, parse_mode=HTML)
            except: pass
    
    # Отвечаем клиенту
    await update.message.reply_text(
        "✅ <b>Сообщение отправлено!</b>\n\n"
        "<i>Администратор скоро вам ответит.</i>",
        reply_markup=create_user_keyboard(),
        parse_mode=HTML
    )


async def groups_menu(update: Update, context: CallbackContext) -> None:
    """Меню групп клиентов"""
    if not is_admin(update.effective_user.id):
        return
    
    groups = db.get_groups()
    context.user_data['state'] = BotState.GROUPS_MENU
    
    message = "👥 <b>ГРУППЫ КЛИЕНТОВ</b>\n\nВыберите группу:"
    await update.message.reply_text(
        message,
        reply_markup=create_groups_keyboard(groups),
        parse_mode=HTML
    )


async def send_group_message(update: Update, context: CallbackContext) -> None:
    """Отправляет сообщение всем клиентам в группе"""
    if not is_admin(update.effective_user.id):
        return
    
    group = context.user_data.get('selected_group')
    if not group:
        await update.message.reply_text("❌ Группа не выбрана", parse_mode=HTML)
        return
    
    context.user_data['state'] = BotState.GROUP_MESSAGE
    context.user_data['sending_to_group'] = True
    
    message = f"💌 <b>Рассылка группе:</b> {group['name']}\n\n"
    message += "<b>Введите сообщение:</b>\n"
    message += "<i>Оно будет отправлено всем клиентам в этой группе</i>"
    
    await update.message.reply_text(
        message,
        reply_markup=create_cancel_keyboard(),
        parse_mode=HTML
    )

async def handle_group_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает сообщение для группы"""
    if not context.user_data.get('sending_to_group'):
        return
    
    message_text = update.message.text
    
    if message_text == "❌ Отменить":
        context.user_data.pop('sending_to_group', None)
        context.user_data['state'] = BotState.GROUP_DETAIL_MENU
        await update.message.reply_text("❌ Отменено", parse_mode=HTML)
        return
    
    group = context.user_data.get('selected_group')
    if not group:
        return
    
    context.user_data.pop('sending_to_group', None)
    context.user_data['state'] = BotState.GROUP_DETAIL_MENU
    
    clients = db.get_clients_in_group(group['id'])
    
    if not clients:
        await update.message.reply_text("❌ В группе нет клиентов", parse_mode=HTML)
        return
    
    await update.message.reply_text(f"🔄 Отправляю {len(clients)} клиентам...", parse_mode=HTML)
    
    sent = 0
    for client in clients:
        try:
            await context.bot.send_message(
                client['telegram_id'],
                f"💌 <b>Сообщение от SLK</b>\n\n{message_text}\n\n📁 Группа: {group['name']}",
                parse_mode='HTML'
            )
            sent += 1
        except:
            pass
    
    await update.message.reply_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"<b>Группа:</b> {group['name']}\n"
        f"👥 <b>Отправлено:</b> {sent}/{len(clients)}",
        reply_markup=create_group_actions_keyboard(),
        parse_mode=HTML
    )

async def group_detail(update: Update, context: CallbackContext) -> None:
    """Детали группы"""
    if not is_admin(update.effective_user.id):
        return
    
    message_text = update.message.text
    
    if "⬅️" in message_text:
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text("🏠 Главное меню", reply_markup=create_admin_keyboard())
        return
    
    # Извлекаем название группы
    group_name = message_text.split(' (')[0].strip().replace('📁 ', '')
    
    groups = db.get_groups()
    group = next((g for g in groups if g['name'] == group_name), None)
    
    if group:
        context.user_data['selected_group'] = group
        context.user_data['state'] = BotState.GROUP_DETAIL_MENU
        
        clients = db.get_clients_in_group(group['id'])
        
        message = f"<b>{group['name']}</b>\n\n"
        message += f"👥 Клиентов: {len(clients)}\n\n"
        
        if clients:
            message += "<b>Список:</b>\n"
            for c in clients:
                message += f"  • {c['name']} — <code>{c['login']}</code>\n"
        
        await update.message.reply_text(
            message,
            reply_markup=create_group_actions_keyboard(),
            parse_mode=HTML
        )
    else:
        await update.message.reply_text("❌ Группа не найдена", parse_mode=HTML)

async def add_client_to_group_handler(update: Update, context: CallbackContext) -> None:
    """Добавляет клиента в группу"""
    if not is_admin(update.effective_user.id):
        return
    
    group = context.user_data.get('selected_group')
    if not group:
        return
    
    users = db.get_all_clients()
    context.user_data['state'] = BotState.ADD_TO_GROUP
    context.user_data['users_for_group'] = users
    
    message = f"📁 <b>{group['name']}</b> — добавление клиента\n\n"
    message += "<b>Введите логин клиента:</b>\n"
    message += "<i>Или выберите из списка ниже:</i>"
    
    # Клавиатура с пользователями
    keyboard = []
    for u in users[:20]:
        keyboard.append([f"👤 {u['name']} ({u['login']})"])
    keyboard.append(["⬅️ Отмена"])
    
    await update.message.reply_text(
        message,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode=HTML
    )

async def handle_add_to_group(update: Update, context: CallbackContext) -> None:
    """Обрабатывает добавление клиента в группу"""
    if not is_admin(update.effective_user.id):
        return
    
    message_text = update.message.text
    group = context.user_data.get('selected_group')
    
    if not group or "⬅️" in message_text:
        context.user_data['state'] = BotState.GROUP_DETAIL_MENU
        await group_detail(update, context)
        return
    
    # Извлекаем логин
    import re
    match = re.search(r'\(([^)]+)\)', message_text)
    login = match.group(1) if match else message_text.strip()
    
    client = db.get_client_by_login(login)
    if client:
        db.add_client_to_group(client['id'], group['id'])
        await update.message.reply_text(
            f"✅ <b>{client['name']}</b> добавлен в группу <b>{group['name']}</b>",
            parse_mode=HTML
        )
    else:
        await update.message.reply_text("❌ Клиент не найден", parse_mode=HTML)
    
    context.user_data['state'] = BotState.GROUP_DETAIL_MENU
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=create_group_actions_keyboard(),
        parse_mode=HTML
    )


    await update.message.reply_text("🔌 <b>Получаю информацию о прокси...</b>", parse_mode=HTML)
    
    def get_data():
        from proxy_manager import get_proxy_status
        return get_proxy_status()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_data)
        data = future.result()
    
    if data['status'] == 'error':
        await update.message.reply_text(f"❌ <b>Ошибка:</b> {data.get('error', '?')}", parse_mode=HTML)
        return
    
    status_emoji = '🟢' if data['status'] == 'active' else '🔴'
    status_text = 'Работает' if data['status'] == 'active' else 'Остановлен'
    
    message = "🔌 <b>SOCKS5 ПРОКСИ</b>\n\n"
    message += f"{status_emoji} <b>Статус:</b> {status_text}\n"
    message += f"🔗 <b>Порт:</b> {data['port']}\n"
    message += f"👥 <b>Активных подключений:</b> {data['connections']}\n\n"
    
    # Конфиг
    message += "<b>📋 Конфигурация:</b>\n"
    for line in data['config'][:5]:
        message += f"  • <code>{line[:60]}</code>\n"
    
    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="proxy_users"),
         InlineKeyboardButton("➕ Добавить", callback_data="proxy_add")],
        [InlineKeyboardButton("📊 Статистика", callback_data="proxy_stats"),
         InlineKeyboardButton("🔄 Перезагрузить", callback_data="proxy_restart")],
        [InlineKeyboardButton("📋 Логи", callback_data="proxy_logs")],
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

    if query.data == "proxy_restart":
        from proxy_manager import restart_proxy
        if restart_proxy():
            await query.edit_message_text("✅ <b>Прокси перезагружен!</b>", parse_mode=HTML)
        else:
            await query.edit_message_text("❌ <b>Ошибка перезагрузки</b>", parse_mode=HTML)
    
    elif query.data == "proxy_stats":
        from proxy_manager import get_proxy_status
        import subprocess
        data = get_proxy_status()
        # Кто подключён — IP и логины из логов
        result = subprocess.run(['ss', '-tn'], capture_output=True, text=True, timeout=5)
        connections = [l.split() for l in result.stdout.split('\n') if ':54985' in l]
        
        # Получаем логины из journalctl
        log_result = subprocess.run(['journalctl', '-u', 'danted', '--no-pager', '-n', '50'],
                                    capture_output=True, text=True, timeout=5)
        import re
        user_map = {}
        for line in log_result.stdout.split('\n'):
            match = re.search(r'username%(\w+)@([\d.]+)', line)
            if match:
                ip = match.group(2)
                # Обрезаем порт если есть
                if '.' in ip:
                    parts = ip.split('.')
                    if len(parts) == 5:  # IP с портом
                        ip = '.'.join(parts[:4])
                user_map[ip] = match.group(1)
        
        conn_info = ""
        for c in connections[:10]:
            ip = c[4].split('.')[0] if len(c) > 4 else '?'
            full_ip = c[4] if len(c) > 4 else '?'
            user = user_map.get(full_ip.split(':')[0] if ':' in full_ip else full_ip, '?')
            conn_info += f"  • {user} @ {full_ip}\n" if user != '?' else f"  • {full_ip}\n"
        
        if not conn_info:
            conn_info = "  Нет подключений"
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="proxy_back")]]
        await query.edit_message_text(
            f"📊 <b>Статистика прокси</b>\n\n"
            f"👥 <b>Подключений:</b> {data['connections']}\n"
            f"🔗 <b>Порт:</b> {data['port']}\n"
            f"🟢 <b>Статус:</b> {data['status']}\n\n"
            f"<b>Подключены:</b>\n{conn_info}",
            parse_mode=HTML
        )

    elif query.data == "proxy_users":
        from proxy_manager import get_proxy_users
        users = get_proxy_users()
        if users:
            user_list = "\n".join([f"  • <code>{u['login']}</code>" for u in users])
        else:
            user_list = "  Нет пользователей"
        await query.edit_message_text(
            f"👥 <b>Пользователи прокси</b>\n\n{user_list}",
            parse_mode=HTML
        )

    elif query.data == "proxy_add":
        context.user_data['adding_proxy_user'] = True
        await query.edit_message_text(
            "➕ <b>Добавление пользователя</b>\n\n"
            "<b>Введите логин и пароль через пробел:</b>\n"
            "<code>client3 password123</code>",
            parse_mode=HTML
        )

    elif query.data == "proxy_logs":
        import subprocess
        result = subprocess.run(['journalctl', '-u', 'danted', '--no-pager', '-n', '15'],
                               capture_output=True, text=True, timeout=5)
        logs = result.stdout.strip()[-500:]
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="proxy_back")]]
        await query.edit_message_text(
            f"📋 <b>Логи прокси</b>\n\n<code>{logs if logs else 'Нет логов'}</code>",
            parse_mode=HTML
        )

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
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    from panel_manager import _active_panel_id, get_panels_list
    
    panels = get_panels_list()
    active = next((p for p in panels if p['id'] == _active_panel_id), panels[0])
    
    message = f"🔄 <b>Выбор панели</b>\n\n"
    message += f"Активная: {active['emoji']} {active['name']}\n"
    message += f"🔗 <code>{active['url']}</code>\n\n"
    message += "<b>Выберите панель:</b>"
    
    await update.message.reply_text(
        message,
        reply_markup=create_panel_switch_keyboard(),
        parse_mode=HTML
    )

async def handle_panel_selection(update: Update, context: CallbackContext) -> None:
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




async def settings_menu(update: Update, context: CallbackContext) -> None:
    """Меню настроек бота"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>Нет доступа</b>", parse_mode=HTML)
        return
    
    context.user_data['state'] = BotState.SETTINGS_MENU
    
    message = "⚙️ <b>НАСТРОЙКИ БОТА</b>\n\nВыберите действие:"
    await update.message.reply_text(
        message,
        reply_markup=create_settings_keyboard(),
        parse_mode=HTML
    )

async def bot_status(update: Update, context: CallbackContext) -> None:
    """Показывает состояние бота"""
    if not is_admin(update.effective_user.id):
        return
    
    import psutil, os, time as time_mod
    from datetime import datetime
    
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss
    threads = process.num_threads()
    cpu = process.cpu_percent(interval=0.5)
    
    # Uptime бота
    now = datetime.now()
    start_time = datetime.fromtimestamp(process.create_time())
    uptime = now - start_time
    uptime_str = f"{uptime.days}д {uptime.seconds//3600}ч {(uptime.seconds%3600)//60}м"
    
    # Кэш
    try:
        from xui_api import get_traffic_cache_stats
        cache = get_traffic_cache_stats()
    except:
        cache = {}
    
    # База
    from database import db
    users_count = len(db.get_all_clients())
    
    # Уведомления
    try:
        from connection_notifier import get_notifications_status
        notif = "🟢 ВКЛ" if get_notifications_status() else "🔴 ВЫКЛ"
    except:
        notif = "❓"
    
    # Панель
    from panel_manager import get_active_panel
    panel = get_active_panel()
    
    message = "🤖 <b>СОСТОЯНИЕ БОТА</b>\n\n"
    message += f"⏰ <b>Аптайм:</b> {uptime_str}\n"
    message += f"⚡ <b>CPU:</b> {cpu:.1f}%\n"
    message += f"🧠 <b>Память:</b> {mem // 1024 // 1024} MB\n"
    message += f"🧵 <b>Потоков:</b> {threads}\n\n"
    
    if cache and 'error' not in cache:
        message += f"📊 <b>LRU-Кэш:</b>\n"
        message += f"  Размер: {cache.get('size', 0)}/{cache.get('max_size', 0)}\n"
        message += f"  Hit rate: {cache.get('stats', {}).get('hit_rate', 0):.1f}%\n"
        message += f"  Очисток: {cache.get('stats', {}).get('evictions', 0)}\n\n"
    
    message += f"👥 <b>В базе:</b> {users_count} пользователей\n"
    message += f"🔔 <b>Уведомления:</b> {notif}\n"
    message += f"🔄 <b>Панель:</b> {panel['emoji']} {panel['name']}\n"
    message += f"🔗 <b>URL:</b> <code>{panel['url'][:50]}...</code>\n\n"
    
    message += "✅ <b>Бот работает стабильно</b>"
    
    await update.message.reply_text(message, parse_mode=HTML)

async def restart_bot(update: Update, context: CallbackContext) -> None:
    """Перезагружает бота"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text("🔄 <b>Перезагружаю бота...</b>", parse_mode=HTML)
    import os, sys
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def check_errors(update: Update, context: CallbackContext) -> None:
    """Проверяет бота на ошибки"""
    if not is_admin(update.effective_user.id):
        return
    
    import subprocess
    result = subprocess.run(
        ['journalctl', '-u', 'SLV-bot.service', '--no-pager', '-n', '20', '-p', '3'],
        capture_output=True, text=True, timeout=5
    )
    
    errors = result.stdout.strip()
    
    if errors:
        message = f"📋 <b>ПОСЛЕДНИЕ ОШИБКИ:</b>\n\n<code>{errors[:1000]}</code>"
    else:
        message = "✅ <b>Ошибок не найдено!</b>\n\nБот работает стабильно."
    
    await update.message.reply_text(message, parse_mode=HTML)


async def auto_reset_status(update: Update, context: CallbackContext) -> None:
    """Показывает статус автосброса"""
    if not is_admin(update.effective_user.id):
        return
    
    from auto_reset import auto_reset
    from datetime import datetime
    
    now = datetime.now()
    
    # Вычисляем следующее 1 число
    if now.month == 12:
        next_reset = now.replace(year=now.year+1, month=1, day=1, hour=0, minute=1, second=0)
    else:
        next_reset = now.replace(month=now.month+1, day=1, hour=0, minute=1, second=0)
    
    days_left = (next_reset - now).days
    
    months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
             'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
    
    message = "🔄 <b>АВТОСБРОС ТРАФИКА</b>\n\n"
    message += f"📅 <b>Следующий сброс:</b> {next_reset.day} {months[next_reset.month-1]} {next_reset.year}\n"
    message += f"🕐 <b>Время:</b> 00:01\n"
    message += f"⏳ <b>Осталось:</b> {days_left} дней\n\n"
    message += "<b>При сбросе:</b>\n"
    message += "• Обнуляется трафик ВСЕХ активных клиентов\n"
    message += "• На ВСЕХ панелях\n"
    message += "• Админ получает отчёт\n\n"
    message += "<i>Сброс происходит автоматически</i>"
    
    await update.message.reply_text(message, parse_mode=HTML)


async def create_backup(update: Update, context: CallbackContext) -> None:
    """Создаёт полный бэкап бота"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text("💾 <b>Создаю бэкап...</b>", parse_mode=HTML)
    
    def do_backup():
        import subprocess, time
        name = f"SLV_bot_FINAL_{time.strftime("%Y%m%d_%H%M%S")}.tar.gz"
        path = f"/opt/SLV_Bot/backups/{name}"
        result = subprocess.run(
            f"cd / && tar -czf {path} --exclude=venv --exclude=__pycache__ --exclude='*.pyc' --exclude=logs opt/SLV_Bot/*.py opt/SLV_Bot/.env opt/SLV_Bot/*.db opt/SLV_Bot/*.mp3 opt/SLV_Bot/*.sh opt/SLV_Bot/*.txt etc/systemd/system/SLV-bot.service ",
            shell=True, capture_output=True, timeout=60
        )
        if result.returncode == 0:
            size = subprocess.run(['du', '-sh', path], capture_output=True, text=True).stdout.split()[0]
            return name, size
        return None, None
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(do_backup)
        name, size = future.result()
    
    if name:
        await update.message.reply_text(
            f"💾 <b>БЭКАП СОЗДАН!</b>\n\n"
            f"📁 <b>Файл:</b> {name}\n"
            f"📏 <b>Размер:</b> {size}\n"
            f"📂 <b>Папка:</b> /opt/SLV_Bot/backups/",
            parse_mode=HTML
        )
    else:
        await update.message.reply_text("❌ <b>Ошибка создания бэкапа</b>", parse_mode=HTML)




async def show_changelog(update: Update, context: CallbackContext) -> None:
    """Показывает что нового в обновлениях панели"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text("🔄 <b>Получаю информацию об обновлениях...</b>", parse_mode=HTML)
    
    def get_changelog():
        import requests as req
        try:
            # Получаем текущую версию
            from xui_api import get_panel_update_info
            current_info = get_panel_update_info()
            current_ver = current_info.get('currentVersion', '3.0.2')
            latest_ver = current_info.get('latestVersion', 'v3.2.0')
            
            # Получаем релизы с GitHub
            r = req.get("https://api.github.com/repos/MHSanaei/3x-ui/releases?per_page=10", timeout=10)
            if r.status_code != 200:
                return None
            
            releases = r.json()
            
            # Ищем текущую и последнюю версию
            changelogs = []
            found_current = False
            
            for release in releases:
                tag = release.get('tag_name', '')
                body = release.get('body', '')
                date = release.get('published_at', '')[:10]
                
                # Собираем изменения для текущей и всех новых версий
                if tag == latest_ver or (found_current and not found_current):
                    # Извлекаем ключевые изменения
                    lines = []
                    for line in body.split('\n'):
                        line = line.strip()
                        if line.startswith('- [') or line.startswith('- feat'):
                            # Извлекаем описание
                            import re
                            match = re.search(r'\]\s*(.+?)(?:\s*\(|$)', line)
                            if match:
                                lines.append(f"  • {match.group(1)[:80]}")
                            elif len(line) > 10:
                                clean = re.sub(r'\[.*?\]\(.*?\)', '', line)
                                lines.append(f"  • {clean[:80]}")
                    
                    changelogs.append({
                        'version': tag,
                        'date': date,
                        'changes': lines[:7]  # Топ-7 изменений
                    })
                    found_current = True
                    
                if len(changelogs) >= 2:
                    break
            
            return changelogs, current_ver, latest_ver
        except:
            return None
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_changelog)
        result = future.result()
    
    if result:
        changelogs, current_ver, latest_ver = result
        
        message = "🆕 <b>ОБНОВЛЕНИЯ ПАНЕЛИ 3X-UI</b>\n\n"
        message += f"📦 <b>У вас:</b> {current_ver}\n"
        message += f"🆕 <b>Доступна:</b> {latest_ver}\n\n"
        
        for cl in changelogs[:2]:  # только последние 2 версии
            message += f"<b>📋 {cl['version']}</b> ({cl['date']})\n"
            for change in cl['changes'][:5]:  # показываем 5 изменений
                message += f"{change}\n"
            message += "\n"
        
        message += "<i>Данные с GitHub</i>"
    else:
        message = "❌ <b>Не удалось получить информацию об обновлениях</b>"
    
    await update.message.reply_text(message, parse_mode=HTML)

async def delete_backups(update: Update, context: CallbackContext) -> None:
    """Удаляет все бэкапы"""
    if not is_admin(update.effective_user.id):
        return
    
    import os, glob
    
    backups = glob.glob('/opt/SLV_Bot/backups/*.tar.gz')
    
    if not backups:
        await update.message.reply_text("📋 <b>Нет бэкапов для удаления</b>", parse_mode=HTML)
        return
    
    # Показываем что будет удалено
    message = "🗑️ <b>УДАЛЕНИЕ БЭКАПОВ</b>\n\n"
    message += f"📁 <b>Будет удалено:</b> {len(backups)} файлов\n\n"
    for b in backups[:5]:
        name = os.path.basename(b)
        size = os.path.getsize(b)
        if size > 1024*1024*1024:
            size_str = f"{size/1024/1024/1024:.1f} GB"
        elif size > 1024*1024:
            size_str = f"{size/1024/1024:.0f} MB"
        else:
            size_str = f"{size/1024:.0f} KB"
        message += f"  • {name[:50]} — {size_str}\n"
    
    if len(backups) > 5:
        message += f"  ... и ещё {len(backups)-5}\n"
    
    message += "\n⚠️ <b>Подтвердите удаление:</b>"
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить все", callback_data="backup_delete_confirm"),
         InlineKeyboardButton("❌ Отмена", callback_data="backup_delete_cancel")]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

async def handle_backup_delete(update: Update, context: CallbackContext) -> None:
    """Обрабатывает удаление бэкапов"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "backup_delete_cancel":
        await query.edit_message_text("❌ <b>Удаление отменено</b>", parse_mode=HTML)
        return
    
    if query.data == "backup_delete_confirm":
        import os, glob
        backups = glob.glob('/opt/SLV_Bot/backups/*.tar.gz')
        count = len(backups)
        
        for b in backups:
            try:
                os.remove(b)
            except:
                pass
        
        await query.edit_message_text(
            f"✅ <b>Удалено {count} бэкапов!</b>\n\n"
            f"💾 Место освобождено.",
            parse_mode=HTML
        )

async def list_backups(update: Update, context: CallbackContext) -> None:
    """Показывает список бэкапов"""
    if not is_admin(update.effective_user.id):
        return
    
    import os, glob
    
    backups = sorted(glob.glob('/opt/SLV_Bot/backups/*.tar.gz'), reverse=True)
    
    if not backups:
        await update.message.reply_text("📋 <b>Список бэкапов пуст</b>", parse_mode=HTML)
        return
    
    message = "📋 <b>СПИСОК БЭКАПОВ</b>\n\n"
    
    for i, b in enumerate(backups[:10], 1):
        name = os.path.basename(b)
        size = os.path.getsize(b)
        # Форматируем размер
        if size > 1024 * 1024 * 1024:
            size_str = f"{size / 1024 / 1024 / 1024:.1f} GB"
        elif size > 1024 * 1024:
            size_str = f"{size / 1024 / 1024:.0f} MB"
        else:
            size_str = f"{size / 1024:.0f} KB"
        
        message += f"{i}. <code>{name[:50]}</code> — {size_str}\n"
    
    if len(backups) > 10:
        message += f"\n<i>... и ещё {len(backups) - 10}</i>"
    
    await update.message.reply_text(message, parse_mode=HTML)


async def show_changelog(update: Update, context: CallbackContext) -> None:
    """Показывает что нового в обновлениях"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text("🔄 <b>Получаю информацию...</b>", parse_mode=HTML)
    
    def get_changelog():
        import requests as req, re
        try:
            from xui_api import get_panel_update_info
            info = get_panel_update_info()
            current = info.get('currentVersion', '3.0.2')
            latest = info.get('latestVersion', 'v3.2.0')
            
            r = req.get("https://api.github.com/repos/MHSanaei/3x-ui/releases?per_page=5", timeout=10)
            if r.status_code != 200:
                return None
            
            releases = r.json()
            changelogs = []
            
            for rel in releases:
                tag = rel.get('tag_name', '')
                date = rel.get('published_at', '')[:10]
                body = rel.get('body', '')
                
                changes = []
                for line in body.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('<'):
                        continue
                    # Извлекаем текст из [текст](url)
                    match = re.search(r'\[([^\]]+)\]', line)
                    if match:
                        text = match.group(1)
                        # Очищаем префиксы
                        text = re.sub(r'^feat\([^)]*\):\s*', '', text)
                        text = re.sub(r'^feat:\s*', '', text)
                        text = re.sub(r'^fix\([^)]*\):\s*', '', text)
                        text = re.sub(r'^fix:\s*', '', text)
                        text = text.strip()
                        if len(text) > 10:
                            changes.append(text)
                
                if changes:
                    changelogs.append({
                        'version': tag,
                        'date': date,
                        'changes': changes[:5]
                    })
            
            return changelogs, current, latest
        except:
            return None
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_changelog)
        result = future.result()
    
    if result:
        changelogs, current, latest = result
        
        message = "🆕 <b>ОБНОВЛЕНИЯ ПАНЕЛИ 3X-UI</b>\n\n"
        message += f"📦 <b>У вас:</b> {current}\n"
        message += f"🆕 <b>Доступна:</b> {latest}\n\n"
        
        for cl in changelogs[:2]:  # только последние 2 версии
            message += f"📋 <b>{cl['version']}</b> ({cl['date']})\n"
            for change in cl['changes']:
                message += f"  • {change}\n"
            message += "\n"
        
        message += "<i>Данные с GitHub</i>"
    else:
        message = "❌ <b>Не удалось получить информацию</b>"
    
    await update.message.reply_text(message, parse_mode=HTML)

# ==================== МОНИТОРИНГ СЕРВЕРОВ ====================

def load_servers():
    try:
        with open('/opt/SLV_Bot/servers.txt') as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def save_servers(servers):
    with open('/opt/SLV_Bot/servers.txt', 'w') as f:
        for ip in servers:
            f.write(ip + '\n')

def ping_server(ip, port=22):
    """Проверяет доступность сервера через TCP (fallback на ICMP)"""
    import subprocess, socket
    # Сначала пробуем TCP
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        start = __import__('time').time()
        result = sock.connect_ex((ip, port))
        elapsed = (__import__('time').time() - start) * 1000
        sock.close()
        if result == 0:
            return elapsed
    except:
        pass
    # Если TCP не сработал — пробуем ICMP
    try:
        result = subprocess.run(['ping', '-c', '1', '-W', '2', ip], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            import re
            match = re.search(r'time=(\d+\.?\d*)', result.stdout)
            return float(match.group(1)) if match else 0
    except:
        pass
    return None

async def monitor_callback(update: Update, context: CallbackContext) -> None:
    """Обрабатывает inline-кнопки мониторинга"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "mon_add":
        context.user_data['waiting_for_server'] = True
        await query.edit_message_text("➕ <b>Введите IP сервера:</b>", parse_mode='HTML')
        return
    
    elif data == "mon_del":
        servers = load_servers()
        if not servers:
            await query.edit_message_text("📋 <b>Список пуст</b>", parse_mode='HTML')
            return
        keyboard = [[InlineKeyboardButton(f"🗑️ {ip}", callback_data=f"mon_del_{ip}")] for ip in servers]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="mon_refresh")])
        await query.edit_message_text("🗑️ <b>Выберите сервер для удаления:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return
    
    elif data.startswith("mon_del_"):
        ip = data.replace("mon_del_", "")
        servers = load_servers()
        if ip in servers:
            servers.remove(ip)
            save_servers(servers)
        await query.answer(f"✅ {ip} удалён")
        await server_monitor(update, context, query)
        return
    
    elif data == "mon_refresh":
        await query.answer("🔄 Обновляю...")
        await server_monitor(update, context, query)
        return
    
    elif data == "mon_back":
        await query.edit_message_text("⚙️ <b>Настройки</b>", parse_mode='HTML')
        return


async def server_monitor(update: Update, context: CallbackContext, query=None) -> None:
    """Показывает список серверов с кнопками"""
    if not is_admin(update.effective_user.id):
        return
    
    servers = load_servers()
    message = "🖥️ <b>МОНИТОРИНГ СЕРВЕРОВ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if servers:
        for ip in servers:
            status = ping_server(ip)
            if status is not None:
                message += f"🟢 <code>{ip}</code> — {status:.0f} ms\n"
            else:
                message += f"🔴 <code>{ip}</code> — не отвечает\n"
    else:
        message += "📋 Список серверов пуст\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить сервер", callback_data="mon_add")],
        [InlineKeyboardButton("🗑️ Удалить сервер", callback_data="mon_del")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="mon_refresh")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="mon_back")],
    ]
    
    if query is not None:
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def add_server(update: Update, context: CallbackContext) -> None:
    """Добавляет сервер в мониторинг"""
    if not is_admin(update.effective_user.id):
        return
    try:
        ip = context.args[0]
        servers = load_servers()
        if ip not in servers:
            servers.append(ip)
            save_servers(servers)
            await update.message.reply_text(f"✅ <b>Сервер {ip} добавлен!</b>", parse_mode='HTML')
        else:
            await update.message.reply_text(f"⚠️ <b>{ip}</b> уже в списке", parse_mode='HTML')
    except:
        await update.message.reply_text("❌ Используйте: /addserver IP", parse_mode='HTML')

async def del_server(update: Update, context: CallbackContext) -> None:
    """Удаляет сервер из мониторинга"""
    if not is_admin(update.effective_user.id):
        return
    try:
        ip = context.args[0]
        servers = load_servers()
        if ip in servers:
            servers.remove(ip)
            save_servers(servers)
            await update.message.reply_text(f"✅ <b>Сервер {ip} удалён!</b>", parse_mode='HTML')
        else:
            await update.message.reply_text(f"⚠️ <b>{ip}</b> не найден", parse_mode='HTML')
    except:
        await update.message.reply_text("❌ Используйте: /delserver IP", parse_mode='HTML')


# ==================== ПРОВЕРКА ОБНОВЛЕНИЙ БОТА ====================
import asyncio as asyncio_bot_upd

BOT_VERSION = "1.3.0"
GITHUB_RAW = "https://raw.githubusercontent.com/elifecomp/slk-telegram-bot/main"

async def check_bot_updates():
    """Проверяет обновления бота на GitHub раз в час"""
    await asyncio_bot_upd.sleep(10)
    while True:
        try:
            import requests
            r = requests.get(f"{GITHUB_RAW}/version.txt", timeout=10)
            if r.status_code == 200:
                latest = r.text.strip()
                if latest != BOT_VERSION:
                    for admin_id in ADMIN_IDS:
                        try:
                            await application.bot.send_message(admin_id,
                                f"🆕 <b>ОБНОВЛЕНИЕ БОТА!</b>\n━━━━━━━━━━━━━━━━━\n"
                                f"📦 Версия: {latest}\n"
                                f"📋 Текущая: {BOT_VERSION}\n\n"
                                f"Выполните для обновления:\n"
                                f"<code>cd /opt/SLV_Bot && git pull && systemctl restart SLV-bot</code>",
                                parse_mode='HTML')
                        except: pass
        except: pass
        await asyncio_bot_upd.sleep(3600)


async def check_bot_update_manual(update: Update, context: CallbackContext) -> None:
    """Ручная проверка обновлений бота"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text("🔄 <b>Проверяю обновления бота...</b>", parse_mode='HTML')
    
    import requests
    try:
        r = requests.get(f"{GITHUB_RAW}/version.txt", timeout=10)
        if r.status_code == 200:
            latest = r.text.strip()
            if latest != BOT_VERSION:
                await update.message.reply_text(
                    f"🆕 <b>ДОСТУПНО ОБНОВЛЕНИЕ!</b>\n━━━━━━━━━━━━━━━━━\n"
                    f"📦 Новая версия: {latest}\n"
                    f"📋 Текущая: {BOT_VERSION}\n\n"
                    f"Для обновления выполните:\n"
                    f"<code>cd /opt/SLV_Bot && git pull && systemctl restart SLV-bot</code>",
                    parse_mode='HTML')
            else:
                await update.message.reply_text(
                    f"✅ <b>У вас актуальная версия:</b> {BOT_VERSION}",
                    parse_mode='HTML')
        else:
            await update.message.reply_text("❌ Не удалось проверить обновления", parse_mode='HTML')
    except:
        await update.message.reply_text("❌ Ошибка подключения к GitHub", parse_mode='HTML')


async def show_cache(update: Update, context: CallbackContext) -> None:
    """Показывает статистику кэша"""
    if not is_admin(update.effective_user.id):
        return
    
    try:
        from xui_api import get_traffic_cache_stats
        stats = get_traffic_cache_stats()
        
        if stats and 'error' not in stats:
            message = "📊 <b>СТАТИСТИКА LRU-КЭША</b>\n\n"
            message += f"📦 <b>Размер:</b> {stats['size']}/{stats['max_size']} ({stats['usage_percent']:.1f}%)\n"
            message += f"🟢 <b>Активных:</b> {stats['active_records']}\n"
            message += f"🔴 <b>Неактивных:</b> {stats['inactive_records']}\n"
            message += f"⏱️ <b>Средний возраст:</b> {stats['avg_age_minutes']:.1f} мин\n"
            message += f"🎯 <b>Hit rate:</b> {stats['stats']['hit_rate']:.1f}%\n"
            message += f"🧹 <b>Очисток:</b> {stats['stats']['evictions']}\n"
        else:
            message = "❌ Статистика недоступна"
    except:
        message = "❌ Ошибка получения статистики"
    
    await update.message.reply_text(message, parse_mode=HTML)

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

async def handle_routing_callback(update: Update, context: CallbackContext) -> None:
    """Обрабатывает inline-кнопки маршрутов"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "routing_close":
        await query.edit_message_text("🛡️ Маршрутизация закрыта", parse_mode=HTML)
        return
    
    if data == "routing_refresh":
        from routing_view import get_routing_rules, format_rules
        rules, error = get_routing_rules()
        if error:
            await query.answer("Ошибка получения правил", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить правило", callback_data="routing_add"),
             InlineKeyboardButton("🗑️ Удалить правило", callback_data="routing_del")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="routing_refresh"),
             InlineKeyboardButton("⬅️ Закрыть", callback_data="routing_close")]
        ]
        
        try:
            await query.edit_message_text(
                format_rules(rules),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=HTML
            )
        except:
            await query.answer("✅ Обновлено", show_alert=False)
        return
    
    if data == "routing_add":
        await query.edit_message_text(
            "➕ <b>ДОБАВЛЕНИЕ ПРАВИЛА</b>\n\n"
            "<b>Формат команды:</b>\n"
            "<code>/addroute тип:значение:действие</code>\n\n"
            "<b>Примеры:</b>\n"
            "<code>/addroute domain:netflix.com:proxy</code>\n"
            "<code>/addroute geoip:us:block</code>\n"
            "<code>/addroute geosite:netflix:proxy</code>\n\n"
            "<b>Типы:</b> domain, geoip, geosite\n"
            "<b>Действия:</b> direct, proxy, block",
            parse_mode=HTML
        )
        return
    
    if data == "routing_del":
        await query.edit_message_text(
            "🗑️ <b>УДАЛЕНИЕ ПРАВИЛА</b>\n\n"
            "Введите номер правила для удаления:\n"
            "<code>/delroute 3</code>\n\n"
            "<i>Номера видны в списке правил</i>",
            parse_mode=HTML
        )
        return


    """Показывает правила маршрутизации Xray"""
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
    
    await update.message.reply_text(result, parse_mode=HTML)


async def add_route_command(update: Update, context: CallbackContext) -> None:
    """Добавляет правило маршрутизации: /addroute domain:site.com:block"""
    if not is_admin(update.effective_user.id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /addroute domain:site.com:block", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔧 Добавление правила через конфиг Xray...\n<i>В разработке</i>", parse_mode=HTML)

async def del_route_command(update: Update, context: CallbackContext) -> None:
    """Удаляет правило: /delroute 3"""
    if not is_admin(update.effective_user.id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /delroute 3", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔧 Удаление правила...\n<i>В разработке</i>", parse_mode=HTML)

async def inbounds(update: Update, context: CallbackContext) -> None:

    if not is_admin(update.effective_user.id):

        await update.message.reply_text("⛔  <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)

        return

    

    await update.message.reply_text("🔄 <b>Получаю список инбаундов...</b>", parse_mode=HTML)

    

    def get_inbounds_data():

        return get_inbounds_list()

    

    with ThreadPoolExecutor() as executor:

        future = executor.submit(get_inbounds_data)

        inbounds_list = future.result()

    

    if inbounds_list:

        context.user_data['inbounds_list'] = inbounds_list

        context.user_data['state'] = BotState.INBOUNDS_MENU

        keyboard = create_inbounds_keyboard(inbounds_list)

        

        message = f"📡 <b>Инбаунды:</b> {len(inbounds_list)}\n\n"

        

        for i, inbound in enumerate(inbounds_list, 1):

            remark = inbound.get('remark', 'Без названия')

            protocol = inbound.get('protocol', '?').upper()

            port = inbound.get('port', '?')

            enable = inbound.get('enable', False)

            status = "🟢" if enable else "🔴"

            clients_count = len(inbound.get('clientStats', []))

            total_up = inbound.get('up', 0)

            total_down = inbound.get('down', 0)

            

            message += f"{i}. {status} <b>{remark}</b>\n"

            message += f"   📡 {protocol}:{port} | 👥 {clients_count} клиентов\n"

            message += f"   📊 ↑{format_traffic(total_up)} ↓{format_traffic(total_down)}\n\n"

        

        message += "🔍 <b>Выберите инбаунд для просмотра клиентов:</b>"

        

        await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)

    else:

        await update.message.reply_text(

            "❌  <b>Не удалось получить список инбаундов или инбаунды отсутствуют</b>\n\n"

            "🔧 <b>Возможные причины:</b>\n"

            "• Проблемы с подключением к панели\n"

            "• Неправильные учетные данные\n"

            "• На панели нет созданных инбаундов",

            reply_markup=create_admin_keyboard(),

            parse_mode=HTML

        )

        context.user_data['state'] = BotState.MAIN_MENU
async def inbound_detail(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    inbound_name = update.message.text
    
    if inbound_name == "⬅️ Назад в меню":
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "🏠 <b>Главное меню:</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return
    
    inbounds_list = context.user_data.get('inbounds_list', [])
    selected_inbound = None
    
    for inbound in inbounds_list:
        remark = inbound.get('remark', '')
        if remark == inbound_name:
            selected_inbound = inbound
            break
    
    if selected_inbound:
        clients_info = "❌  <b>Нет клиентов</b>"
        client_stats = selected_inbound.get('clientStats', [])
        if client_stats:
            active = sum(1 for c in client_stats if c.get('enable', True))
            clients_info = f"👥 <b>Клиентов:</b> {len(client_stats)} (🟢 {active} активных)\n"
        
        security_info = ""
        protocol = selected_inbound.get('protocol', '').lower()
        
        stream_settings = selected_inbound.get('streamSettings', {})
        
        if isinstance(stream_settings, str):
            try:
                if stream_settings.strip():
                    stream_settings = json.loads(stream_settings)
                else:
                    stream_settings = {}
            except json.JSONDecodeError:
                stream_settings = {}
        
        if isinstance(stream_settings, dict):
            security_settings = stream_settings.get('security', '')
            if security_settings:
                security_info += f"  🔐 <b>Безопасность:</b> {security_settings.upper()}\n"
            
            tls_settings = stream_settings.get('tlsSettings', {})
            if isinstance(tls_settings, dict):
                server_name = tls_settings.get('serverName', '')
                if server_name:
                    security_info += f"  🌐 <b>SNI:</b> {server_name}\n"
                
                alpn = tls_settings.get('alpn', [])
                if alpn:
                    security_info += f"  🔄 <b>ALPN:</b> {', '.join(alpn)}\n"
            
            network = stream_settings.get('network', 'tcp')
            security_info += f"  📡 <b>Сеть:</b> {network.upper()}\n"
            
            if network == 'ws':
                ws_settings = stream_settings.get('wsSettings', {})
                if isinstance(ws_settings, dict):
                    path = ws_settings.get('path', '')
                    if path:
                        security_info += f"  🛣️ <b>Путь:</b> {path}\n"
                    
                    headers = ws_settings.get('headers', {})
                    if isinstance(headers, dict):
                        host = headers.get('Host', '')
                        if host:
                            security_info += f"  🏠 <b>Host:</b> {host}\n"
            
            elif network == 'grpc':
                grpc_settings = stream_settings.get('grpcSettings', {})
                if isinstance(grpc_settings, dict):
                    service_name = grpc_settings.get('serviceName', '')
                    if service_name:
                        security_info += f"  🔧 <b>Сервис:</b> {service_name}\n"
        
        settings = selected_inbound.get('settings', {})
        if isinstance(settings, str):
            try:
                if settings.strip():
                    settings = json.loads(settings)
                else:
                    settings = {}
            except json.JSONDecodeError:
                settings = {}
        
        if isinstance(settings, dict):
            clients_settings = settings.get('clients', [])
            if clients_settings:
                for client in clients_settings:
                    if isinstance(client, dict):
                        flow = client.get('flow', '')
                        if flow:
                            security_info += f"  🌊 <b>Flow:</b> {flow}\n"
                        break
        
        if not security_info:
            security_info = "  🔐 <b>Безопасность:</b> Базовая\n"
            security_info += f"  📡 <b>Протокол:</b> {protocol.upper()}\n"
            security_info += f"  🔌 <b>Порт:</b> {selected_inbound.get('port', 'N/A')}\n"
        
        message = f"📡 <b>Инбаунд:</b> {inbound_name}\n\n"
        message += f"🆔 <b>ID:</b> {selected_inbound.get('id', 'N/A')}\n"
        message += f"🔌 <b>Порт:</b> {selected_inbound.get('port', 'N/A')}\n"
        message += f"📊 <b>Протокол:</b> {selected_inbound.get('protocol', 'N/A')}\n"
        message += f"💾 <b>Трафик:</b> ↑{format_traffic(selected_inbound.get('up', 0))} ↓{format_traffic(selected_inbound.get('down', 0))}\n"
        message += f"🔒 <b>Включен:</b> {'✅' if selected_inbound.get('enable', False) else '❌'}\n\n"
        
        message += "👥 <b>Клиенты:</b>\n"
        message += clients_info + "\n"
        
        message += "🛡️ <b>Безопасность:</b>\n"
        message += security_info
        
        await update.message.reply_text(message, parse_mode=HTML)
    else:
        await update.message.reply_text("❌ <b>Инбаунд не найден</b>", parse_mode=HTML)
async def all_clients(update: Update, context: CallbackContext) -> None:
    """Inline-меню выбора инбаунда"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text("🔄 <b>Получаю список инбаундов...</b>", parse_mode=HTML)
    
    def get_data():
        from xui_api import get_inbounds_list
        return get_inbounds_list()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_data)
        inbounds = future.result()
    
    if not inbounds:
        await update.message.reply_text("❌ <b>Нет инбаундов</b>", parse_mode=HTML)
        return
    
    keyboard = []
    for inbound in inbounds:
        clients_count = len(inbound.get('clientStats', []))
        remark = inbound.get('remark', '?').strip()
        keyboard.append([InlineKeyboardButton(
            f"{remark} ({clients_count} клиентов)",
            callback_data=f"inbound_select_{inbound['id']}"
        )])
    
    await update.message.reply_text(
        "📡 <b>ВЫБОР ИНБАУНДА</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

async def handle_inbound_select(update: Update, context: CallbackContext) -> None:
    """Показывает клиентов инбаунда inline-кнопками"""
    query = update.callback_query
    await query.answer("👥 Загружаю клиентов...")
    
    inbound_id = int(query.data.replace("inbound_select_", ""))
    
    def get_clients():
        from xui_api import get_inbounds_list
        inbounds = get_inbounds_list()
        for inbound in inbounds:
            if inbound['id'] == inbound_id:
                return inbound
        return None
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_clients)
        inbound = future.result()
    
    if not inbound:
        await query.edit_message_text("❌ Инбаунд не найден", parse_mode=HTML)
        return
    
    clients = inbound.get('clientStats', [])
    remark = inbound.get('remark', '?').strip()
    
    keyboard = []
    row = []
    for c in clients[:30]:
        email = c.get('email', '?')
        row.append(InlineKeyboardButton(
            f"👤 {email[:20]}",
            callback_data=f"client_btn_{email}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_inbounds")])
    
    context.user_data['inbounds_list'] = [inbound]
    context.user_data['selected_inbound'] = inbound
    context.user_data['clients'] = clients
    
    await query.edit_message_text(
        f"👥 <b>{remark}</b> — {len(clients)} клиентов\n\n<i>Выберите клиента:</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

async def handle_client_button(update: Update, context: CallbackContext) -> None:
    """Показывает информацию о клиенте по inline-кнопке"""
    query = update.callback_query
    await query.answer("📊 Загружаю информацию...")
    
    data = query.data
    
    if data == "back_to_inbounds":
        await query.answer("⬅️ Возврат к инбаундам...")
        # Возврат к списку инбаундов
        def get_data():
            from xui_api import get_inbounds_list
            return get_inbounds_list()
        
        with ThreadPoolExecutor() as executor:
            future = executor.submit(get_data)
            inbounds = future.result()
        
        keyboard = []
        for inbound in inbounds:
            clients_count = len(inbound.get('clientStats', []))
            remark = inbound.get('remark', '?').strip()
            keyboard.append([InlineKeyboardButton(
                f"{remark} ({clients_count} клиентов)",
                callback_data=f"inbound_select_{inbound['id']}"
            )])
        
        await query.edit_message_text(
            "📡 <b>ВЫБОР ИНБАУНДА</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=HTML
        )
        return
    
    email = data.replace("client_btn_", "")
    
    def get_client_info():
        from xui_api import get_inbounds_list
        inbounds = get_inbounds_list()
        for inbound in inbounds:
            for c in inbound.get('clientStats', []):
                if c.get('email') == email:
                    return c, inbound
        return None, None
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_client_info)
        client, inbound = future.result()
    
    if client:
        up = client.get('up', 0)
        down = client.get('down', 0)
        total = up + down
        total_limit = client.get('total', 0)
        limit_str = format_traffic(total_limit) if total_limit > 0 else '♾️'
        status = '🟢 Активен' if client.get('enable', True) else '🔴 Отключён'
        
        message = f"👤 <b>Детальная информация о клиенте</b>\n\n"
        message += f"📧 <b>Email:</b> {email}\n"
        message += f"🆔 <b>ID:</b> {client.get('id', '?')}\n"
        message += f"📡 <b>Инбаунд:</b> {inbound.get('remark', '?').strip()}\n"
        message += f"🔌 <b>Протокол:</b> {inbound.get('protocol', '?').upper()}:{inbound.get('port', '?')}\n"
        message += f"💾 <b>Трафик:</b> ↑{format_traffic(up)} ↓{format_traffic(down)}\n"
        message += f"📊 <b>Всего:</b> {format_traffic(total)}\n"
        message += f"🔒 <b>Статус:</b> {status}\n"
        
        # UUID и Sub ID
        try:
            import json
            settings = inbound.get('settings', {})
            if isinstance(settings, str):
                settings = json.loads(settings) if settings.strip() else {}
            if isinstance(settings, dict):
                for sc in settings.get('clients', []):
                    if sc.get('email') == email:
                        message += f"🔑 <b>UUID:</b> <code>{sc.get('id', '?')}</code>\n"
                        sub_id = sc.get('subId', '')
                        if sub_id:
                            message += f"📋 <b>Sub ID:</b> <code>{sub_id}</code>\n"
                            message += f"🔗 <b>Ссылка:</b> <code>{SUBSCRIPTION_URL}/sub/{SUBSCRIPTION_EXTRA_PATH}/{sub_id}</code>\n"
                        break
        except:
            pass
        
        # Лимит
        if total_limit > 0:
            pct = total / total_limit * 100 if total_limit > 0 else 0
            message += f"📈 <b>Лимит:</b> {limit_str} ({pct:.1f}%)\n"
        else:
            message += f"📈 <b>Лимит:</b> ♾️ Безлимит\n"
        
        # Срок
        expiry = client.get('expiryTime', 0)
        if expiry > 0:
            from datetime import datetime
            dt = datetime.fromtimestamp(expiry / 1000)
            days = (expiry / 1000 - datetime.now().timestamp()) / 86400
            message += f"⏰ <b>Срок:</b> {dt.strftime('%d.%m.%Y')}\n"
            message += f"📅 <b>Осталось:</b> {int(days)} дн.\n" if days > 0 else "❌ Истек\n"
        else:
            message += f"⏰ <b>Срок:</b> ♾️ Бессрочно\n"
        
        # Flow
        flow = client.get('flow', '')
        if flow:
            message += f"🌊 <b>Flow:</b> {flow}\n"
        
        # IP, страна, оператор
        try:
            from xui_api import get_client_ips
            import requests as req
            ips = get_client_ips(email)
            if ips and isinstance(ips, list) and len(ips) > 0:
                ip = str(ips[0]).split(' ')[0].strip()
                if ip and '.' in ip:
                    message += f"🌐 <b>IP:</b> <code>{ip}</code>\n"
                    try:
                        r = req.get(f"http://ip-api.com/json/{ip}?fields=country,isp", timeout=3)
                        if r.status_code == 200:
                            geo = r.json()
                            country = geo.get('country', '')
                            isp = geo.get('isp', '')
                            flags = {'Russia': '🇷🇺', 'Finland': '🇫🇮', 'Germany': '🇩🇪'}
                            flag = flags.get(country, '🌍')
                            message += f"🌍 <b>Страна:</b> {flag} {country}\n"
                            if isp:
                                message += f"📡 <b>Оператор:</b> {isp}\n"
                    except:
                        pass
        except:
            pass
        
        # Telegram ID
        tg_id = ''
        try:
            import json
            settings = inbound.get('settings', {})
            if isinstance(settings, str):
                settings = json.loads(settings) if settings.strip() else {}
            if isinstance(settings, dict):
                for sc in settings.get('clients', []):
                    if sc.get('email') == email:
                        tg_id = str(sc.get('tgId', ''))
                        break
        except:
            pass
        
        if tg_id and tg_id != '0' and tg_id != '':
            message += f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n"
        else:
            message += f"🆔 <b>Telegram ID:</b> ❌ Не привязан\n"
        
        # Кнопка Назад
        keyboard = [[InlineKeyboardButton("⬅️ К списку", callback_data=f"inbound_select_{inbound['id']}")]]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=HTML
        )
    else:
        await query.edit_message_text("❌ Клиент не найден", parse_mode=HTML)

async def all_clients_old(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔄 <b>Получаю список инбаундов...</b>", parse_mode=HTML)
    
    def get_inbounds_data():
        return get_inbounds_list()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_inbounds_data)
        inbounds_list = future.result()
    
    if inbounds_list:
        context.user_data['inbounds_list'] = inbounds_list
        context.user_data['state'] = BotState.ALL_CLIENTS_MENU
        
        keyboard = create_inbounds_keyboard(inbounds_list)
        
        message = f"📡 <b>Доступные инбаунды:</b> {len(inbounds_list)}\n\n"
        message += "👥 <b>Выберите инбаунд для просмотра клиентов:</b>"
        
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)
    else:
        await update.message.reply_text(
            "❌ <b>Не удалось получить список инбаундов или инбаунды отсутствуют</b>\n\n"
            "🔧 <b>Возможные причины:</b>\n"
            "• Проблемы с подключением к панели\n"
            "• Неправильные учетные данные\n"
            "• На панели нет созданных инбаундов",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        context.user_data['state'] = BotState.MAIN_MENU
async def clients_list(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    inbound_name = update.message.text
    
    if inbound_name == "⬅️ Назад в меню":
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "🏠 <b>Главное меню:</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return
    
    inbounds_list = context.user_data.get('inbounds_list', [])
    selected_inbound = None
    
    for inbound in inbounds_list:
        remark = inbound.get('remark', '')
        if remark == inbound_name:
            selected_inbound = inbound
            break
    
    if selected_inbound:
        clients = selected_inbound.get('clientStats', [])
        if not clients:
            await update.message.reply_text("❌ <b>В этом инбаунде нет клиентов</b>", parse_mode=HTML)
            return
        
        context.user_data['selected_inbound'] = selected_inbound
        context.user_data['selected_inbound_name'] = inbound_name
        context.user_data['clients'] = clients
        context.user_data['state'] = BotState.CLIENTS_MENU
        
        keyboard = create_clients_keyboard(clients)
        
        message = f"👥 <b>Клиенты инбаунда:</b> {inbound_name}\n\n"
        message += f"📊 <b>Всего клиентов:</b> {len(clients)}\n\n"
        message += "🔍 <b>Выберите клиента для просмотра деталей:</b>"
        
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)
    else:
        await update.message.reply_text("❌ <b>Инбаунд не найден</b>", parse_mode=HTML)
async def client_detail(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    message_text = update.message.text
    
    # Проверяем, не ожидается ли подтверждение удаления
    if context.user_data.get('awaiting_delete_confirmation'):
        await handle_delete_confirmation(update, context)
        return
    
    action_buttons = ["🔄 Обновить клиента", "🗑️ Удалить клиента", "📊 Сбросить трафик", "🌍 IP адреса", "🆔 Привязать TG", "⬅️ Назад к клиентам"]
    if message_text in action_buttons:
        return
    
    selected_client = context.user_data.get('selected_client')
    
    if not selected_client or (message_text not in action_buttons and message_text != context.user_data.get('last_client_email')):
        clients = context.user_data.get('clients', [])
        selected_client = None
        
        for client in clients:
            email = client.get('email', '')
            if email == message_text:
                selected_client = client
                context.user_data['selected_client'] = client
                context.user_data['last_client_email'] = email
                break
        
        if not selected_client:
            await update.message.reply_text("❌ <b>Клиент не найден</b>", parse_mode=HTML)
            return
    
    context.user_data['state'] = BotState.CLIENT_DETAIL_MENU
    
    selected_inbound = context.user_data.get('selected_inbound', {})
    client_email = selected_client.get('email', '')
    
    # Получаем полные данные клиента из настроек инбаунда
    full_client_info = None
    settings = selected_inbound.get('settings', {})
    
    if isinstance(settings, str):
        try:
            if settings.strip():
                settings = json.loads(settings)
            else:
                settings = {}
        except json.JSONDecodeError:
            settings = {}
    
    if isinstance(settings, dict):
        clients_settings = settings.get('clients', [])
        for client_setting in clients_settings:
            if isinstance(client_setting, dict) and client_setting.get('email') == client_email:
                full_client_info = client_setting
                break
    
    # Получаем онлайн-статус через API панели (более точный)
    current_up = selected_client.get('up', 0)
    current_down = selected_client.get('down', 0)
    
    # Используем API для получения точного онлайн-статуса
    def get_online_status():
        try:
            online_clients = get_online_clients()
            last_online_map = get_last_online()
            is_online = client_email in online_clients
            last_ts = last_online_map.get(client_email, 0)
            return is_online, last_ts
        except:
            # Fallback на старый метод
            from xui_api import get_client_connection_status
            return get_client_connection_status(client_email, current_up, current_down), 0
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_online_status)
        is_online, last_online_ts = future.result()
    
    connection_status = "🟢 Онлайн" if is_online else "🔴 Офлайн"
    
    # Обновляем кэш
    from xui_api import update_traffic_history
    update_traffic_history(client_email, current_up, current_down)
    last_seen = get_client_last_seen(client_email)
    
    # Форматируем информацию о клиенте
    message = "👤 <b>Детальная информация о клиенте</b>\n\n"
    message += f"📧 <b>Email:</b> {selected_client.get('email', 'N/A')}\n"
    message += f"🆔 <b>ID:</b> {selected_client.get('id', 'N/A')}\n"
    message += f"📶 <b>Статус соединения:</b> {connection_status}\n"
    message += f"👀 <b>Последняя активность:</b> {last_seen}\n"
    message += f"💾 <b>Трафик:</b> ↑{format_traffic(selected_client.get('up', 0))} ↓{format_traffic(selected_client.get('down', 0))}\n"
    message += f"📊 <b>Всего трафика:</b> {format_traffic(selected_client.get('up', 0) + selected_client.get('down', 0))}\n"
    message += f"🔒 <b>Статус:</b> {'🟢 Активен' if selected_client.get('enable', True) else '🔴 Отключен'}\n"
    
    if full_client_info:
        uuid = full_client_info.get('id', 'Не указан')
        sub_id = full_client_info.get('subId', 'Отсутствует')
        
        message += f"🔑 <b>UUID:</b> <code>{uuid}</code>\n"
        message += f"📋 <b>Sub ID:</b> <code>{sub_id}</code>\n"
        
        if sub_id and sub_id != 'Отсутствует':
            subscription_link = f"{SUBSCRIPTION_URL}/sub/{SUBSCRIPTION_EXTRA_PATH}/{sub_id}"
            message += f"\n🔗 <b>Ссылка для подписки:</b>\n\n"
            message += f"<code>{subscription_link}</code>\n\n"
            message += f"<i>Нажмите на ссылку, чтобы скопировать</i>"
    
    # Прямые ссылки подключения
    if full_client_info:
        try:
            from xui_api import get_client_url
            inbound_id = selected_inbound.get('id')
            if inbound_id:
                urls = get_client_url(inbound_id, client_email)
                if urls:
                    message += f"\n\n🔗 <b>Прямые ссылки подключения:</b>\n"
                    for url in urls[:2]:
                        short_url = url[:120] + "..." if len(url) > 120 else url
                        message += f"<code>{short_url}</code>\n\n"
                    message += "<i>Скопируйте ссылку и вставьте в приложение</i>"
        except Exception as e:
            logger.error(f"Ошибка получения прямых ссылок: {e}")
    
    # Добавляем прямые ссылки подключения
    if full_client_info and sub_id and sub_id != 'Отсутствует':
        try:
            from xui_api import get_client_url
            inbound_id = selected_inbound.get('id')
            if inbound_id:
                urls = get_client_url(inbound_id, client_email)
                if urls:
                    message += f"\n\n🔗 <b>Прямые ссылки подключения:</b>\n"
                    for url in urls[:3]:  # Максимум 3 ссылки
                        # Обрезаем для отображения
                        short_url = url[:100] + "..." if len(url) > 100 else url
                        message += f"<code>{short_url}</code>\n"
        except Exception as e:
            logger.error(f"Ошибка получения прямых ссылок: {e}")
    else:
        message += f"🔑 <b>UUID:</b> Не удалось получить\n"
        message += f"📋 <b>Sub ID:</b> Не удалось получить\n"
    
    # Добавляем время последней активности из X-UI
    last_seen_xui = selected_client.get('last_seen', 0)
    if last_seen_xui > 0:
        try:
            last_seen_timestamp = last_seen_xui / 1000
            last_seen_date = datetime.fromtimestamp(last_seen_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            now_timestamp = datetime.now().timestamp()
            hours_ago = (now_timestamp - last_seen_timestamp) / (60 * 60)
            
            if hours_ago < 1:
                minutes_ago = hours_ago * 60
                message += f"🕒 <b>Был(а) в сети (X-UI):</b> {last_seen_date} (~{int(minutes_ago)} мин. назад)\n"
            elif hours_ago < 24:
                message += f"🕒 <b>Был(а) в сети (X-UI):</b> {last_seen_date} (~{int(hours_ago)} ч. назад)\n"
            else:
                days_ago = hours_ago / 24
                message += f"🕒 <b>Был(а) в сети (X-UI):</b> {last_seen_date} (~{int(days_ago)} дн. назад)\n"
        except:
            message += f"🕒 <b>Был(а) в сети (X-UI):</b> Ошибка обработки\n"
    
    # Лимиты
    total_limit = selected_client.get('total', 0)
    if total_limit > 0:
        message += f"📈 <b>Лимит трафика:</b> {format_traffic(total_limit)}\n"
        used = selected_client.get('up', 0) + selected_client.get('down', 0)
        used_percent = (used / total_limit) * 100 if total_limit > 0 else 0
        message += f"📊 <b>Использовано:</b> {used_percent:.1f}%\n"
    else:
        message += f"📈 <b>Лимит трафика:</b> ♾️ Безлимит\n"
    
    # Срок действия
    expiry_time = 0
    if full_client_info:
        expiry_time = full_client_info.get('expiryTime', 0)
        if expiry_time == 0:
            expiry_time = selected_client.get('expiryTime', 0)
    else:
        expiry_time = selected_client.get('expiryTime', 0)
    
    if expiry_time > 0:
        try:
            expiry_timestamp = expiry_time / 1000
            expiry_date = datetime.fromtimestamp(expiry_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            now_timestamp = datetime.now().timestamp()
            days_left = (expiry_timestamp - now_timestamp) / (24 * 60 * 60)
            
            if days_left > 0:
                message += f"⏰ <b>Срок действия:</b> {expiry_date}\n"
                message += f"📅 <b>Осталось дней:</b> {int(days_left)}\n"
            else:
                message += f"⏰ <b>Срок действия:</b> ❌ Истек ({expiry_date})\n"
        except:
            message += f"⏰ <b>Срок действия:</b> Ошибка обработки\n"
    else:
        message += f"⏰ <b>Срок действия:</b> ♾️ Бессрочно\n"
    
    if full_client_info and full_client_info.get('flow'):
        message += f"🌊 <b>Flow:</b> {full_client_info.get('flow')}\n"
    

    
    # Определяем страну по IP
    try:
        from xui_api import get_client_ips
        ips = get_client_ips(client_email)
        if ips and isinstance(ips, list) and len(ips) > 0:
            last_ip = str(ips[0]).split(' ')[0].strip()
            if last_ip and last_ip != 'N':
                country, isp = get_ip_info(last_ip)
                message += f"🌍 <b>Страна:</b> {country}\n"
                if isp:
                    message += f"📡 <b>Оператор:</b> {isp}\n"
    except:
        pass
    
    # Статус клиента
    total_traffic = selected_client.get('up', 0) + selected_client.get('down', 0)
    limit = selected_client.get('total', 0)
    
    if total_traffic > 100 * 1024 * 1024 * 1024:  # > 100 GB
        status = "💎 VIP"
    elif total_traffic > 10 * 1024 * 1024 * 1024:  # > 10 GB
        status = "⭐ Активный"
    elif total_traffic > 0:
        status = "🆕 Новый"
    else:
        status = "💤 Неактивный"
    
    # Если есть лимит и использовано > 80%
    if limit > 0 and total_traffic > 0:
        pct = total_traffic / limit * 100
        if pct > 90:
            status = "🔴 Критический"
        elif pct > 80:
            status = "🟡 Внимание"
    
    message += f"🏷️ <b>Статус:</b> {status}\n"
    
    # Информация о привязке Telegram
    tg_id = full_client_info.get('tgId', '') if full_client_info else ''
    if tg_id and str(tg_id) != '0' and str(tg_id) != '':
        message += f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n"
        

    else:
        message += f"🆔 <b>Telegram ID:</b> ❌ Не привязан\n"

        message += f"<i>Нажмите '🆔 Привязать TG' чтобы привязать</i>\n"
    
    # Определение устройства по имени клиента
    email_lower = client_email.lower()
    
    device_info = ""
    
    # Проверяем ключевые слова в email
    if 'mobile' in email_lower or 'мобайл' in email_lower or 'phone' in email_lower:
        device_info = "📱 <b>Устройство:</b> Телефон (Mobile)"
    elif 'ноут' in email_lower or 'laptop' in email_lower or 'notebook' in email_lower or 'пк' in email_lower or 'pc' in email_lower:
        device_info = "💻 <b>Устройство:</b> Компьютер (PC/Laptop)"
    elif 'tv' in email_lower or 'телек' in email_lower or 'телевизор' in email_lower or 'smarttv' in email_lower:
        device_info = "📺 <b>Устройство:</b> Телевизор (Smart TV)"
    elif 'tablet' in email_lower or 'планшет' in email_lower or 'ipad' in email_lower:
        device_info = "📱 <b>Устройство:</b> Планшет (Tablet)"
    elif 'iphone' in email_lower or 'ios' in email_lower:
        device_info = "🍎 <b>Устройство:</b> iPhone"
    elif 'ipad' in email_lower:
        device_info = "🍎 <b>Устройство:</b> iPad"
    elif 'mac' in email_lower or 'macbook' in email_lower:
        device_info = "🍎 <b>Устройство:</b> Mac/MacBook"
    elif 'android' in email_lower:
        device_info = "🤖 <b>Устройство:</b> Android"
    elif any(w in email_lower for w in ['samsung', 'galaxy']):
        device_info = "🤖 <b>Устройство:</b> Samsung Galaxy"
    elif 'xiaomi' in email_lower or 'poco' in email_lower or 'redmi' in email_lower:
        device_info = "🤖 <b>Устройство:</b> Xiaomi"
    elif 'huawei' in email_lower or 'honor' in email_lower:
        device_info = "🤖 <b>Устройство:</b> Huawei/Honor"
    elif 'windows' in email_lower or 'win' in email_lower:
        device_info = "💻 <b>Устройство:</b> Windows"
    elif 'linux' in email_lower or 'ubuntu' in email_lower:
        device_info = "🐧 <b>Устройство:</b> Linux"
    
    # Если не определили по email — проверяем имя из базы
    if not device_info:
        try:
            db_client = db.get_client_by_login(client_email)
            if db_client:
                name_lower = db_client['name'].lower()
                if any(w in name_lower for w in ['андроид', 'android', 'телефон', 'мобильный']):
                    device_info = "🤖 <b>Устройство:</b> Android"
                elif any(w in name_lower for w in ['айфон', 'iphone', 'яблоко']):
                    device_info = "🍎 <b>Устройство:</b> iPhone"
                elif any(w in name_lower for w in ['комп', 'ноут', 'пк', 'компьютер']):
                    device_info = "💻 <b>Устройство:</b> Компьютер"
                elif any(w in name_lower for w in ['планшет', 'ipad']):
                    device_info = "📱 <b>Устройство:</b> Планшет"
                elif any(w in name_lower for w in ['телек', 'телевизор', 'tv']):
                    device_info = "📺 <b>Устройство:</b> Телевизор"
        except:
            pass
    
    if device_info:
        message += device_info + "\n"
    
    keyboard = create_client_detail_keyboard()
    await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)
async def handle_delete_confirmation(update: Update, context: CallbackContext) -> None:
    """Обрабатывает подтверждение/отмену удаления клиента"""
    message_text = update.message.text
    
    if message_text == "✅ Подтвердить":
        # Выполняем удаление
        selected_client = context.user_data.get('selected_client')
        selected_inbound = context.user_data.get('selected_inbound')
        
        if not selected_client or not selected_inbound:
            await update.message.reply_text("❌ <b>Данные клиента утеряны</b>", parse_mode=HTML)
            context.user_data.pop('awaiting_delete_confirmation', None)
            return
        
        client_email = selected_client.get('email', '')
        inbound_id = selected_inbound.get('id')
        
        await update.message.reply_text("🗑️ <b>Удаляю клиента...</b>", parse_mode=HTML)
        
        def do_delete():
            return delete_client_by_email(inbound_id, client_email)
        
        with ThreadPoolExecutor() as executor:
            future = executor.submit(do_delete)
            success = future.result()
        
        context.user_data.pop('awaiting_delete_confirmation', None)
        
        if success:
            await update.message.reply_text(
                f"✅ <b>Клиент успешно удалён!</b>\n\n"
                f"📧 <b>Email:</b> {client_email}\n"
                f"📡 <b>Инбаунд ID:</b> {inbound_id}",
                parse_mode=HTML
            )
            await back_to_clients(update, context)
        else:
            await update.message.reply_text(
                f"❌ <b>Не удалось удалить клиента</b>\n\n"
                f"📧 <b>Email:</b> {client_email}\n\n"
                f"<b>Возможные причины:</b>\n"
                f"• Клиент уже был удалён\n"
                f"• Ошибка связи с панелью\n"
                f"• Недостаточно прав",
                parse_mode=HTML
            )
    
    elif message_text == "❌ Отменить":
        context.user_data.pop('awaiting_delete_confirmation', None)
        await update.message.reply_text("❌ <b>Удаление отменено</b>", parse_mode=HTML)
        await client_detail(update, context)
    
    else:
        # Любая другая кнопка - отмена удаления
        context.user_data.pop('awaiting_delete_confirmation', None)
        await update.message.reply_text("❌ <b>Удаление отменено</b>", parse_mode=HTML)
async def refresh_client_status(update: Update, context: CallbackContext) -> None:
    """Принудительно обновляет статус клиента через API"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_client = context.user_data.get('selected_client')
    
    if not selected_client:
        await update.message.reply_text("❌ <b>Клиент не выбран</b>", parse_mode=HTML)
        return
    
    client_email = selected_client.get('email', '')
    selected_inbound_name = context.user_data.get('selected_inbound_name')
    
    if not client_email or not selected_inbound_name:
        await update.message.reply_text("❌ <b>Недостаточно данных для обновления</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔄 <b>Обновляю данные клиента...</b>", parse_mode=HTML)
    
    def get_updated_inbounds():
        return get_inbounds_list()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_updated_inbounds)
        inbounds_list = future.result()
    
    if not inbounds_list:
        await update.message.reply_text("❌ <b>Не удалось получить данные инбаундов</b>", parse_mode=HTML)
        return
    
    updated_client = None
    updated_inbound = None
    
    for inbound in inbounds_list:
        remark = inbound.get('remark', '')
        if remark == selected_inbound_name:
            updated_inbound = inbound
            clients = inbound.get('clientStats', [])
            for client in clients:
                if client.get('email') == client_email:
                    updated_client = client
                    break
            break
    
    if updated_client and updated_inbound:
        context.user_data['selected_client'] = updated_client
        context.user_data['selected_inbound'] = updated_inbound
        context.user_data['clients'] = updated_inbound.get('clientStats', [])
        
        await update.message.reply_text("✅ <b>Статус клиента обновлён</b>", parse_mode=HTML)
        
        current_up = updated_client.get('up', 0)
        current_down = updated_client.get('down', 0)
        from xui_api import update_traffic_history
        update_traffic_history(client_email, current_up, current_down)
        
        await client_detail(update, context)
    else:
        await update.message.reply_text(
            "❌ <b>Не удалось обновить статус клиента</b>\n\n"
            f"• Клиент: {client_email}\n"
            f"• Инбаунд: {selected_inbound_name}\n\n"
            "Возможно, клиент был удален или произошла ошибка при получении данных.",
            parse_mode=HTML
        )
# ==================== АДМИНСКИЕ ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ КЛИЕНТАМИ ====================

async def delete_client(update: Update, context: CallbackContext) -> None:
    """Реальное удаление клиента через API панели"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_client = context.user_data.get('selected_client')
    selected_inbound = context.user_data.get('selected_inbound')
    
    if not selected_client or not selected_inbound:
        await update.message.reply_text("❌ <b>Клиент не выбран или данные утеряны</b>", parse_mode=HTML)
        return
    
    client_email = selected_client.get('email', '')
    inbound_id = selected_inbound.get('id')
    
    if not client_email or not inbound_id:
        await update.message.reply_text("❌ <b>Недостаточно данных для удаления</b>", parse_mode=HTML)
        return
    
    # Запрашиваем подтверждение
    context.user_data['awaiting_delete_confirmation'] = True
    
    message = (
        f"🗑️ <b>Подтверждение удаления</b>\n\n"
        f"Вы действительно хотите удалить клиента?\n\n"
        f"📧 <b>Email:</b> {client_email}\n"
        f"📡 <b>Инбаунд ID:</b> {inbound_id}\n\n"
        f"<b>⚠️ Это действие нельзя отменить!</b>\n\n"
        f"Нажмите <b>✅ Подтвердить</b> для удаления или <b>❌ Отменить</b> для отмены."
    )
    
    await update.message.reply_text(
        message,
        reply_markup=create_delete_confirmation_keyboard(),
        parse_mode=HTML
    )
async def reset_client_traffic(update: Update, context: CallbackContext) -> None:
    """Реальный сброс трафика клиента через API панели"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_client = context.user_data.get('selected_client')
    selected_inbound = context.user_data.get('selected_inbound')
    
    if not selected_client or not selected_inbound:
        await update.message.reply_text("❌ <b>Клиент не выбран или данные утеряны</b>", parse_mode=HTML)
        return
    
    client_email = selected_client.get('email', '')
    inbound_id = selected_inbound.get('id')
    
    if not client_email or not inbound_id:
        await update.message.reply_text("❌ <b>Недостаточно данных для сброса трафика</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("📊 <b>Сбрасываю трафик клиента...</b>", parse_mode=HTML)
    
    def do_reset():
        return reset_client_traffic(inbound_id, client_email)
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(do_reset)
        success = future.result()
    
    if success:
        # Очищаем кэш трафика
        try:
            from traffic_cache import client_traffic_history
            if client_traffic_history:
                client_traffic_history.remove(client_email)
        except:
            pass
        
        await update.message.reply_text(
            f"✅ <b>Трафик клиента успешно сброшен!</b>\n\n"
            f"📧 <b>Email:</b> {client_email}\n"
            f"📡 <b>Инбаунд ID:</b> {inbound_id}\n\n"
            f"<i>Обновите данные клиента для просмотра актуальной статистики</i>",
            parse_mode=HTML
        )
        
        await refresh_client_status(update, context)
    else:
        await update.message.reply_text(
            f"❌ <b>Не удалось сбросить трафик клиента</b>\n\n"
            f"📧 <b>Email:</b> {client_email}\n\n"
            f"<b>Возможные причины:</b>\n"
            f"• Клиент не найден\n"
            f"• Ошибка связи с панелью",
            parse_mode=HTML
        )



def get_zodiac(day, month):
    """Определяет знак зодиака по дню и месяцу"""
    if (month == 3 and day >= 21) or (month == 4 and day <= 19):
        return "♈ Овен"
    elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
        return "♉ Телец"
    elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
        return "♊ Близнецы"
    elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
        return "♋ Рак"
    elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
        return "♌ Лев"
    elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
        return "♍ Дева"
    elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
        return "♎ Весы"
    elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
        return "♏ Скорпион"
    elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
        return "♐ Стрелец"
    elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
        return "♑ Козерог"
    elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
        return "♒ Водолей"
    elif (month == 2 and day >= 19) or (month == 3 and day <= 20):
        return "♓ Рыбы"
    return ""

def get_ip_info(ip):
    """Определяет страну и провайдера по IP"""
    try:
        import requests
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode,isp,org", timeout=3)
        if r.status_code == 200:
            data = r.json()
            code = data.get('countryCode', '')
            isp = data.get('isp', '') or data.get('org', '')
            
            flags = {
                'RU': '🇷🇺 Россия', 'FI': '🇫🇮 Финляндия', 'DE': '🇩🇪 Германия',
                'US': '🇺🇸 США', 'GB': '🇬🇧 Англия', 'FR': '🇫🇷 Франция',
                'IT': '🇮🇹 Италия', 'ES': '🇪🇸 Испания', 'CN': '🇨🇳 Китай',
                'JP': '🇯🇵 Япония', 'KR': '🇰🇷 Корея', 'IN': '🇮🇳 Индия',
                'BR': '🇧🇷 Бразилия', 'CA': '🇨🇦 Канада', 'AU': '🇦🇺 Австралия',
                'KZ': '🇰🇿 Казахстан', 'BY': '🇧🇾 Беларусь', 'UA': '🇺🇦 Украина',
                'TR': '🇹🇷 Турция', 'NL': '🇳🇱 Нидерланды', 'SE': '🇸🇪 Швеция',
                'NO': '🇳🇴 Норвегия', 'PL': '🇵🇱 Польша', 'CZ': '🇨🇿 Чехия',
            }
            country = flags.get(code, f'🌍 {code}')
            return country, isp
    except:
        pass
    return '🌍 Неизвестно', ''

def get_country_by_ip(ip):
    """Определяет страну по IP (для совместимости)"""
    country, _ = get_ip_info(ip)
    return country

async def show_client_ips(update: Update, context: CallbackContext) -> None:
    """Показывает IP адреса клиента"""
    if not is_admin(update.effective_user.id):
        return
    
    selected_client = context.user_data.get('selected_client')
    if not selected_client:
        await update.message.reply_text("❌ <b>Клиент не выбран</b>", parse_mode=HTML)
        return
    
    email = selected_client.get('email', '')
    
    await update.message.reply_text("🌍 <b>Получаю IP адреса...</b>", parse_mode=HTML)
    
    def get_ips():
        from xui_api import get_client_ips
        result = get_client_ips(email)
        # get_client_ips возвращает список строк вида "ip (timestamp)"
        return result if isinstance(result, list) else []
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_ips)
        ips = future.result()
    
    if ips and len(ips) > 0:
        message = f"🌍 <b>IP адреса клиента</b>\n\n"
        message += f"📧 <b>Email:</b> {email}\n\n"
        message += "<b>Последние подключения:</b>\n"
        
        count = 0
        for item in ips:
            if count >= 20:
                break
            item_str = str(item).strip()
            if not item_str or item_str in ['N', 'o', 'I', 'P', 'R', 'e', 'c', 'd']:
                continue
            # Форматируем дату красиво (панель хранит UTC, вычитаем 3 часа для MSK)
            import re as re2
            time_match = re2.search(r'\((.*?)\)', item_str)
            if time_match:
                try:
                    from datetime import datetime, timedelta
                    dt = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
                    # Панель отдаёт UTC, переводим в MSK (-3 часа)
                    dt = dt - timedelta(hours=3)
                    months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                             'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
                    formatted = f"{dt.day} {months[dt.month-1]} {dt.year} {dt.strftime('%H:%M')}"
                    item_str = item_str.replace(time_match.group(1), formatted)
                except:
                    pass
            if item_str and item_str != 'N' and item_str != 'o':
                # Добавляем флаг страны
                ip_match = re2.search(r'([\d.]+)', item_str)
                if ip_match:
                    ip = ip_match.group(1)
                    country, isp = get_ip_info(ip)
                    # Форматируем: страна, IP с датой, оператор
                    time_part = time_match.group(0) if time_match else ''
                    message += f"  {country}\n"
                    message += f"  <code>{ip}</code> {time_part}\n"
                    if isp:
                        message += f"  📡 {isp}\n\n"
                    continue  # Пропускаем обычный вывод
                
                count += 1
        
        total = len([i for i in ips if str(i).strip()])
        if total > 20:
            message += f"\n<i>... и ещё {total - 20}</i>"
        
        message += f"\n\n💡 <i>Всего записей: {total}</i>"
        
        await update.message.reply_text(message, parse_mode=HTML)
    else:
        await update.message.reply_text(
            f"🌍 <b>Нет данных о IP адресах</b>\n\n"
            f"📧 {email}\n\n"
            f"<i>Клиент ещё не подключался или данные очищены</i>",
            parse_mode=HTML
        )


async def bind_telegram_id(update: Update, context: CallbackContext) -> None:
    """Привязывает Telegram ID к клиенту в панели"""
    if not is_admin(update.effective_user.id):
        return
    
    selected_client = context.user_data.get('selected_client')
    selected_inbound = context.user_data.get('selected_inbound')
    
    if not selected_client or not selected_inbound:
        await update.message.reply_text("❌ <b>Клиент не выбран</b>", parse_mode=HTML)
        return
    
    email = selected_client.get('email', '')
    inbound_id = selected_inbound.get('id')
    
    # Запрашиваем Telegram ID
    context.user_data['awaiting_tg_id'] = True
    context.user_data['state'] = BotState.BIND_TG_ID
    context.user_data['bind_email'] = email
    context.user_data['bind_inbound_id'] = inbound_id
    
    # Ищем Telegram ID в базе
    db_tg_id = None
    try:
        db_client = db.get_client_by_login(email)
        if db_client:
            db_tg_id = db_client['telegram_id']
    except:
        pass
    
    message = f"🆔 <b>Привязка Telegram ID</b>\n\n"
    message += f"📧 <b>Клиент:</b> {email}\n"
    message += f"📡 <b>Инбаунд ID:</b> {inbound_id}\n"
    
    if db_tg_id:
        message += f"🆔 <b>Telegram ID из базы:</b> <code>{db_tg_id}</code>\n"
        message += f"<i>Скопируйте ID выше и вставьте ниже</i>\n\n"
    else:
        message += f"🆔 <b>Telegram ID:</b> ❌ Не найден в базе\n\n"
    
    message += "<b>Введите Telegram ID пользователя:</b>"
    
    await update.message.reply_text(
        message,
        reply_markup=create_cancel_keyboard(),
        parse_mode=HTML
    )

async def handle_tg_id_input(update: Update, context: CallbackContext) -> None:
    """Обрабатывает ввод Telegram ID"""
    if not context.user_data.get('awaiting_tg_id'):
        return
    
    message_text = update.message.text
    
    if message_text == "❌ Отменить":
        context.user_data.pop('awaiting_tg_id', None)
        await update.message.reply_text("❌ <b>Привязка отменена</b>", parse_mode=HTML)
        return
    
    # Проверяем что ввели число
    try:
        tg_id = int(message_text.strip())
    except:
        await update.message.reply_text(
            "❌ <b>Неверный формат.</b>\nВведите числовой Telegram ID.",
            parse_mode=HTML
        )
        return
    
    email = context.user_data.get('bind_email')
    inbound_id = context.user_data.get('bind_inbound_id')
    
    if not email or not inbound_id:
        await update.message.reply_text("❌ <b>Данные утеряны</b>", parse_mode=HTML)
        context.user_data.pop('awaiting_tg_id', None)
        return
    
    await update.message.reply_text("🔄 <b>Привязываю Telegram ID...</b>", parse_mode=HTML)
    
    # Обновляем клиента через API
    def do_bind():
        try:
            from xui_api import get_inbound_by_id
            import requests, json
            
            # Получаем текущий инбаунд
            inbound = get_inbound_by_id(inbound_id)
            if not inbound:
                return False, "Инбаунд не найден"
            
            settings = inbound.get('settings', {})
            if isinstance(settings, str):
                settings = json.loads(settings) if settings.strip() else {}
            
            # Находим и обновляем клиента
            clients = settings.get('clients', [])
            found = False
            for c in clients:
                if c.get('email') == email:
                    c['tgId'] = str(tg_id)
                    found = True
                    break
            
            if not found:
                return False, "Клиент не найден в настройках"
            
            # Отправляем обновление
            from xui_api import session, _get_headers, get_current_panel_url
            url = f"{get_current_panel_url().rstrip('/')}/panel/api/inbounds/update/{inbound_id}"
            
            # Обновляем settings в inbound
            inbound['settings'] = json.dumps(settings)
            
            r = session.post(url, json=inbound, headers=_get_headers(), timeout=15)
            if r.status_code == 200:
                return True, "OK"
            else:
                return False, f"Ошибка API: {r.status_code}"
        except Exception as e:
            return False, str(e)
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(do_bind)
        success, msg = future.result()
    
    context.user_data.pop('awaiting_tg_id', None)
    
    if success:
        await update.message.reply_text(
            f"✅ <b>Telegram ID привязан!</b>\n\n"
            f"📧 <b>Клиент:</b> {email}\n"
            f"🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n\n"
            f"<i>Теперь пользователь с этим ID будет видеть эту подписку в 'Моя подписка'</i>",
            parse_mode=HTML
        )
    else:
        await update.message.reply_text(
            f"❌ <b>Ошибка привязки:</b> {msg}",
            parse_mode=HTML
        )

async def back_to_clients(update: Update, context: CallbackContext) -> None:
    """Возврат к списку клиентов текущего инбаунда"""
    context.user_data.pop('awaiting_delete_confirmation', None)  # Очищаем флаг подтверждения
    
    selected_inbound_name = context.user_data.get('selected_inbound_name')
    clients = context.user_data.get('clients', [])
    
    if selected_inbound_name and clients:
        context.user_data['state'] = BotState.CLIENTS_MENU
        
        keyboard = create_clients_keyboard(clients)
        
        message = f"👥 <b>Клиенты инбаунда:</b> {selected_inbound_name}\n\n"
        message += f"📊 <b>Всего клиентов:</b> {len(clients)}\n\n"
        message += "🔍 <b>Выберите клиента для просмотра деталей:</b>"
        
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)
    else:
        await all_clients(update, context)
# ==================== АДМИНСКИЕ ФУНКЦИИ ДЛЯ ОТПРАВКИ СООБЩЕНИЙ ====================

async def send_message(update: Update, context: CallbackContext) -> None:
    """Начинает процесс отправки сообщения пользователю (для админа)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔄 <b>Получаю список пользователей...</b>", parse_mode=HTML)
    
    def get_users_data():
        return db.get_all_clients()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_users_data)
        users = future.result()
    
    if users:
        context.user_data['users_for_message'] = users
        context.user_data['state'] = BotState.ADMIN_CHOOSE_USER
        
        keyboard = create_users_for_message_keyboard(users)
        
        message = "💌 <b>Отправить сообщение пользователю</b>\n\n"
        message += "👤 <b>Выберите пользователя:</b>"
        
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)
    else:
        await update.message.reply_text(
            "❌ <b>Нет зарегистрированных пользователей</b>\n\n"
            "В базе данных пока нет пользователей.",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        context.user_data['state'] = BotState.MAIN_MENU
async def admin_choose_user(update: Update, context: CallbackContext) -> None:
    """Обрабатывает выбор пользователя для отправки сообщения"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    message_text = update.message.text
    
    if message_text == "❌ Отменить":
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "❌ <b>Отправка сообщения отменена</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return
    
    users = context.user_data.get('users_for_message', [])
    selected_user = None
    
    for user in users:
        user_button = f"👤 {user['name']} ({user['login']})"
        if user_button == message_text:
            selected_user = user
            break
    
    if selected_user:
        context.user_data['selected_user_for_message'] = selected_user
        context.user_data['state'] = BotState.ADMIN_WRITE_MESSAGE
        
        message = "💌 <b>Отправка сообщения пользователю</b>\n\n"
        message += f"👤 <b>Получатель:</b> {selected_user['name']}\n"
        message += f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>\n"
        message += f"📞 <b>Телефон:</b> <code>{selected_user['phone']}</code>\n\n"
        message += "✏️ <b>Введите ваше сообщение:</b>\n\n"
        message += "<b>📸 Вы также можете отправить:</b>\n"
        message += "• Фото (с подписью)\n"
        message += "• Видео (с подписью)\n"
        message += "• Голосовое сообщение\n"
        message += "• Документы\n\n"
        message += "<i>Просто отправьте файл или наберите текст</i>"
        
        await update.message.reply_text(
            message,
            reply_markup=create_cancel_keyboard(),
            parse_mode=HTML
        )
    else:
        await update.message.reply_text("❌ <b>Пользователь не найден</b>", parse_mode=HTML)
async def admin_handle_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает сообщение от админа и отправляет пользователю"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_user = context.user_data.get('selected_user_for_message')
    
    if not selected_user:
        await update.message.reply_text("❌ <b>Ошибка: пользователь не выбран</b>", parse_mode=HTML)
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "🏠 <b>Главное меню:</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return
    
    if context.user_data.get('state') != BotState.ADMIN_WRITE_MESSAGE:
        return
    
    message_text = update.message.text
    
    if message_text == "❌ Отменить":
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "❌ <b>Отправка сообщения отменена</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return
    
    try:
        try:
            sticker_file_id = "CAACAgIAAxkBAAI1nWohorcFBAt5OO3MvgkJON3mDx3VAAJvAAPBnGAMyw59i8DdTVY7BA"
            await context.bot.send_sticker(
                selected_user['telegram_id'], 
                sticker=sticker_file_id
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить стикер пользователю {selected_user['telegram_id']}: {e}")
        
        await asyncio.sleep(0.5)
        
        from datetime import datetime
        now = datetime.now()
        months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                 'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
        date_str = f"{now.day} {months[now.month-1]} {now.year}"
        time_str = now.strftime('%H:%M')
        
        user_message = "💌 <b>Сообщение от администратора</b>\n\n"
        user_message += f"{message_text}\n\n"
        user_message += f"📅 {date_str} | 🕐 {time_str}"
        
        await context.bot.send_message(
            selected_user['telegram_id'], 
            user_message, 
            parse_mode=HTML
        )
        
        await send_notification_sound_to_user(context.bot, selected_user['telegram_id'])
        
        success_message = "✅ <b>Сообщение успешно отправлено!</b>\n\n"
        success_message += f"👤 <b>Пользователь:</b> {selected_user['name']}\n"
        success_message += f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>\n"
        success_message += f"🆔 <b>Telegram ID:</b> <code>{selected_user['telegram_id']}</code>\n\n"
        success_message += f"💬 <b>Ваше сообщение:</b>\n{message_text}"
        
        await update.message.reply_text(
            success_message,
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения пользователю {selected_user['telegram_id']}: {e}")
        error_message = "❌ <b>Не удалось отправить сообщение</b>\n\n"
        error_message += f"👤 <b>Пользователь:</b> {selected_user['name']}\n"
        error_message += f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>\n\n"
        error_message += "<b>Возможные причины:</b>\n"
        error_message += "• Пользователь заблокировал бота\n"
        error_message += "• Ошибка связи с Telegram\n"
        error_message += "• Пользователь удалил аккаунт"
        
        await update.message.reply_text(
            error_message,
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
    
    context.user_data['state'] = BotState.MAIN_MENU






async def admin_handle_media(update: Update, context: CallbackContext) -> None:
    """Универсальный обработчик медиа от админа"""
    if not is_admin(update.effective_user.id):
        return
    
    selected_user = context.user_data.get('selected_user_for_message')
    if not selected_user or context.user_data.get('state') != BotState.ADMIN_WRITE_MESSAGE:
        return
    
    caption = update.message.caption or ""
    
    try:
        # Стикер
        try:
            await context.bot.send_sticker(selected_user['telegram_id'], 
                "CAACAgIAAxkBAAI1nWohorcFBAt5OO3MvgkJON3mDx3VAAJvAAPBnGAMyw59i8DdTVY7BA")
        except: pass
        
        await asyncio.sleep(0.5)
        
        # Определяем тип и отправляем
        msg = update.message
        if msg.photo:
            await context.bot.send_photo(selected_user['telegram_id'], msg.photo[-1].file_id,
                caption=f"💌 <b>Сообщение от администратора</b>\n\n{caption}" if caption else "💌 <b>Сообщение от администратора</b>",
                parse_mode=HTML)
            media_type = "Фото"
        elif msg.video:
            await context.bot.send_video(selected_user['telegram_id'], msg.video.file_id,
                caption=f"💌 <b>Сообщение от администратора</b>\n\n{caption}" if caption else "💌 <b>Сообщение от администратора</b>",
                parse_mode=HTML)
            media_type = "Видео"
        elif msg.voice:
            await context.bot.send_message(selected_user['telegram_id'], "💌 <b>Голосовое сообщение от администратора</b>", parse_mode=HTML)
            await context.bot.send_voice(selected_user['telegram_id'], msg.voice.file_id)
            media_type = "Голосовое"
        elif msg.audio:
            await context.bot.send_message(selected_user['telegram_id'], 
                f"🎵 <b>Музыка от администратора</b>\n\n{caption}" if caption else "🎵 <b>Музыка от администратора</b>",
                parse_mode=HTML)
            await context.bot.send_audio(selected_user['telegram_id'], msg.audio.file_id,
                performer=msg.audio.performer or "Администратор",
                title=msg.audio.title or "Аудио")
            media_type = "Аудио"
        elif msg.document:
            await context.bot.send_document(selected_user['telegram_id'], msg.document.file_id,
                filename=msg.document.file_name,
                caption=f"💌 <b>Документ от администратора</b>\n\n{caption}" if caption else "💌 <b>Документ от администратора</b>",
                parse_mode=HTML)
            media_type = "Документ"
        else:
            return
        
        await update.message.reply_text(
            f"✅ <b>{media_type} успешно отправлено!</b>\n\n"
            f"👤 <b>Пользователь:</b> {selected_user['name']}\n"
            f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>",
            reply_markup=create_admin_keyboard(), parse_mode=HTML
        )
    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {e}")
        await update.message.reply_text(
            f"❌ <b>Не удалось отправить</b>\n\n<b>Причины:</b>\n• Пользователь заблокировал бота\n• Ошибка связи",
            reply_markup=create_admin_keyboard(), parse_mode=HTML
        )
    
    context.user_data['state'] = BotState.MAIN_MENU

async def send_notification_sound_to_user(bot, user_id):
    """Отправляет звуковой файл пользователю с автовоспроизведением"""
    try:
        sound_path = None
        possible_paths = [
            'notification.mp3',
            './notification.mp3',
            os.path.join(os.path.dirname(__file__), 'notification.mp3'),
            os.path.join(os.getcwd(), 'notification.mp3'),
            '/app/notification.mp3',
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                sound_path = path
                logger.info(f"✅ Найден звуковой файл уведомления: {path}")
                break
        
        if sound_path:
            with open(sound_path, 'rb') as audio_file:
                await bot.send_audio(
                    chat_id=user_id,
                    audio=InputFile(audio_file, filename="notification.mp3"),
                    caption="🔔 Прослушайте обязательно!",
                    duration=3,
                    performer="SLV-Админ",
                    title="Уведомление"
                )
            logger.info(f"✅ Звуковое уведомление отправлено пользователю {user_id}")
        else:
            logger.warning(f"❌ Звуковой файл уведомления не найден!")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке звукового уведомления пользователю {user_id}: {e}")
# ==================== ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ====================

async def get_telegram_id(update: Update, context: CallbackContext) -> None:
    """Показывает ID пользователя с inline-кнопкой"""
    user = update.effective_user
    
    keyboard = [[InlineKeyboardButton(f"📋 Скопировать ID: {user.id}", callback_data=f"copy_id_{user.id}")]]
    
    device_info = ""
    try:
        user_agent = update.effective_user.user_agent if hasattr(update.effective_user, 'user_agent') else None
        if user_agent:
            if 'Android' in user_agent: device_info = "📱 Android"
            elif 'iPhone' in user_agent: device_info = "🍎 iPhone"
            elif 'Windows' in user_agent: device_info = "💻 Windows"
            elif 'Mac' in user_agent: device_info = "💻 Mac"
            elif 'Linux' in user_agent: device_info = "💻 Linux"
            else: device_info = "📱 Неизвестно"
        else: device_info = "📱 Не определено"
    except: device_info = "📱 Не определено"
    
    message = "👤 <b>МОЙ ПРОФИЛЬ</b>\n\n"
    message += f"🆔 <code>{user.id}</code> | 📛 {user.first_name} {user.last_name or ''}"
    if user.username:
        message += f" | @{user.username}"
    message += f"\n{device_info}\n\n"
    message += f"💡 <i>Нажми на кнопку чтобы скопировать ID</i>"
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

async def commands(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    commands_text = """
📋 <b>Доступные команды:</b>

/start - Запуск бота
/status - Информация о подключении к панели
/id - Показать мой ID Telegram
/admin - Вернуться в админ-панель (из клиентского режима)
/client - Перейти в режим клиента
/cache - Статистика LRU-кэша
/clearcache - Очистить кэш трафика
"""
    await update.message.reply_text(commands_text, parse_mode=HTML)

async def users_list(update: Update, context: CallbackContext) -> None:
    """Показывает список зарегистрированных пользователей из базы данных"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔄 <b>Получаю список пользователей...</b>", parse_mode=HTML)
    
    def get_users_data():
        return db.get_all_clients()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_users_data)
        users = future.result()
    
    if users:
        context.user_data['users_list'] = users
        context.user_data['state'] = BotState.USERS_LIST_MENU
        
        keyboard = create_users_list_keyboard(users)
        
        message = "👤 <b>Зарегистрированные пользователи</b>\n\n"
        message += f"📊 <b>Всего пользователей:</b> {len(users)}\n\n"
        message += "🔍 <b>Выберите пользователя для управления:</b>"
        
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)
    else:
        await update.message.reply_text(
            "❌ <b>Нет зарегистрированных пользователей</b>\n\n"
            "В базе данных пока нет пользователей.",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        context.user_data['state'] = BotState.MAIN_MENU
async def user_detail(update: Update, context: CallbackContext) -> None:
    """Показывает детальную информацию о пользователе и действия"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    message_text = update.message.text
    
    action_buttons = ["✏️ Редактировать логин", "📞 Редактировать телефон", "👤 Редактировать имя", 
                     "🔒 Блокировать/Разблокировать", "🗑️ Удалить пользователя", "⬅️ Назад к списку"]
    if message_text in action_buttons:
        return
    
    users = context.user_data.get('users_list', [])
    selected_user = None
    
    for user in users:
        user_button = f"👤 {user['name']} ({user['login']})"
        if user_button == message_text:
            selected_user = user
            break
    
    if selected_user:
        context.user_data['selected_user'] = selected_user
        # Перезагружаем из базы чтобы получить свежие данные
        selected_user = db.get_client_by_id(selected_user['id'])
        context.user_data['state'] = BotState.USER_DETAIL_MENU
        
        registration_date = selected_user['registration_date']
        if not isinstance(registration_date, str):
            registration_date = registration_date.strftime('%Y-%m-%d %H:%M:%S')
        
        message = "👤 <b>Детальная информация о пользователе</b>\n\n"
        import sqlite3
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        message += f"🆔 <b>ID в базе:</b> {selected_user['id']}\n"
        message += f"👤 <b>Имя:</b> {selected_user['name']}\n"
        message += f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>\n"
        message += f"📞 <b>Телефон:</b> <code>{selected_user['phone']}</code>{get_operator(selected_user.get("phone", ""))}\n"
        message += f"🆔 <b>Telegram ID:</b> <code>{selected_user['telegram_id']}</code>\n"
        reg_date = selected_user['registration_date']
        if isinstance(reg_date, str):
            try:
                from datetime import datetime
                dt = datetime.strptime(reg_date, '%Y-%m-%d %H:%M:%S')
                months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                         'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
                reg_formatted = f"{dt.day} {months[dt.month-1]} {dt.year}"
                reg_time = dt.strftime('%H:%M')
                message += f"📅 <b>Дата:</b> {reg_formatted}\n"
                message += f"🕐 <b>Время:</b> {reg_time}\n"
            except:
                message += f"📅 <b>Дата регистрации:</b> {reg_date}\n"
        else:
            message += f"📅 <b>Дата регистрации:</b> {reg_date}\n"
        message += f"🔒 <b>Статус:</b> {'🟢 Активен' if selected_user['is_active'] else '🔴 Заблокирован'}\n"
        
        birthday = selected_user.get('birthday', '')
        if birthday:
            try:
                b_day, b_month, _ = birthday.split('.')
                zodiac = get_zodiac(int(b_day), int(b_month))
                message += f"📅 <b>Регистрация:</b> {dt.day} {months[dt.month-1]} {dt.year}\n" if 'dt' in dir() else ""
                message += f"🎂 <b>День рождения:</b> {birthday}\n"
                message += f"   {zodiac}\n"
            except:
                pass
        else:
            message += f"🎂 <b>День рождения:</b> не задан\n"
        city = selected_user.get('city', '')
        if city:
            message += f"🏙️ <b>Город:</b> {city}\n"
        
        hwid = selected_user.get('hwid', '')
        if hwid:
            message += f"📱 <b>HWID:</b> <code>{hwid}</code>\n"
        else:
            message += f"📱 <b>HWID:</b> не задан\n"
        
        keyboard = create_user_actions_keyboard()
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)
    else:
        await update.message.reply_text("❌ <b>Пользователь не найден</b>", parse_mode=HTML)



async def edit_user_city(update: Update, context: CallbackContext) -> None:
    """Редактирование города — простой ввод"""
    if not is_admin(update.effective_user.id):
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ Пользователь не выбран", parse_mode=HTML)
        return
    
    context.user_data['awaiting_city'] = True
    
    current = selected_user.get('city', '') or 'не задан'
    await update.message.reply_text(
        f"🏙️ <b>Город проживания</b>\n\n"
        f"Текущий: <code>{current}</code>\n\n"
        f"📝 <b>Введите название города:</b>",
        parse_mode=HTML
    )

async def edit_user_hwid(update: Update, context: CallbackContext) -> None:
    """Редактирование HWID"""
    if not is_admin(update.effective_user.id):
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ Пользователь не выбран", parse_mode=HTML)
        return
    
    context.user_data['awaiting_hwid'] = True
    context.user_data['state'] = BotState.USER_EDIT_HWID
    
    current = selected_user.get('hwid', '') or 'не задан'
    await update.message.reply_text(
        f"📱 <b>HWID устройства</b>\n\n"
        f"Текущий: <code>{current}</code>\n\n"
        f"📝 <b>Введите новый HWID:</b>\n"
        f"<i>Клиент может посмотреть HWID в приложении v2rayTun</i>",
        parse_mode=HTML
    )

async def edit_user_birthday(update: Update, context: CallbackContext) -> None:
    """Редактирование даты рождения — простой ввод"""
    if not is_admin(update.effective_user.id):
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ Пользователь не выбран", parse_mode=HTML)
        return
    
    # Сохраняем что ждём дату
    context.user_data['awaiting_birthday'] = True
    context.user_data['state'] = BotState.USER_EDIT_BIRTHDAY
    
    current = selected_user.get('birthday', '') or 'не задана'
    await update.message.reply_text(
        f"🎂 <b>Дата рождения</b>\n\n"
        f"Текущая: <code>{current}</code>\n\n"
        f"📝 <b>Введите дату в формате ДД.ММ.ГГГГ:</b>",
        parse_mode=HTML
    )

async def edit_user_login(update: Update, context: CallbackContext) -> None:
    """Начинает процесс редактирования логина пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ <b>Пользователь не выбран</b>", parse_mode=HTML)
        return
    
    context.user_data['state'] = BotState.USER_EDIT_LOGIN
    context.user_data['edit_field'] = 'login'
    
    await update.message.reply_text(
        f"✏️ <b>Редактирование логина</b>\n\n"
        f"Текущий логин: <code>{selected_user['login']}</code>\n\n"
        f"📝 <b>Введите новый логин:</b>",
        parse_mode=HTML,
        reply_markup=create_edit_confirmation_keyboard()
    )
async def edit_user_phone(update: Update, context: CallbackContext) -> None:
    """Начинает процесс редактирования телефона пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ <b>Пользователь не выбран</b>", parse_mode=HTML)
        return
    
    context.user_data['state'] = BotState.USER_EDIT_PHONE
    context.user_data['edit_field'] = 'phone'
    
    await update.message.reply_text(
        f"📞 <b>Редактирование телефона</b>\n\n"
        f"Текущий телефон: <code>{selected_user['phone']}</code>\n\n"
        f"📱 <b>Введите новый телефон:</b>",
        parse_mode=HTML,
        reply_markup=create_edit_confirmation_keyboard()
    )


async def edit_user_name(update: Update, context: CallbackContext) -> None:
    """Начинает процесс редактирования имени пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ <b>Пользователь не выбран</b>", parse_mode=HTML)
        return
    
    context.user_data['state'] = BotState.USER_EDIT_NAME
    context.user_data['edit_field'] = 'name'
    
    await update.message.reply_text(
        f"👤 <b>Редактирование имени</b>\n\n"
        f"Текущее имя: {selected_user['name']}\n\n"
        f"👤 <b>Введите новое имя:</b>",
        parse_mode=HTML,
        reply_markup=create_edit_confirmation_keyboard()
    )
async def toggle_user_active(update: Update, context: CallbackContext) -> None:
    """Блокирует/разблокирует пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ <b>Пользователь не выбран</b>", parse_mode=HTML)
        return
    
    def toggle_in_db():
        return db.toggle_client_active(selected_user['id'])
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(toggle_in_db)
        new_state = future.result()
    
    if new_state is not None:
        action = "разблокирован" if new_state else "заблокирован"
        await update.message.reply_text(
            f"✅ <b>Пользователь {action}</b>\n\n"
            f"👤 {selected_user['name']}\n"
            f"📝 {selected_user['login']}",
            parse_mode=HTML
        )
        selected_user['is_active'] = new_state
        await user_detail(update, context)
    else:
        await update.message.reply_text("❌ <b>Ошибка при изменении статуса пользователя</b>", parse_mode=HTML)
async def delete_user(update: Update, context: CallbackContext) -> None:
    """Начинает процесс удаления пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ <b>Пользователь не выбран</b>", parse_mode=HTML)
        return
    
    context.user_data['state'] = BotState.USER_CONFIRM_DELETE
    
    await update.message.reply_text(
        f"🗑️ <b>Подтверждение удаления</b>\n\n"
        f"Вы действительно хотите удалить пользователя?\n\n"
        f"👤 <b>Имя:</b> {selected_user['name']}\n"
        f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>\n"
        f"📞 <b>Телефон:</b> <code>{selected_user['phone']}</code>\n\n"
        f"<b>Это действие нельзя отменить!</b>",
        parse_mode=HTML,
        reply_markup=create_edit_confirmation_keyboard()
    )
async def confirm_user_delete(update: Update, context: CallbackContext) -> None:
    """Подтверждает удаление пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_user = context.user_data.get('selected_user')
    if not selected_user:
        await update.message.reply_text("❌ <b>Пользователь не выбран</b>", parse_mode=HTML)
        return
    
    def delete_from_db():
        return db.delete_client(selected_user['id'])
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(delete_from_db)
        success = future.result()
    
    if success:
        await update.message.reply_text(
            f"✅ <b>Пользователь удален</b>\n\n"
            f"👤 {selected_user['name']}\n"
            f"📝 {selected_user['login']}",
            parse_mode=HTML,
            reply_markup=create_admin_keyboard()
        )
        context.user_data['state'] = BotState.MAIN_MENU
        users_list = context.user_data.get('users_list', [])
        context.user_data['users_list'] = [u for u in users_list if u['id'] != selected_user['id']]
    else:
        await update.message.reply_text("❌ <b>Ошибка при удалении пользователя</b>", parse_mode=HTML)
async def back_to_users_list(update: Update, context: CallbackContext) -> None:
    """Возврат к списку пользователей"""
    await users_list(update, context)
async def handle_user_edit_input(update: Update, context: CallbackContext) -> None:
    """Обрабатывает ввод новых данных для редактирования пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    current_state = context.user_data.get('state')
    edit_field = context.user_data.get('edit_field')
    selected_user = context.user_data.get('selected_user')
    
    if not selected_user or not edit_field:
        await update.message.reply_text("❌ <b>Ошибка: данные редактирования не найдены</b>", parse_mode=HTML)
        return
    
    new_value = update.message.text.strip()
    
    if edit_field == 'login2' or edit_field == 'birthday' or edit_field == 'city':
        pass  # без валидации для второго логина
    elif edit_field == 'login2' or edit_field == 'birthday' or edit_field == 'city':
        pass
    elif edit_field == 'login':
        if len(new_value) < 2 or len(new_value) > 30:
            await update.message.reply_text(
                "❌ <b>Логин должен быть от 2 до 30 символов.</b>\n\n"
                "💫 Пожалуйста, введите логин еще раз:",
                parse_mode=HTML
            )
            return
    
    elif edit_field == 'phone':
        if not re.match(r'^(\+79\d{9}|\+9936\d{8})$', new_value):
            await update.message.reply_text(
                "❌ <b>Неверный формат номера телефона.</b>\n\n"
                "📱 <b>Пожалуйста, введите номер в формате:</b>\n"
                "• <code>+79ххххххххх</code>\n"
                "• <code>+9936ххххххх</code>",
                parse_mode=HTML
            )
            return
    
    elif edit_field == 'name':
        if len(new_value) < 2 or len(new_value) > 50:
            await update.message.reply_text(
                "❌ <b>Имя должно быть от 2 до 50 символов.</b>\n\n"
                "👤 Пожалуйста, введите имя еще раз:",
                parse_mode=HTML
            )
            return
    
    context.user_data['new_value'] = new_value
    context.user_data['awaiting_confirmation'] = True
    
    field_names = {
        'login': 'логин',
        'phone': 'телефон', 
        'name': 'имя'
    }
    
    await update.message.reply_text(
        f"✅ <b>Подтвердите изменение</b>\n\n"
        f"Поле: <b>{field_names[edit_field]}</b>\n"
        f"Старое значение: <code>{selected_user[edit_field]}</code>\n"
        f"Новое значение: <code>{new_value}</code>\n\n"
        f"Нажмите <b>✅ Подтвердить</b> для сохранения или <b>❌ Отменить</b> для отмены.",
        parse_mode=HTML,
        reply_markup=create_edit_confirmation_keyboard()
    )
async def confirm_edit(update: Update, context: CallbackContext) -> None:
    """Подтверждает редактирование пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    selected_user = context.user_data.get('selected_user')
    edit_field = context.user_data.get('edit_field')
    new_value = context.user_data.get('new_value')
    
    if not all([selected_user, edit_field, new_value]):
        await update.message.reply_text("❌ <b>Ошибка: данные для сохранения не найдены</b>", parse_mode=HTML)
        return
    
    success = False
    if edit_field == 'login2' or edit_field == 'birthday' or edit_field == 'city':
        pass  # без валидации для второго логина
    elif edit_field == 'login':
        success = db.update_client_login(selected_user['id'], new_value)
    elif edit_field == 'phone':
        success = db.update_client_phone(selected_user['id'], new_value)
    elif edit_field == 'name':
        success = db.update_client_name(selected_user['id'], new_value)
    
    
    
    if success:
        if edit_field in selected_user:
            selected_user[edit_field] = new_value
        
        field_names = {
            'login': 'логин',
            'phone': 'телефон',
            'name': 'имя'
        }
        
        await update.message.reply_text(
            f"✅ <b>{field_names[edit_field].title()} успешно обновлен</b>\n\n"
            f"Новое значение: <code>{new_value}</code>",
            parse_mode=HTML
        )
        
        pass  # убран вызов
    else:
        await update.message.reply_text(
            f"❌ <b>Ошибка при обновлении {edit_field}</b>\n"
            f"Возможно, такой логин уже существует.",
            parse_mode=HTML
        )
async def cancel_edit(update: Update, context: CallbackContext) -> None:
    """Отменяет редактирование пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    context.user_data.pop('edit_field', None)
    context.user_data.pop('new_value', None)
    context.user_data.pop('awaiting_confirmation', None)
    
    await update.message.reply_text("❌ <b>Редактирование отменено</b>", parse_mode=HTML)
# ==================== ФУНКЦИИ ДЛЯ ОНЛАЙН КЛИЕНТОВ ====================

async def online(update: Update, context: CallbackContext) -> None:
    """Inline-меню онлайн клиентов"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text("🔄 <b>Получаю список онлайн клиентов...</b>", parse_mode=HTML)
    
    def get_online_data():
        from panel_manager import get_panels_list, set_active_panel, get_active_panel
        from xui_api import get_online_clients, get_inbounds_list
        
        panels = get_panels_list()
        original = get_active_panel()['id']
        result = []
        
        for panel in panels:
            set_active_panel(panel['id'])
            online = get_online_clients()
            inbounds = get_inbounds_list()
            clients = []
            seen_emails = set()
            for inbound in inbounds:
                for c in inbound.get('clientStats', []):
                    email = c.get('email', '')
                    if email in online and email not in seen_emails:
                        seen_emails.add(email)
                        clients.append({
                            'email': email,
                            'up': c.get('up', 0),
                            'down': c.get('down', 0),
                            'total': c.get('total', 0),
                            'inbound': inbound.get('remark', '?').strip(),
                            'inbound_id': inbound.get('id')
                        })
            result.append({
                'name': panel['name'],
                'emoji': panel['emoji'],
                'online': len(online),
                'clients': clients
            })
        
        set_active_panel(original)
        return result
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_online_data)
        panels_data = future.result()
    
    for panel in panels_data:
        if panel['online'] == 0:
            continue
        
        keyboard = []
        row = []
        for c in panel['clients']:
            row.append(InlineKeyboardButton(
                f"👤 {c['email'][:20]}", 
                callback_data=f"online_info_{c['email']}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        message = f"{panel['emoji']} <b>{panel['name']}</b> — 🟢 {panel['online']} онлайн"
        
        if keyboard:
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="online_refresh")])
            await update.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=HTML
            )
    
    if not panels_data or all(p['online'] == 0 for p in panels_data):
        await update.message.reply_text("❌ <b>Нет клиентов онлайн</b>", parse_mode=HTML)


async def handle_server_refresh(update: Update, context: CallbackContext) -> None:
    """Обновляет состояние сервера"""
    query = update.callback_query
    await query.answer("🔄 Обновлено!")
    from server_info import get_server_status
    from datetime import datetime
    
    def get_data():
        return get_server_status()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_data)
        info = future.result()
    
    now = datetime.now().strftime('%H:%M:%S')
    if info:
        info += f"\n\n<i>Обновлено: {now}</i>"
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="server_refresh")]]
        await query.edit_message_text(info, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=HTML)



async def handle_online_refresh(update: Update, context: CallbackContext) -> None:
    """Обновляет список онлайн клиентов"""
    query = update.callback_query
    await query.answer("Обновлено!")
    from datetime import datetime
    now = datetime.now().strftime('%H:%M:%S')
    
    def get_online_data():
        from panel_manager import get_panels_list, set_active_panel, get_active_panel
        from xui_api import get_online_clients, get_inbounds_list
        panels = get_panels_list()
        original = get_active_panel()['id']
        result = []
        for panel in panels:
            set_active_panel(panel['id'])
            online = get_online_clients()
            inbounds = get_inbounds_list()
            clients = []
            seen_emails = set()
            for inbound in inbounds:
                for c in inbound.get('clientStats', []):
                    email = c.get('email', '')
                    if email in online and email not in seen_emails:
                        seen_emails.add(email)
                        clients.append({
                            'email': email,
                            'up': c.get('up', 0),
                            'down': c.get('down', 0),
                            'total': c.get('total', 0),
                            'inbound': inbound.get('remark', '?').strip(),
                            'inbound_id': inbound.get('id')
                        })
            result.append({'name': panel['name'], 'emoji': panel['emoji'], 'online': len(online), 'clients': clients})
        set_active_panel(original)
        return result
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_online_data)
        panels_data = future.result()
    
    # Перестраиваем сообщение
    has_online = False
    message_parts = []
    all_keyboards = []
    
    for panel in panels_data:
        if panel['online'] == 0:
            continue
        has_online = True
        keyboard = []
        row = []
        for c in panel['clients']:
            row.append(InlineKeyboardButton(f"👤 {c['email'][:20]}", callback_data=f"online_info_{c['email']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="online_refresh")])
        
        msg = f"{panel['emoji']} <b>{panel['name']}</b> — 🟢 {panel['online']} онлайн\n<i>Обновлено: {now}</i>"
        message_parts.append((msg, keyboard))
    
    if not has_online:
        await query.edit_message_text("❌ <b>Нет клиентов онлайн</b>", parse_mode=HTML)
        return
    
    # Показываем только первую панель (остальные можно добавить)
    msg, keyboard = message_parts[0]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=HTML)

async def handle_online_info(update: Update, context: CallbackContext) -> None:
    """Показывает информацию о клиенте по кнопке"""
    query = update.callback_query
    await query.answer("📊 Загружаю информацию...")
    
    email = query.data.replace("online_info_", "")
    
    def get_client_info():
        from xui_api import get_inbounds_list
        
        inbounds = get_inbounds_list()
        for inbound in inbounds:
            for c in inbound.get('clientStats', []):
                if c.get('email') == email:
                    up = c.get('up', 0)
                    down = c.get('down', 0)
                    return {
                        'email': email,
                        'up': up,
                        'down': down,
                        'total': up + down,
                        'inbound': inbound.get('remark', '?').strip(),
                        'protocol': inbound.get('protocol', '?').upper(),
                        'port': inbound.get('port', '?'),
                        'flow': c.get('flow', ''),
                        'total_limit': c.get('total', 0),
                        'enable': c.get('enable', True),
                        'expiry': c.get('expiryTime', 0)
                    }
        return None
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_client_info)
        info = future.result()
    
    if info:
        status = '🟢 Активен' if info['enable'] else '🔴 Отключён'
        limit = f"{format_traffic(info['total_limit'])}" if info['total_limit'] > 0 else '♾️'
        
        message = f"👤 <b>Детальная информация о клиенте</b>\n\n"
        message += f"📧 <b>Email:</b> {info['email']}\n"
        message += f"📡 <b>Инбаунд:</b> {info['inbound']}\n"
        message += f"🔌 <b>Протокол:</b> {info['protocol']}:{info['port']}\n"
        if info['flow']:
            message += f"🌊 <b>Flow:</b> {info['flow']}\n"
        message += f"💾 <b>Трафик:</b> ↑{format_traffic(info['up'])} ↓{format_traffic(info['down'])}\n"
        message += f"📊 <b>Всего:</b> {format_traffic(info['total'])} / {limit}\n"
        message += f"🔒 <b>Статус:</b> {status}\n"
        message += f"🟢 <b>Онлайн</b>\n\n"
        
        # IP, страна, оператор
        try:
            from xui_api import get_client_ips
            import requests as req
            ips = get_client_ips(info['email'])
            if ips:
                ip = str(ips[0]).split(' ')[0].strip()
                if ip and '.' in ip:
                    message += f"🌐 <b>IP:</b> <code>{ip}</code>\n"
                    try:
                        r = req.get(f"http://ip-api.com/json/{ip}?fields=country,isp", timeout=3)
                        if r.status_code == 200:
                            geo = r.json()
                            country = geo.get('country', '?')
                            isp = geo.get('isp', '')
                            flags = {'Russia': '🇷🇺', 'Finland': '🇫🇮'}
                            flag = flags.get(country, '🌍')
                            message += f"🌍 <b>Страна:</b> {flag} {country}\n"
                            if isp:
                                message += f"📡 <b>Оператор:</b> {isp}\n"
                    except:
                        pass
        except:
            pass
        
        # Срок
        expiry = info.get('expiry', 0)
        if expiry > 0:
            from datetime import datetime
            dt = datetime.fromtimestamp(expiry / 1000)
            days = (expiry / 1000 - datetime.now().timestamp()) / 86400
            message += f"⏰ <b>Срок:</b> {dt.strftime('%d.%m.%Y')}\n"
            if days > 0:
                message += f"📅 <b>Осталось:</b> {int(days)} дн.\n"
        else:
            message += f"⏰ <b>Срок:</b> ♾️ Бессрочно\n"
        
        await query.edit_message_text(message, parse_mode=HTML)
    else:
        await query.edit_message_text(f"❌ Клиент не найден", parse_mode=HTML)

async def online_old(update: Update, context: CallbackContext) -> None:
    """Показывает список клиентов, которые онлайн (через API панели)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔄 <b>Получаю список онлайн клиентов через API...</b>", parse_mode=HTML)
    
    def get_online_data():
        try:
            online_emails = get_online_clients()
            last_online_map = get_last_online()
            inbounds = get_inbounds_list()
            
            online_details = []
            for inbound in inbounds:
                clients = inbound.get('clientStats', [])
                for client in clients:
                    email = client.get('email', '')
                    if email in online_emails:
                        online_details.append({
                            'email': email,
                            'inbound': inbound.get('remark', 'Unknown'),
                            'id': inbound.get('id'),
                            'up': client.get('up', 0),
                            'down': client.get('down', 0),
                            'enable': client.get('enable', True),
                            'last_online_ts': last_online_map.get(email, 0)
                        })
            
            logger.info(f"Онлайн клиентов через API: {len(online_details)}")
            return online_details
        except Exception as e:
            logger.error(f"Ошибка получения онлайн клиентов: {e}")
            return []
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_online_data)
        online_clients = future.result()
    
    if online_clients:
        online_clients.sort(key=lambda x: x['email'])
        
        message = "🌐 <b>Онлайн клиенты (API панели)</b>\n\n"
        message += f"🟢 <b>Сейчас онлайн:</b> {len(online_clients)} клиентов\n\n"
        
        for i, client in enumerate(online_clients, 1):
            email = client.get('email', 'Без email')
            inbound_name = client.get('inbound', 'Unknown')
            traffic_up = format_traffic(client.get('up', 0))
            traffic_down = format_traffic(client.get('down', 0))
            
            last_ts = client.get('last_online_ts', 0)
            last_seen_str = ""
            if last_ts > 0:
                diff = int(time.time() - last_ts / 1000) if last_ts > 1000000000000 else int(time.time() - last_ts)
                if diff < 60:
                    last_seen_str = f" (был {diff}с назад)"
                elif diff < 3600:
                    last_seen_str = f" (был {diff // 60}мин назад)"
            
            message += f"{i}. <code>{email}</code>{last_seen_str}\n"
            message += f"   📡 Инбаунд: {inbound_name}\n"
            message += f"   📊 Трафик: ↑{traffic_up} ↓{traffic_down}\n\n"
        
        message += "💡 <i>Данные получены напрямую из панели 3x-ui</i>"
        
        await update.message.reply_text(
            message, 
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        context.user_data['state'] = BotState.MAIN_MENU
    else:
        await update.message.reply_text(
            "❌ <b>Нет клиентов онлайн в данный момент</b>\n\n"
            "🔍 <i>Данные получены через API панели 3x-ui</i>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        context.user_data['state'] = BotState.MAIN_MENU
# ==================== ПОЛЬЗОВАТЕЛЬСКИЕ ФУНКЦИИ ====================

async def statistics(update: Update, context: CallbackContext) -> None:
    """Показывает информацию о клиенте"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔄 <b>Получаю информацию...</b>", parse_mode=HTML)
    
    def get_all_info():
        from xui_api import get_inbounds_list, get_client_ips
        from datetime import datetime
        import requests as req
        
        inbounds = get_inbounds_list()
        result = {'found': False}
        
        for inbound in inbounds:
            for c in inbound.get('clientStats', []):
                if c.get('email') == client['login']:
                    result['found'] = True
                    result['up'] = c.get('up', 0)
                    result['down'] = c.get('down', 0)
                    result['total'] = c.get('total', 0)
                    result['enable'] = c.get('enable', True)
                    result['expiry'] = c.get('expiryTime', 0)
                    break
        
        # IP и гео
        try:
            ips = get_client_ips(client['login'])
            if ips:
                ip = str(ips[0]).split(' ')[0].strip()
                if ip and '.' in ip:
                    result['ip'] = ip
                    # Страна и оператор
                    try:
                        r = req.get(f"http://ip-api.com/json/{ip}?fields=country,isp", timeout=3)
                        if r.status_code == 200:
                            geo = r.json()
                            result['country'] = geo.get('country', '')
                            result['isp'] = geo.get('isp', '')
                    except: pass
                    # Город и область через DaData
                    try:
                        r = req.get(
                            f"https://suggestions.dadata.ru/suggestions/api/4_1/rs/detectAddressByIp?ip={ip}",
                            headers={"Authorization": "Token a20c77a8cc6393aee5070f10e0fc6e4116d3423c"},
                            timeout=3
                        )
                        if r.status_code == 200:
                            loc = r.json().get('location', {}).get('data', {})
                            result['region'] = loc.get('region_with_type', '')
                            result['city'] = loc.get('city_with_type', '')
                    except: pass
        except: pass
        
        return result
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_all_info)
        info = future.result()
    
    months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
             'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
    now = datetime.now()
    
    message = "📊 <b>ИНФОРМАЦИЯ</b>\n\n"
    message += f"👤 <b>{client['name']}</b>\n"
    message += f"📝 <b>Логин:</b> <code>{client['login']}</code>\n"
    message += "──────────────────\n"
    message += f"📞 <b>Телефон:</b> <code>{client['phone']}</code>\n" + (f"📶 <b>Сим-карта:</b> {get_operator(client.get('phone', '')).replace(' | 📶 ', '')}\n" if get_operator(client.get('phone', '')) else "")
    
    # Дата регистрации
    reg_date = client['registration_date']
    if isinstance(reg_date, str):
        try:
            dt = datetime.strptime(reg_date, '%Y-%m-%d %H:%M:%S')
            message += f"📅 <b>Регистрация:</b> {dt.day} {months[dt.month-1]} {dt.year}\n"
        except:
            pass
    
    # Гео
    if info.get('region'):
        message += f"🏙️ <b>Область:</b> {info['region']}\n"
    if info.get('city'):
        message += f"🏙️ <b>Город:</b> {info['city']}\n"
    if info.get('country'):
        flags = {'Russia': '🇷🇺', 'Finland': '🇫🇮'}
        flag = flags.get(info['country'], '🌍')
        message += f"🌍 <b>Страна:</b> {flag} {info['country']}\n"
    message += "──────────────────\n"
    if info.get('ip'):
        message += f"🌐 <b>IP:</b> <code>{info['ip']}</code>\n"
    if info.get('isp'):
        message += f"📡 <b>Оператор:</b> {info['isp']}\n"
    message += "──────────────────\n"
    # ДР
    
    # День рождения
    birthday = client.get('birthday', '')
    if birthday:
        try:
            b_day, b_month, _ = birthday.split('.')
            zodiac = get_zodiac(int(b_day), int(b_month))
            message += f"\n🎂 <b>День рождения:</b> {birthday}\n"
            message += f"♒ <b>Зодиак:</b> {zodiac}\n"
        except:
            pass
    
    # Трафик
    if info.get('found'):
        up = format_traffic(info.get('up', 0))
        down = format_traffic(info.get('down', 0))
        total = format_traffic(info.get('up', 0) + info.get('down', 0))
        
        if info.get('total', 0) > 0:
            pct = (info.get('up', 0) + info.get('down', 0)) / info['total'] * 100
        else:
            pass
        
        status = '🟢' if info.get('enable', True) else '🔴'
        
        expiry = info.get('expiry', 0)
        if expiry > 0:
            dt = datetime.fromtimestamp(expiry / 1000)
            days = (expiry / 1000 - datetime.now().timestamp()) / 86400
            message += f" | ⏰ {dt.strftime('%d.%m.%Y')}"
            message += f" ({int(days)}дн)" if days > 0 else " ❌"
        else:
    
            pass
    await update.message.reply_text(message, parse_mode=HTML)

async def direct_keys(update: Update, context: CallbackContext) -> None:
    """Показывает прямые ключи через новый API"""
    # Определяем откуда вызов — сообщение или callback
    if hasattr(update, 'callback_query') and update.callback_query:
        message = update.callback_query.message
        reply_fn = message.reply_text
    else:
        reply_fn = update.message.reply_text
    
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    if not client:
        await reply_fn("❌ <b>Вы не зарегистрированы</b>", parse_mode='HTML')
        return
    
    await reply_fn("🔑 <b>Получаю прямые ключи...</b>", parse_mode='HTML')
    
    def get_keys():
        from xui_api import get_inbounds_list, get_sub_links_new
        inbounds = get_inbounds_list()
        email = client['login']
        results = []
        seen = set()
        for inbound in inbounds:
            settings = inbound.get('settings', {})
            if isinstance(settings, str):
                import json as j
                settings = j.loads(settings) if settings.strip() else {}
            for c in settings.get('clients', []):
                if c.get('email') == email:
                    sub_id = c.get('subId', '')
                    if sub_id and sub_id not in seen:
                        seen.add(sub_id)
                        links = get_sub_links_new(sub_id)
                        if links:
                            results.append({
                                'sub_id': sub_id,
                                'remark': inbound.get('remark', '?').strip(),
                                'links': links
                            })
        return results
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_keys)
        results = future.result()
    
    if not results:
        await update.message.reply_text("❌ <b>Ключи не найдены</b>", parse_mode='HTML')
        return
    
    message = "🔑 <b>ПРЯМЫЕ КЛЮЧИ</b>\n━━━━━━━━━━━━━━━━━\n\n"
    for r in results:
        message += f"📡 <b>{r['remark']}</b>\n"
        for i, link in enumerate(r['links'], 1):
            short = link
            message += f"{i}. <code>{short}</code>\n"
        message += "\n"
    message += "<i>Нажмите на ключ чтобы скопировать</i>"
    
    await reply_fn(message, parse_mode='HTML')


# ==================== AI ПОМОЩНИК (DeepSeek) ====================
DEEPSEEK_API_KEY = "sk-2175559a00504846ad07716a07e451c7"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

async def ai_help(update: Update, context: CallbackContext) -> None:
    """AI-помощник для клиентов — режим диалога"""
    user = update.effective_user
    
    # Проверяем что клиент зарегистрирован
    client = db.get_client_by_telegram_id(user.id)
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы</b>", parse_mode='HTML')
        return
    
    context.user_data['asking_ai'] = True
    
    keyboard = [[InlineKeyboardButton("❌ Выйти из AI", callback_data="ai_exit")]]
    
    await update.message.reply_text(
        "🤖 <b>AI ПОМОЩНИК (диалог)</b>\n\n"
        "Задавайте вопросы о VPN, подключении, настройках.\n"
        "Я постараюсь помочь!\n\n"
        "<i>Для выхода нажмите кнопку ниже</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def ai_answer(update: Update, context: CallbackContext) -> None:
    """Отправляет вопрос в DeepSeek и возвращает ответ"""
    if not context.user_data.get('asking_ai'):
        return
    
    question = update.message.text
    
    # Проверяем команду выхода
    if question == "❌ Выйти из AI":
        context.user_data.pop('asking_ai')
        await update.message.reply_text("✅ <b>Вы вышли из AI-помощника.</b> Используйте кнопки меню.", parse_mode='HTML')
        return
    
    import logging
    logging.getLogger(__name__).info(f"AI вопрос: {question}")
    await update.message.reply_text("🤖 <b>Думаю...</b>", parse_mode='HTML')
    def ask_deepseek(q):
        import requests
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "deepseek-chat", "messages": [{"role": "system", "content": "Ты — поддержка VPN-сервиса SLK. Отвечай кратко, на русском."}, {"role": "user", "content": q}], "max_tokens": 500}
        try:
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            return "❌ Ошибка AI. Попробуйте позже."
        except:
            return "❌ AI недоступен. Попробуйте позже."
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(ask_deepseek, question)
        answer = future.result()
    
    await update.message.reply_text(
        f"🤖 <b>Ответ AI:</b>\n\n{answer}\n\n<i>💡 Это автоматический ответ. Для связи с администратором нажмите «💬 Написать админу»</i>",
        parse_mode='HTML'
    )


async def link(update: Update, context: CallbackContext) -> None:
    """Показывает ссылку подписки"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌  <b>Вы не зарегистрированы в системе</b>", parse_mode=HTML)
        return
    
    
    
    await update.message.reply_text("🔄 <b>Получаю информацию о вашей подписке...</b>", parse_mode=HTML)
    
    def get_sub_data():
        try:
            inbounds = get_inbounds_list()
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    try:
                        if settings.strip():
                            settings = json.loads(settings)
                        else:
                            settings = {}
                    except json.JSONDecodeError:
                        settings = {}
                
                if isinstance(settings, dict):
                    clients_settings = settings.get('clients', [])
                    for xui_client in clients_settings:
                        if isinstance(xui_client, dict) and xui_client.get('email') == client['login']:
                            sub_id = xui_client.get('subId')
                            if sub_id:
                                sub_link = f"{SUBSCRIPTION_URL}/sub/{SUBSCRIPTION_EXTRA_PATH}/{sub_id}"
                                return sub_link, sub_id
            return None, None
        except Exception as e:
            logger.error(f"Ошибка получения ссылки подписки: {e}")
            return None, None
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_sub_data)
        result = future.result()
    
    if result and result[0]:
        subscription_link, sub_id = result
        
        # Формируем JSON ссылку
        json_link = ""
        try:
            from config import SUBSCRIPTION_JSON_PATH
            if SUBSCRIPTION_JSON_PATH:
                json_link = f"{SUBSCRIPTION_URL}/json/{SUBSCRIPTION_JSON_PATH}/{sub_id}"
        except:
            pass
        
        # Inline-кнопки
        keyboard = []
        if subscription_link:
            keyboard.append([InlineKeyboardButton("📋 Открыть подписку", url=f"{SUBSCRIPTION_URL}/sub/{SUBSCRIPTION_EXTRA_PATH}/{sub_id}")])
        
        
        
        message = f"👤 <b>Логин:</b> <code>{client['login']}</code>\n\n"
        message += "🔗 <b>СТРАНИЦА ПОДПИСКИ</b>\n"
        message += "━━━━━━━━━━━━━━━━━\n"
        message += "Нажмите кнопку чтобы открыть:\n"
        message += "  • Статистика трафика\n"
        message += "  • Ссылки для подключения\n"
        message += "  • Скачивание приложений\n\n"
        message += "<i>👇 Нажмите кнопку ниже</i>"
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=HTML)
    else:
        await update.message.reply_text(
            "❌ <b>Не удалось получить ссылку подписки.</b>\n"
            "Возможно, ваш аккаунт не активирован.",
            parse_mode=HTML
        )

async def qr_code(update: Update, context: CallbackContext) -> None:
    """Меню выбора QR-кода"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы</b>", parse_mode=HTML)
        return
    
    keyboard = [
        [InlineKeyboardButton("📋 Обычная подписка", callback_data="qr_sub")],
        [InlineKeyboardButton("📋 JSON подписка", callback_data="qr_json")],
    ]
    
    await update.message.reply_text(
        "📱 <b>QR-КОД</b>\n\n"
        "<b>Выберите тип подписки:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

async def handle_qr_callback(update: Update, context: CallbackContext) -> None:
    """Обрабатывает выбор QR-кода"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await query.edit_message_text("❌ <b>Вы не зарегистрированы</b>", parse_mode=HTML)
        return
    
    def get_sub_data():
        try:
            from xui_api import get_inbounds_list
            import json
            inbounds = get_inbounds_list()
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    try:
                        settings = json.loads(settings) if settings.strip() else {}
                    except:
                        settings = {}
                if isinstance(settings, dict):
                    for c in settings.get('clients', []):
                        if c.get('email') == client['login']:
                            return c.get('subId')
            return None
        except:
            return None
    
    sub_id = get_sub_data()
    if not sub_id:
        await query.edit_message_text("❌ <b>Подписка не найдена</b>", parse_mode=HTML)
        return
    
    if query.data == "qr_sub":
        link = f"{SUBSCRIPTION_URL}/sub/{SUBSCRIPTION_EXTRA_PATH}/{sub_id}"
        label = "Обычная подписка"
    else:
        link = f"{SUBSCRIPTION_URL}/json/{SUBSCRIPTION_JSON_PATH}/{sub_id}"
        label = "JSON подписка"
    
    # Генерируем QR
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    
    await query.message.reply_photo(
        photo=bio,
        caption=f"📱 <b>QR-код: {label}</b>\n<code>{link[:60]}...</code>",
        parse_mode=HTML
    )
    await query.edit_message_text("✅ <b>QR-код отправлен!</b>", parse_mode=HTML)

async def qr_code_old(update: Update, context: CallbackContext) -> None:
    """Генерирует QR-код для подключения"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы в системе</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔄 <b>Генерирую QR-код для подключения...</b>", parse_mode=HTML)
    
    def generate_qr_code():
        try:
            inbounds = get_inbounds_list()
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    try:
                        if settings.strip():
                            settings = json.loads(settings)
                        else:
                            settings = {}
                    except json.JSONDecodeError:
                        settings = {}
                
                if isinstance(settings, dict):
                    clients_settings = settings.get('clients', [])
                    for xui_client in clients_settings:
                        if isinstance(xui_client, dict) and xui_client.get('email') == client['login']:
                            sub_id = xui_client.get('subId')
                            if sub_id:
                                subscription_link = f"{SUBSCRIPTION_URL}/sub/{SUBSCRIPTION_EXTRA_PATH}/{sub_id}"
                                
                                qr = qrcode.QRCode(
                                    version=1,
                                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                                    box_size=10,
                                    border=4,
                                )
                                qr.add_data(subscription_link)
                                qr.make(fit=True)
                                
                                img = qr.make_image(fill_color="black", back_color="white")
                                bio = BytesIO()
                                img.save(bio, 'PNG')
                                bio.seek(0)
                                
                                return bio, subscription_link
            return None, None
        except Exception as e:
            logger.error(f"Ошибка генерации QR-кода: {e}")
            return None, None
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(generate_qr_code)
        qr_code_bio, subscription_link = future.result()
    
    if qr_code_bio and subscription_link:
        message = "📱 <b>QR-код для подключения</b>\n\n"
        message += f"👤 <b>Логин:</b> <code>{client['login']}</code>\n\n"
        message += "• Откройте приложение V2RayTun\n"
        message += "• Нажмите 'Добавить по QR-коду'\n"
        message += "• Наведите камеру на код\n"
        message += "• Наслаждайтесь быстрым интернетом! 🚀"
        
        await update.message.reply_photo(
            photo=qr_code_bio,
            caption=message,
            parse_mode=HTML
        )
    else:
        await update.message.reply_text(
            "❌ <b>Не удалось сгенерировать QR-код.</b>\n"
            "Возможно, ваш аккаунт не активирован.",
            parse_mode=HTML
        )


async def vpn_status(update: Update, context: CallbackContext) -> None:
    """Проверяет статус VPN клиента"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы</b>", parse_mode=HTML)
        return
    
    await update.message.reply_text("🔄 <b>Проверяю подключение...</b>", parse_mode=HTML)
    await update.message.reply_sticker('CAACAgIAAxkBAAI1iGohmQAB-JJJJndUBI0R3sGYTBKZiQACoQwAAkI1CUsKh5IXMf-oETsE')
    
    def check():
        from panel_manager import get_panels_list, set_active_panel, get_active_panel
        from xui_api import get_online_clients, get_client_ips
        import requests as req
        from datetime import datetime
        
        panels = get_panels_list()
        original = get_active_panel()['id']
        results = []
        
        for panel in panels:
            set_active_panel(panel['id'])
            online = get_online_clients()
            
            # Проверяем все логины клиента + поиск по tgId
            is_online = False
            check_logins = [client['login']]
            if client.get('login2'):
                check_logins.append(client['login2'])
            
            # Ищем по tgId в настройках клиентов
            import json
            try:
                from xui_api import get_inbounds_list
                inbounds = get_inbounds_list()
                for inbound in inbounds:
                    settings = inbound.get('settings', {})
                    if isinstance(settings, str):
                        settings = json.loads(settings) if settings.strip() else {}
                    if isinstance(settings, dict):
                        for c in settings.get('clients', []):
                            if str(c.get('tgId', '')) == str(user.id):
                                email = c.get('email', '')
                                if email not in check_logins:
                                    check_logins.append(email)
            except:
                pass
            
            for login in check_logins:
                if login in online:
                    is_online = True
                    
                    # Получаем IP
                    ips = get_client_ips(login)
                    ip = str(ips[0]).split(' ')[0].strip() if ips else '?'
                    isp = ''
                    if ip and '.' in ip:
                        try:
                            r = req.get(f"http://ip-api.com/json/{ip}?fields=isp", timeout=3)
                            if r.status_code == 200:
                                isp = r.json().get('isp', '')
                        except: pass
                    
                    results.append({
                        'panel': panel['name'],
                        'emoji': panel['emoji'],
                        'online': True,
                        'login': login,
                        'ip': ip,
                        'isp': isp
                    })
                    break
            
            if not is_online:
                results.append({
                    'panel': panel['name'],
                    'emoji': panel['emoji'],
                    'online': False,
                    'login': client['login']
                })
        
        set_active_panel(original)
        return results
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(check)
        results = future.result()
    
    online_count = sum(1 for r in results if r['online'])
    
    if online_count > 0:
        message = "🛡️ <b>СТАТУС VPN</b>\n\n"
        for r in results:
            if r['online']:
                message += f"🟢 {r['emoji']} {r['panel']}: <b>Подключён</b> | <code>{r['login']}</code>\n"
    else:
        message = "🛡️ <b>СТАТУС VPN</b>\n\n"
        message += "🔴 <b>Вы не подключены к VPN</b>\n\n"
        message += "📱 Откройте приложение <b>v2rayTun</b>\n"
        message += "🔗 Импортируйте подписку из раздела <b>Ссылки</b>\n"
        message += "▶️ Нажмите <b>Подключить</b>"
    
    await update.message.reply_text(message, parse_mode=HTML)

async def app_info(update: Update, context: CallbackContext) -> None:
    """Информация о приложении с inline-кнопками"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы</b>", parse_mode=HTML)
        return
    
    keyboard = [
        [InlineKeyboardButton("🤖 Открыть в Google Play", url="https://play.google.com/store/apps/details?id=com.v2raytun.android")],
        [InlineKeyboardButton("🍎 Открыть в App Store", url="https://apps.apple.com/app/v2raytun/id6476628951")],
    ]
    
    message = "📱 <b>v2rayTun</b>\n\n"
    message += "🏆 <b>Лучшее приложение для VPN</b>\n\n"
    message += "<b>Возможности:</b>\n"
    message += "• Поддержка VLESS, VMess, Trojan\n"
    message += "• Reality + XTLS Vision\n"
    message += "• Импорт по QR-коду\n"
    message += "• Импорт по ссылке из буфера\n"
    message += "• Автозапуск при загрузке\n"
    message += "• Раздельный туннель (обход приложений)\n\n"
    message += "<b>Как настроить:</b>\n"
    message += "1️⃣ Нажмите ➕ → Импорт из буфера обмена\n"
    message += "2️⃣ Или отсканируйте QR-код из раздела 📱 QR-Код\n"
    message += "3️⃣ Нажмите ▶️ для подключения\n\n"
    message += "👇 <b>Скачайте приложение:</b>"
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

async def android_app(update: Update, context: CallbackContext) -> None:
    """Открывает ссылку на v2rayTun в Google Play"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы в системе</b>", parse_mode=HTML)
        return
    
    message = "🤖 <b>Приложение для Android</b>\n\n"
    message += "📱 <b>v2rayTun</b> - лучшее приложение для работы с VPN\n"
    message += "⭐ Рейтинг: 4.8\n"
    message += "📥 Размер: 15 MB\n"
    message += "🔒 Безопасно и надежно\n\n"
    message += "👇 <b>Нажмите на кнопку ниже, чтобы открыть Google Play:</b>"
    
    from keyboards import create_app_links_keyboard
    await update.message.reply_text(
        message, 
        reply_markup=create_app_links_keyboard(),
        parse_mode=HTML
    )
async def iphone_app(update: Update, context: CallbackContext) -> None:
    """Открывает ссылку на v2rayTun в App Store"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы в системе</b>", parse_mode=HTML)
        return
    
    message = "🍎 <b>Приложение для iPhone</b>\n\n"
    message += "📱 <b>v2rayTun</b> - лучшее приложение для работы с VPN\n"
    message += "⭐ Рейтинг: 4.9\n"
    message += "📥 Размер: 25 MB\n"
    message += "🔒 Безопасно и надежно\n\n"
    message += "👇 <b>Нажмите на кнопку ниже, чтобы открыть App Store:</b>"
    
    from keyboards import create_iphone_links_keyboard
    await update.message.reply_text(
        message, 
        reply_markup=create_iphone_links_keyboard(),
        parse_mode=HTML
    )

async def open_web_app(update: Update, context: CallbackContext) -> None:
    """Открывает веб-кабинет как Web App"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)
    
    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы</b>", parse_mode=HTML)
        return
    
    from telegram import WebAppInfo
    
    keyboard = [[InlineKeyboardButton(
        "🏢 Открыть личный кабинет",
        web_app=WebAppInfo(url="http://144.31.133.182:8080")
    )]]
    
    await update.message.reply_text(
        "🏢 <b>ЛИЧНЫЙ КАБИНЕТ</b>\n\n"
        "👤 Для входа используйте ваш номер телефона:\n"
        f"📞 <code>{client['phone']}</code>\n\n"
        "👇 <b>Нажмите кнопку чтобы открыть:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=HTML
    )

async def show_direct_keys_handler(update: Update, context: CallbackContext) -> None:
    """Показывает прямые ключи по нажатию кнопки"""
    query = update.callback_query
    await query.answer()
    await direct_keys(update, context)
    await query.delete_message()

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
    from config import SUBSCRIPTION_URL, SUBSCRIPTION_JSON_PATH, SUBSCRIPTION_EXTRA_PATH, SUBSCRIPTION_JSON_PATH
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
async def handle_message(update: Update, context: CallbackContext) -> None:
    """Обработка текстовых сообщений в зависимости от состояния"""
    user_id = update.effective_user.id
    current_state = context.user_data.get('state', BotState.MAIN_MENU)
    message_text = update.message.text
    
    # Проверяем ввод Telegram ID
    if context.user_data.get('waiting_for_server'):
        ip = update.message.text.strip()
        servers = load_servers()
        if ip not in servers:
            servers.append(ip)
            save_servers(servers)
            await update.message.reply_text(f'✅ <b>{ip} добавлен!</b>', parse_mode='HTML')
        else:
            await update.message.reply_text(f'⚠️ <b>{ip}</b> уже в списке', parse_mode='HTML')
        context.user_data.pop('waiting_for_server')
        return
    if context.user_data.get('asking_ai'):
        await ai_answer(update, context)
        return
    if context.user_data.get('awaiting_bonus_password') and update.message.text and not is_admin(update.effective_user.id):
        if update.message.text == 'slkbonus':
            context.user_data.pop('awaiting_bonus_password', None)
            context.user_data['bonus_unlocked'] = True
            await update.message.reply_text("✅ <b>Доступ разрешён!</b>", parse_mode=HTML)
            # Показываем бонусы
            import os
            bonus_path = "/opt/SLV_Bot/Bonus"
            keyboard = [
                [InlineKeyboardButton("🎬 Видео", callback_data="bonus_Video")],
                [InlineKeyboardButton("📸 Фото", callback_data="bonus_Photo")],
                [InlineKeyboardButton("🎵 Музыка", callback_data="bonus_Music")],
                [InlineKeyboardButton("📁 Файлы", callback_data="bonus_Files")],
            ]
            msg = "🎁 <b>БОНУСЫ</b>\n\n<b>Выберите категорию:</b>"
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=HTML)
        else:
            await update.message.reply_text("❌ <b>Неверный пароль!</b>", parse_mode=HTML)
        return
    
    if context.user_data.get('awaiting_city'):
        selected_user = context.user_data.get('selected_user')
        if selected_user and update.message.text:
            city = update.message.text.strip()
            # Записываем напрямую в базу
            import sqlite3
            conn = sqlite3.connect('/opt/SLV_Bot/clients.db')
            conn.execute('UPDATE clients SET city = ? WHERE id = ?', (city, selected_user['id']))
            conn.commit()
            conn.close()
            selected_user['city'] = city
            await update.message.reply_text(
                f"✅ <b>Город сохранён:</b> {city}",
                reply_markup=create_user_actions_keyboard(),
                parse_mode=HTML
            )
        context.user_data.pop('awaiting_city', None)
        context.user_data['state'] = BotState.USER_DETAIL_MENU
        return
    
    if context.user_data.get('awaiting_hwid'):
        selected_user = context.user_data.get('selected_user')
        if selected_user and update.message.text:
            hwid = update.message.text.strip()
            db.update_client_hwid(selected_user['id'], hwid)
            selected_user['hwid'] = hwid
            await update.message.reply_text(
                f"✅ <b>HWID сохранён:</b> <code>{hwid}</code>",
                reply_markup=create_user_actions_keyboard(),
                parse_mode=HTML
            )
        context.user_data.pop('awaiting_hwid', None)
        context.user_data['state'] = BotState.USER_DETAIL_MENU
        return
    
    if context.user_data.get('awaiting_birthday'):
        # Сохраняем день рождения
        selected_user = context.user_data.get('selected_user')
        if selected_user and update.message.text:
            birthday = update.message.text.strip()
            db.update_client_birthday(selected_user['id'], birthday)
            selected_user['birthday'] = birthday
            await update.message.reply_text(
                f"✅ <b>Дата рождения сохранена:</b> {birthday}",
                reply_markup=create_user_actions_keyboard(),
                parse_mode=HTML
            )
        context.user_data.pop('awaiting_birthday', None)
        context.user_data['state'] = BotState.USER_DETAIL_MENU
        return
    
    if context.user_data.get('client_writing'):
        await handle_client_message(update, context)
        return
    
    if context.user_data.get('awaiting_tg_id'):
        await handle_tg_id_input(update, context)
        return
    
    # Проверяем особые состояния
    if context.user_data.get('awaiting_delete_confirmation'):
        if message_text in ["✅ Подтвердить", "❌ Отменить"]:
            await handle_delete_confirmation(update, context)
            return
        else:
            context.user_data.pop('awaiting_delete_confirmation', None)
    
    logger.info(f"Получено сообщение: '{message_text}' от пользователя {user_id}, состояние: {current_state}")
    
    # Обработка состояний админа по отправке сообщений
    if current_state == BotState.ADMIN_CHOOSE_USER:
        await admin_choose_user(update, context)
        return
    
    if current_state == BotState.ADMIN_WRITE_MESSAGE:
        if update.message.photo:
            await admin_handle_media(update, context)
        elif update.message.video:
            await admin_handle_media(update, context)
        elif update.message.voice:
            await admin_handle_media(update, context)
        elif update.message.audio:
            await admin_handle_media(update, context)    
        elif update.message.document:    
            await admin_handle_media(update, context)
        elif update.message.text:
            await admin_handle_message(update, context)
        else:
            await update.message.reply_text(
                "❌ <b>Неподдерживаемый тип сообщения.</b>",
                parse_mode=HTML
            )
        return
    
    # Обработка состояний регистрации
    if current_state == BotState.REGISTRATION_LOGIN:
        await handle_registration_login(update, context)
        return
    
    elif current_state == BotState.REGISTRATION_PHONE:
        await handle_registration_phone(update, context)
        return
    
    elif current_state == BotState.REGISTRATION_NAME:
        await handle_registration_name(update, context)
        return
    
    # Обработка состояний управления пользователями
    elif current_state == BotState.USERS_LIST_MENU:
        if message_text == "⬅️ Назад в меню":
            context.user_data['state'] = BotState.MAIN_MENU
            await update.message.reply_text(
                "🏠 <b>Главное меню:</b>",
                reply_markup=create_admin_keyboard(),
                parse_mode=HTML
            )
        else:
            await user_detail(update, context)
        return
    
    elif current_state == BotState.USER_DETAIL_MENU:
        if message_text == "✏️ Редактировать логин":
            await edit_user_login(update, context)
        elif message_text == "🏙️ Город":
            await edit_user_city(update, context)
        elif message_text == "📱 HWID":
            await edit_user_hwid(update, context)
        elif message_text == "🎂 День рождения":
            await edit_user_birthday(update, context)
        elif message_text == "📞 Редактировать телефон":
            await edit_user_phone(update, context)
        elif message_text == "👤 Редактировать имя":
            await edit_user_name(update, context)
        elif message_text == "🔒 Блокировать/Разблокировать":
            await toggle_user_active(update, context)
        elif message_text == "🗑️ Удалить пользователя":
            await delete_user(update, context)
        elif message_text == "⬅️ Назад к списку":
            await back_to_users_list(update, context)
        else:
            await user_detail(update, context)
        return
    
    # Обработка состояний редактирования пользователя
    elif current_state in [BotState.USER_EDIT_LOGIN, BotState.USER_EDIT_PHONE, BotState.USER_EDIT_NAME, BotState.USER_EDIT_CITY]:
        if message_text == "✅ Подтвердить":
            await confirm_edit(update, context)
        elif message_text == "❌ Отменить":
            await cancel_edit(update, context)
        else:
            await handle_user_edit_input(update, context)
        return
    
    elif current_state == BotState.USER_CONFIRM_DELETE:
        if message_text == "✅ Подтвердить":
            await confirm_user_delete(update, context)
        elif message_text == "❌ Отменить":
            await update.message.reply_text("❌ <b>Удаление отменено</b>", parse_mode=HTML)
            await user_detail(update, context)
        return
    
    # Обработка состояний админского меню
    elif current_state == BotState.INBOUNDS_MENU:
        if message_text == "⬅️ Назад в меню":
            context.user_data['state'] = BotState.MAIN_MENU
            await update.message.reply_text(
                "🏠 <b>Главное меню:</b>",
                reply_markup=create_admin_keyboard(),
                parse_mode=HTML
            )
        else:
            await inbound_detail(update, context)
        return
    
    elif current_state == BotState.ALL_CLIENTS_MENU:
        if message_text == "⬅️ Назад в меню":
            context.user_data['state'] = BotState.MAIN_MENU
            await update.message.reply_text(
                "🏠 <b>Главное меню:</b>",
                reply_markup=create_admin_keyboard(),
                parse_mode=HTML
            )
        else:
            await clients_list(update, context)
        return

    elif current_state == BotState.CLIENTS_MENU:
        if message_text == "⬅️ Назад":
            await all_clients(update, context)
        elif message_text == "⬅️ Назад в меню":
            context.user_data['state'] = BotState.MAIN_MENU
            await update.message.reply_text(
                "🏠 <b>Главное меню:</b>",
                reply_markup=create_admin_keyboard(),
                parse_mode=HTML
            )
        else:
            await client_detail(update, context)
        return
    
    elif current_state == BotState.CLIENT_DETAIL_MENU:
        if message_text == "🔄 Обновить клиента":
            await refresh_client_status(update, context)
        elif message_text == "🗑️ Удалить клиента":
            await delete_client(update, context)
        elif message_text == "📊 Сбросить трафик":
            await reset_client_traffic(update, context)
        elif message_text == "🌍 IP адреса":
            await show_client_ips(update, context)
        elif message_text == "🆔 Привязать TG":
            await bind_telegram_id(update, context)
        elif message_text == "⬅️ Назад к клиентам":
            await back_to_clients(update, context)
        else:
            await client_detail(update, context)
        return
    
    # Обработка главного меню
    elif current_state == BotState.GROUPS_MENU:
        if any(g["name"] in message_text for g in db.get_groups()):
            await group_detail(update, context)
        elif "➕" in message_text:
            # Создание группы — упрощённо
            await update.message.reply_text("Введите название группы:", parse_mode=HTML)
        elif "⬅️" in message_text:
            context.user_data['state'] = BotState.MAIN_MENU
            await update.message.reply_text("🏠 Главное меню", reply_markup=create_admin_keyboard(), parse_mode=HTML)
        return

    elif current_state == BotState.GROUP_DETAIL_MENU:
        if message_text == "👥 Показать клиентов":
            # Показываем список клиентов
            group = context.user_data.get('selected_group')
            if group:
                clients = db.get_clients_in_group(group['id'])
                if clients:
                    msg = f"📁 <b>{group['name']}</b>\n\n"
                    for c in clients:
                        msg += f"  • {c['name']} — <code>{c['login']}</code>\n"
                else:
                    msg = f"📁 <b>{group['name']}</b>\n\n❌ Нет клиентов"
                await update.message.reply_text(msg, parse_mode=HTML)
            else:
                await group_detail(update, context)
        elif message_text == "➕ Добавить клиента":
            await add_client_to_group_handler(update, context)
        elif message_text == "➖ Удалить клиента":
            await update.message.reply_text("В разработке", parse_mode=HTML)
        elif message_text == "💌 Сообщение группе":
            await send_group_message(update, context)
        elif message_text == "🗑️ Удалить группу":
            await update.message.reply_text("В разработке", parse_mode=HTML)
        elif "⬅️" in message_text:
            await groups_menu(update, context)
        return

    elif current_state == BotState.GROUP_MESSAGE:
        await handle_group_message(update, context)
        return

    elif current_state == BotState.ADD_TO_GROUP:
        await handle_add_to_group(update, context)
        return

    elif current_state == BotState.SETTINGS_MENU:
        if message_text == "🤖 Состояние бота":
            await bot_status(update, context)
        elif message_text == "🔄 Перезагрузить":
            await restart_bot(update, context)
        elif message_text == "📋 Проверить ошибки":
            await check_errors(update, context)
        elif message_text == "🖥️ Мониторинг":
            await server_monitor(update, context)
            return
        elif message_text == "📊 Кэш":
            await show_cache(update, context)
        elif message_text == "🛡️ Маршруты":
            await routing_view(update, context)
        elif message_text == "🗑️ Удалить бэкапы":
            await delete_backups(update, context)
        elif message_text == "📋 Список бэкапов":
            await list_backups(update, context)
        elif message_text == "🔄 Обновление бота":
            await check_bot_update_manual(update, context)
            return
        elif message_text == "💾 Бэкап":
            await create_backup(update, context)
        elif message_text == "🆕 Что нового":
            await show_changelog(update, context)
        elif message_text == "🆕 Что нового":
            await show_changelog(update, context)
        elif message_text == "🔄 Автосброс":
            await auto_reset_status(update, context)
        elif message_text == "🔔 Уведомления":
            await toggle_notifications_handler(update, context)
        elif message_text == "⬅️ Назад в меню":
            context.user_data['state'] = BotState.MAIN_MENU
            await update.message.reply_text(
                "🏠 <b>Главное меню:</b>",
                reply_markup=create_admin_keyboard(),
                parse_mode=HTML
            )
        else:
            await update.message.reply_text("❌ Используйте кнопки меню", parse_mode=HTML)
        return

    elif current_state == BotState.MAIN_MENU:
        is_user_admin = is_admin(user_id)
        is_in_client_mode = context.user_data.get('is_admin_in_client_mode', False)
        
        if is_user_admin and is_in_client_mode:
            if message_text == "💬 Написать админу":
                await write_to_admin(update, context)
                return
            if message_text == "🎁 Бонус":
                await bonus_menu(update, context)
                return
            if message_text == "⚙️ Админ-панель":
                await switch_to_admin_mode(update, context)
                return
            
            user_handlers = {
                "📊 Мои данные": statistics,
                "🔗 Ссылки": link,
                "🔑 Прямые ключи": direct_keys,
                "📱 QR-Код": qr_code,
                "📱 Приложение": app_info,
                "🛡️ Статус VPN": vpn_status,
                "🛡️ Статус VPN": vpn_status,
                "🆔 Мой ID": get_telegram_id,
                
                "🤖 AI Помощник": ai_help,
                "💬 Написать админу": write_to_admin,
            }
            
            if message_text in user_handlers:
                await user_handlers[message_text](update, context)
            else:
                await update.message.reply_text(
                    "❌ <b>Неизвестная команда. Используйте кнопки для навигации.</b>",
                    reply_markup=create_user_keyboard(is_admin=True),
                    parse_mode=HTML
                )
            return
        
        if is_user_admin:
            # Проверяем выбор панели
            if "Финляндия" in message_text or "Россия" in message_text:
                await handle_panel_selection(update, context)
                return
            
            admin_handlers = {
                "📊 Состояние сервера": server_status,
                "💌 Отправить сообщение": send_message,
                "📡 Инбаунды": inbounds,
                "🛡️ Маршруты": routing_view,
                "👥 Все клиенты": all_clients,                
                "👤 Пользователи": users_list,
                "👥 Группы": groups_menu,
                "🌐 Онлайн": online,
                "🔄 Панель": panel_switch,
            "👤 Режим клиента": switch_to_client_mode,
                "⚙️ Настройки": settings_menu,
                "🔔 Уведомления": toggle_notifications_handler,
            }
            
            if message_text in admin_handlers:
                await admin_handlers[message_text](update, context)
            else:
                await update.message.reply_text(
                    "❌ <b>Неизвестная команда. Используйте кнопки для навигации.</b>",
                    reply_markup=create_admin_keyboard(),
                    parse_mode=HTML
                )
        else:
            user_handlers = {
                "📊 Мои данные": statistics,
                "🔗 Ссылки": link,
                "🔑 Прямые ключи": direct_keys,
                "📱 QR-Код": qr_code,
                "📱 Приложение": app_info,
                "🛡️ Статус VPN": vpn_status,
                "🆔 Мой ID": get_telegram_id,
                "🤖 AI Помощник": ai_help,
                
                "💬 Написать админу": write_to_admin,
            }
            
            if message_text in user_handlers:
                await user_handlers[message_text](update, context)
            else:
                await update.message.reply_text(
                    "❌ <b>Неизвестная команда. Используйте кнопки для навигации.</b>",
                    reply_markup=create_user_keyboard(),
                    parse_mode=HTML
                )
    
    else:
        context.user_data.clear()
        context.user_data['state'] = BotState.MAIN_MENU
        
        if is_admin(user_id):
            await update.message.reply_text(
                "🏠 <b>Возврат в главное меню:</b>",
                reply_markup=create_admin_keyboard(),
                parse_mode=HTML
            )
        else:
            await update.message.reply_text(
                "🏠 <b>Возврат в главное меню:</b>",
                reply_markup=create_user_keyboard(),
                parse_mode=HTML
            )
