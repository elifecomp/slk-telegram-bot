"""Пользователи — CRUD"""
import logging
import re
logger = logging.getLogger(__name__)
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_admin_keyboard, create_users_list_keyboard, create_user_actions_keyboard
from keyboards import create_edit_confirmation_keyboard, create_cancel_keyboard
from database import db
from operators import get_operator
from handlers_modules.common import is_admin
from handlers_modules.clients import get_zodiac
HTML = "HTML"

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
        message += "🔍 <b>Выберите пользователя или нажмите ➕ для добавления:</b>"

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
async def add_user_start(update: Update, context: CallbackContext) -> None:
    """Начало добавления нового пользователя"""
    if not is_admin(update.effective_user.id):
        return
    context.user_data['adding_user'] = {'step': 'login'}
    await update.message.reply_text(
        "➕ <b>ДОБАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Шаг 1/4: Введите <b>логин</b> пользователя:",
        parse_mode='HTML'
    )

async def handle_add_user_input(update: Update, context: CallbackContext) -> None:
    """Обрабатывает ввод данных при добавлении пользователя"""
    if not is_admin(update.effective_user.id):
        return

    adding = context.user_data.get('adding_user')
    if not adding:
        return

    text = update.message.text.strip()

    if text == "❌ Отмена":
        context.user_data.pop('adding_user', None)
        await update.message.reply_text("❌ Добавление отменено", parse_mode='HTML')
        await users_list(update, context)
        return

    step = adding.get('step')

    if step == 'login':
        adding['login'] = text
        adding['step'] = 'name'
        await update.message.reply_text(
            f"✅ Логин: <b>{text}</b>\n\n"
            "Шаг 2/3: Введите <b>имя</b> пользователя:",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
            parse_mode='HTML'
        )
    elif step == 'name':
        adding['name'] = text
        adding['step'] = 'phone'
        await update.message.reply_text(
            f"✅ Имя: <b>{text}</b>\n\n"
            "Шаг 3/3: Введите <b>номер телефона</b>:",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
            parse_mode='HTML'
        )
    elif step == 'phone':
        adding['phone'] = text
        adding['step'] = 'tg_id'
        await update.message.reply_text(
            f"✅ Телефон: <b>{text}</b>\n\n"
            "Шаг 4/4: Введите <b>Telegram ID</b> (или 0 если нет):",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
            parse_mode='HTML'
        )
    elif step == 'tg_id':
        try:
            tg_id = int(text)
        except:
            tg_id = 0
        adding['tg_id'] = tg_id

        from database import db
        success = db.add_client(tg_id, adding['login'], adding['phone'], adding['name'])

        if success:
            await update.message.reply_text(
                f"✅ <b>ПОЛЬЗОВАТЕЛЬ ДОБАВЛЕН!</b>\n\n"
                f"👤 Логин: {adding['login']}\n"
                f"📝 Имя: {adding['name']}\n"
                f"📱 Телефон: {adding['phone']}\n"
                f"🆔 Telegram ID: {tg_id}",
                reply_markup=create_admin_keyboard(),
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка при добавлении пользователя",
                reply_markup=create_admin_keyboard(),
                parse_mode='HTML'
            )

        context.user_data.pop('adding_user', None)
        context.user_data['state'] = BotState.MAIN_MENU

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
# ==================== ФУНКЦИИ ДЛЯ ОНЛАЙН КЛИЕНТОВ ====================

