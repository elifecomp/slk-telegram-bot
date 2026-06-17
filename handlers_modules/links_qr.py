"""Ссылки и QR-коды"""
import json, os, subprocess, requests, re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import qrcode
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState, SUBSCRIPTION_URL, SUBSCRIPTION_EXTRA_PATH, SUBSCRIPTION_JSON_PATH
from keyboards import create_admin_keyboard
from xui_api import get_inbounds_list, get_sub_links_new, get_sub_settings
from database import db
from handlers_modules.common import is_admin
import logging
logger = logging.getLogger(__name__)
HTML = "HTML"

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
                                # Формируем ссылку подписки через API панели
                                from xui_api import get_sub_settings
                                sub_set = get_sub_settings()
                                sub_port = sub_set.get('sub_port', 8543)
                                sub_path = sub_set.get('sub_path', '/sub/')
                                sub_domain = sub_set.get('sub_domain', '') or sub_set.get('web_domain', '')
                                if not sub_domain:
                                    import os
                                    cert_path = sub_set.get('cert_path', '')
                                    if cert_path:
                                        parts = os.path.dirname(cert_path).split('/')
                                        sub_domain = parts[-1] if parts[-1] and '.' in parts[-1] else ''
                                if not sub_domain:
                                    import subprocess as sp
                                    try:
                                        r = sp.run("curl -s -4 ifconfig.me 2>/dev/null", shell=True, capture_output=True, text=True, timeout=5)
                                        sub_domain = r.stdout.strip()
                                    except:
                                        pass
                                host = sub_domain if sub_domain else '127.0.0.1'
                                sub_link = f"https://{host}:{sub_port}{sub_path}{sub_id}"
                                return sub_link, sub_id
                                return None, None
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
            from config import BOT_NAME, SUBSCRIPTION_JSON_PATH
            if SUBSCRIPTION_JSON_PATH:
                json_link = ""  # JSON ссылка теперь через API
        except:
            pass

        # Inline-кнопки
        keyboard = []
        if subscription_link:
            keyboard.append([InlineKeyboardButton("📋 Открыть подписку", url=subscription_link)])

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
            from xui_api import _get
            r = _get('/panel/api/clients/list')
            if r.get('success'):
                for c in r.get('obj', []):
                    if c.get('email') == client['login']:
                        return c.get('subId')
            return None
        except:
            return None

    sub_id = get_sub_data()
    if not sub_id:
        await query.edit_message_text("❌ <b>Подписка не найдена</b>", parse_mode=HTML)
        return

    # Получаем настройки из панели
    from xui_api import get_sub_settings
    sub_set = get_sub_settings()
    sub_port = sub_set.get('sub_port', 8543)
    sub_path = sub_set.get('sub_path', '/sub/')
    sub_dom = sub_set.get('sub_domain', '') or sub_set.get('web_domain', '')
    if not sub_dom:
        import os
        cert_path = sub_set.get('cert_path', '')
        if cert_path:
            parts = os.path.dirname(cert_path).split('/')
            sub_dom = parts[-1] if parts[-1] and '.' in parts[-1] else ''
    if not sub_dom:
        import subprocess as sp
        try:
            r = sp.run("curl -s -4 ifconfig.me 2>/dev/null", shell=True, capture_output=True, text=True, timeout=5)
            sub_dom = r.stdout.strip()
        except:
            pass
    host = sub_dom if sub_dom else '127.0.0.1'

    if query.data == "qr_sub":
        link = f"https://{host}:{sub_port}{sub_path}{sub_id}"
        label = "Обычная подписка"
    else:
        link = f"https://{host}:{sub_port}{sub_path}{sub_id}"
        label = "JSON подписка"
        host = sub_dom if sub_dom else '127.0.0.1'
        link = f"https://{host}:{sub_port}{sub_path}{sub_id}"  # JSON
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

