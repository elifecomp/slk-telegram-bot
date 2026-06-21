HTML = "HTML"
"""Работа с группами клиентов"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_groups_keyboard, create_group_actions_keyboard, create_admin_keyboard, create_cancel_keyboard
from database import db
from handlers_modules.common import is_admin

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
    
    # Отправляем уведомление в приложение
    try:
        import requests
        requests.post("http://144.31.133.182:8000/api/notify", 
            json={"text": message_text, "group": group['name']}, timeout=5)
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

