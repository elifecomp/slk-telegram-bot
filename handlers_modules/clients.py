"""Клиенты — управление и детали"""
import json, os, glob, requests, re, subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_admin_keyboard, create_clients_keyboard, create_client_detail_keyboard
from keyboards import create_delete_confirmation_keyboard
from xui_api import get_inbounds_list, delete_client_by_email, reset_client_traffic, get_client_ips, get_client_url, get_sub_settings
from server_info import format_traffic
from database import db
from handlers_modules.common import is_admin
import logging
logger = logging.getLogger(__name__)
HTML = "HTML"

async def handle_backup_delete(update: Update, context: CallbackContext) -> None:
    """Обрабатывает удаление бэкапов"""
    query = update.callback_query
    await query.answer()
    if query.data == "backup_delete_cancel":
        await query.edit_message_text("❌  <b>Удаление отменено</b>", parse_mode=HTML)
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
            f"✅  <b>Удалено {count} бэкапов!</b>\n\n"
            f"💾 Место освобождено.",
            parse_mode=HTML
        )

async def list_backups(update: Update, context: CallbackContext) -> None:
    """Показывает список бэкапов"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔  <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    import os, glob
    backups = glob.glob('/opt/SLV_Bot/backups/*.tar.gz')
    if not backups:
        await update.message.reply_text("📋 <b>Список бэкапов пуст</b>", parse_mode=HTML)
        return
    msg = "📋 <b>СПИСОК БЭКАПОВ</b>\n\n"
    for i, b in enumerate(sorted(backups, reverse=True), 1):
        name = os.path.basename(b)
        size = os.path.getsize(b)
        size_str = f"{size/1024/1024:.1f} MB" if size > 1024*1024 else f"{size/1024:.1f} KB"
        msg += f"{i}. {name} ({size_str})\n"
    await update.message.reply_text(msg, parse_mode=HTML)

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

# ==================== АДМИНСКИЕ ФУНКЦИИ ДЛЯ ОТПРАВКИ СООБЩЕНИЙ ====================
