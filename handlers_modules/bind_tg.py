"""Привязка Telegram ID"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_admin_keyboard, create_clients_keyboard
from database import db
from xui_api import get_inbounds_list
from handlers_modules.common import is_admin
HTML = "HTML"

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