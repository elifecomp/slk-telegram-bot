"""Онлайн и статистика"""
import json, requests, re, subprocess, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import qrcode
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState, SUBSCRIPTION_URL, SUBSCRIPTION_EXTRA_PATH, SUBSCRIPTION_JSON_PATH
from keyboards import create_admin_keyboard
from xui_api import get_inbounds_list, get_online_clients, get_last_online, get_client_ips, get_client_url
from xui_api import get_sub_settings
from server_info import format_traffic
from database import db
from panel_manager import get_active_panel, get_panel_name, get_panels_list, set_active_panel
from operators import get_operator
from handlers_modules.common import is_admin
import logging
logger = logging.getLogger(__name__)
HTML = "HTML"

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

