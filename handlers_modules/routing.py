"""Маршрутизация и инбаунды"""
import json, os, subprocess, requests, re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_inbounds_keyboard, create_clients_keyboard
from xui_api import get_inbounds_list, get_client_url, get_client_ips, get_sub_settings
from server_info import format_traffic
from database import db
from handlers_modules.common import is_admin
HTML = "HTML"

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
    row = []
    for inbound in inbounds:
        clients_count = len(inbound.get('clientStats', []))
        remark = inbound.get('remark', '?').strip()
        row.append(InlineKeyboardButton(
            f"{remark} ({clients_count} клиентов)",
            callback_data=f"inbound_select_{inbound['id']}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
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
        row = []
        for inbound in inbounds:
            clients_count = len(inbound.get('clientStats', []))
            remark = inbound.get('remark', '?').strip()
            row.append(InlineKeyboardButton(
                f"{remark} ({clients_count} клиентов)",
                callback_data=f"inbound_select_{inbound['id']}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

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
                            # Получаем ссылку через API панели
                            from xui_api import get_sub_settings
                            sub_set = get_sub_settings()
                            sub_port = sub_set.get('sub_port', 8543)
                            sub_path = sub_set.get('sub_path', '/sub/')
                            sub_dom = sub_set.get('sub_domain', '') or sub_set.get('web_domain', '')
                            if not sub_dom:
                                import os
                                cp = sub_set.get('cert_path', '')
                                if cp:
                                    pts = os.path.dirname(cp).split('/')
                                    sub_dom = pts[-1] if pts[-1] and '.' in pts[-1] else ''
                            host = sub_dom
                            if not host:
                                try:
                                    # Получаем внешний IPv4 сервера
                                    import subprocess
                                    result = subprocess.run(
                                        "curl -s -4 ifconfig.me 2>/dev/null || curl -s -4 icanhazip.com 2>/dev/null || curl -s -4 ipinfo.io/ip 2>/dev/null",
                                        shell=True, capture_output=True, text=True, timeout=5
                                    )
                                    host = result.stdout.strip()
                                except:
                                    pass
                            if not host:
                                host = '144.31.133.182'
                            sub_link = f"https://{host}:{sub_port}{sub_path}{sub_id}"
                            message += f"🔗 <b>Ссылка:</b> <code>{sub_link}</code>\n"
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

