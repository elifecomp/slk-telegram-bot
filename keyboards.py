# [file name]: keyboards.py
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from config import PERSONAL_CABINET_URL
from database import db

def create_admin_keyboard():
    """Создает клавиатуру для администратора"""
    keyboard = [
        ["🌐 Онлайн", "📊 Состояние сервера"],
        ["📡 Инбаунды", "👥 Все клиенты"],
        ["👤 Пользователи", "👥 Группы"],
        ["💌 Отправить сообщение", "🔄 Панель"],
        ["⚙️ Настройки", "🔔 Уведомления"],
        ["👤 Режим клиента"],

    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_user_keyboard(user_id=None, is_admin=False):
    """
    Создает клавиатуру для обычного пользователя.
    Если is_admin=True, добавляется кнопка возврата в админ-панель.
    """
    keyboard = [
        ["📊 Мои данные", "🔗 Ссылки"],
        ["📱 QR-Код", "📱 Моё приложение"],
        ["🛡️ Статус VPN"],
        ["💬 Написать админу", "🤖 AI Помощник"]
    ]
    if is_admin:
        keyboard.append(["⚙️ Админ-панель"])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_app_links_keyboard():
    """Создает inline-клавиатуру со ссылками на приложения для Android"""
    keyboard = [
        [InlineKeyboardButton("📱 ОТКРЫТЬ В GOOGLE PLAY", url="https://play.google.com/store/apps/details?id=com.v2raytun.android")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_iphone_links_keyboard():
    """Создает inline-клавиатуру со ссылками на приложения для iPhone"""
    keyboard = [
        [InlineKeyboardButton("🍎 ОТКРЫТЬ В APP STORE", url="https://apps.apple.com/app/v2raytun/id6476628951")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_cancel_keyboard():
    keyboard = [["❌ Отменить"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_delete_confirmation_keyboard():
    """Клавиатура для подтверждения удаления клиента"""
    keyboard = [["✅ Подтвердить", "❌ Отменить"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_users_for_message_keyboard(users):
    keyboard = []
    row = []
    for user in users:
        user_button = f"👤 {user['name']} ({user['login']})"
        row.append(user_button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(["❌ Отменить"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_inbounds_keyboard(inbounds_list):
    keyboard = []
    row = []
    for inbound in inbounds_list:
        remark = inbound.get('remark', 'Без названия')
        if len(row) < 2:
            row.append(remark)
        else:
            keyboard.append(row)
            row = [remark]
    if row:
        keyboard.append(row)
    keyboard.append(["⬅️ Назад в меню"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_clients_keyboard(clients):
    keyboard = []
    row = []
    for client in clients:
        email = client.get('email', 'Без email')
        if len(row) < 2:
            row.append(email)
        else:
            keyboard.append(row)
            row = [email]
    if row:
        keyboard.append(row)
    keyboard.append(["⬅️ Назад"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_client_detail_keyboard():
    keyboard = [
        ["🔄 Обновить клиента", "🗑️ Удалить клиента"],
        ["📊 Сбросить трафик", "🌍 IP адреса"],
        ["🆔 Привязать TG", "⬅️ Назад к клиентам"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_users_list_keyboard(users):
    keyboard = []
    row = []
    for user in users:
        user_button = f"👤 {user['name']} ({user['login']})"
        row.append(user_button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(["➕ Добавить пользователя"])
    keyboard.append(["⬅️ Назад в меню"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_user_actions_keyboard():
    keyboard = [
        ["✏️ Редактировать логин", "📞 Редактировать телефон"],
        ["🎂 День рождения", "🏙️ Город"],
        ["📱 HWID"],
        ["👤 Редактировать имя", "🔒 Блокировать/Разблокировать"],
        ["🗑️ Удалить пользователя", "⬅️ Назад к списку"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_edit_confirmation_keyboard():
    keyboard = [["✅ Подтвердить", "❌ Отменить"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def create_panel_switch_keyboard():
    """Клавиатура для выбора панели"""
    from panel_manager import get_panels_list, _active_panel_id
    panels = get_panels_list()
    keyboard = []
    for panel in panels:
        name = panel['name']
        active = " ✅" if panel['id'] == _active_panel_id else ""
        keyboard.append([f"{panel['emoji']} {name}{active}"])
    keyboard.append(["⬅️ Назад в меню"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def create_settings_keyboard():
    """Клавиатура настроек бота"""
    keyboard = [
        ["🔄 Перезагрузить", "🔄 Обновить бота"],
        ["🔄 Автосброс", "🖥️ Мониторинг"],
        ["📰 SLK News", "📰 3x-ui News"],
        ["🔗 Узлы", "🚀 Скорость сервера"],
        ["⬅️ Назад в меню"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_groups_keyboard(groups):
    """Клавиатура со списком групп"""
    keyboard = []
    row = []
    for g in groups:
        count = len(db.get_clients_in_group(g['id']))
        row.append(f"📁 {g['name']} ({count})")
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(["➕ Создать группу", "🗑 Удалить группу"])
    keyboard.append(["⬅️ Назад в меню"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_group_actions_keyboard():
    """Клавиатура действий с группой"""
    keyboard = [
        ["👥 Показать клиентов", "➕ Добавить клиента"],
        ["➖ Удалить клиента", "💌 Сообщение группе"],
        ["⬅️ Назад к группам"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
