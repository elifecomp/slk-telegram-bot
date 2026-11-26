from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton(text="Статус"),
            KeyboardButton(text="Онлайн"),
        ],
        [
            KeyboardButton(text="Инбаунд"),
            KeyboardButton(text="Узлы"),
        ],
        [
            KeyboardButton(text="Клиенты"),
            KeyboardButton(text="👥 Пользователи"),
        ],
        [
            KeyboardButton(text="Хосты"),
            KeyboardButton(text="👤 Панель клиента"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел...",
    )
