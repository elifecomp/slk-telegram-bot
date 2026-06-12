# [file name]: config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота из .env
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []

# Настройки 3x-ui панели
XUI_PANEL_URL = os.getenv('XUI_PANEL_URL', 'http://xxxxxxxx')
XUI_USERNAME = os.getenv('XUI_USERNAME', 'xxxxx')
XUI_PASSWORD = os.getenv('XUI_PASSWORD', 'xxxxxx.')

# Настройки SSL проверки
# Установите в True, если используете валидный SSL-сертификат (например, Let's Encrypt)
# Оставьте False, если используете самоподписанный сертификат или IP-адрес
XUI_VERIFY_SSL = os.getenv('XUI_VERIFY_SSL', 'False').lower() in ('true', '1', 't')

# URL для подписок
SUBSCRIPTION_URL = os.getenv('SUBSCRIPTION_URL', 'xxxxxxxxxxx')
SUBSCRIPTION_EXTRA_PATH = os.getenv('SUBSCRIPTION_EXTRA_PATH', 'finlyandiya2026elifecomp')

# Путь к аудиофайлу
WELCOME_AUDIO_PATH = os.getenv('WELCOME_AUDIO_PATH', 'welcome.mp3')

# Настройки LRU-кэша для истории трафика
TRAFFIC_CACHE_MAX_SIZE = int(os.getenv('TRAFFIC_CACHE_MAX_SIZE', 10000))
TRAFFIC_CACHE_MAX_AGE_HOURS = int(os.getenv('TRAFFIC_CACHE_MAX_AGE_HOURS', 24))
TRAFFIC_CACHE_CLEANUP_INTERVAL = int(os.getenv('TRAFFIC_CACHE_CLEANUP_INTERVAL', 3600))

# URL для личного кабинета
PERSONAL_CABINET_URL = os.getenv('PERSONAL_CABINET_URL', 'http://elifecomp.ru:8080/login')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")

# Состояния бота
class BotState:
    MAIN_MENU = 0
    INBOUNDS_MENU = 1
    ALL_CLIENTS_MENU = 2
    CLIENTS_MENU = 3
    CLIENT_DETAIL_MENU = 4
    REGISTRATION_LOGIN = 10
    REGISTRATION_PHONE = 11
    REGISTRATION_NAME = 12
    USERS_LIST_MENU = 20
    USER_DETAIL_MENU = 21
    USER_EDIT_LOGIN = 22
    USER_EDIT_PHONE = 23
    USER_EDIT_NAME = 24
    USER_EDIT_BIRTHDAY = 27
    USER_EDIT_HWID = 28
    USER_EDIT_CITY = 29
    USER_EDIT_LOGIN2 = 26
    USER_CONFIRM_DELETE = 25
    WRITING_TO_ADMIN = 30
    ADMIN_CHOOSE_USER = 40
    ADMIN_WRITE_MESSAGE = 41
    BIND_TG_ID = 51
    SETTINGS_MENU = 50
    GROUPS_MENU = 52
    GROUP_DETAIL_MENU = 53
    ADD_TO_GROUP = 54
    GROUP_MESSAGE = 55
# API токены для панелей
XUI_API_TOKEN = os.getenv('XUI_API_TOKEN', '')
XUI2_PANEL_URL = os.getenv('XUI2_PANEL_URL', '')
XUI2_API_TOKEN = os.getenv('XUI2_API_TOKEN', '')
XUI2_VERIFY_SSL = os.getenv('XUI2_VERIFY_SSL', 'False').lower() in ('true', '1', 't')
SUBSCRIPTION_JSON_PATH = os.getenv("SUBSCRIPTION_JSON_PATH", "")
BOT_NAME = os.getenv("BOT_NAME", "SLK Bot")
