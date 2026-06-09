# [file name]: panel_manager.py
"""
Менеджер панелей 3x-ui.
Позволяет переключаться между несколькими панелями.
"""

import logging
from typing import Dict, List, Optional
from config import (
    XUI_PANEL_URL, XUI_API_TOKEN, XUI_USERNAME, XUI_PASSWORD, XUI_VERIFY_SSL
)

logger = logging.getLogger(__name__)

# Пробуем загрузить вторую панель
try:
    from config import XUI2_PANEL_URL, XUI2_API_TOKEN, XUI2_VERIFY_SSL
    HAS_PANEL2 = bool(XUI2_PANEL_URL)
except ImportError:
    HAS_PANEL2 = False
    XUI2_PANEL_URL = None
    XUI2_API_TOKEN = None
    XUI2_VERIFY_SSL = True

# Список панелей
PANELS = [
    {
        'id': 1,
        'name': 'Финляндия',
        'url': XUI_PANEL_URL,
        'api_token': XUI_API_TOKEN,
        'verify_ssl': XUI_VERIFY_SSL,
        'emoji': '🇫🇮'
    }
]

# Добавляем вторую панель если есть
if HAS_PANEL2 and XUI2_PANEL_URL:
    PANELS.append({
        'id': 2,
        'name': 'Россия',
        'url': XUI2_PANEL_URL,
        'api_token': XUI2_API_TOKEN,
        'verify_ssl': XUI2_VERIFY_SSL,
        'emoji': '🇷🇺'
    })

# Текущая активная панель (по умолчанию первая)
_active_panel_id = 1

def get_active_panel() -> Dict:
    """Возвращает конфигурацию активной панели"""
    global _active_panel_id
    for panel in PANELS:
        if panel['id'] == _active_panel_id:
            return panel
    return PANELS[0]

def set_active_panel(panel_id: int) -> bool:
    """Переключает активную панель"""
    global _active_panel_id
    for panel in PANELS:
        if panel['id'] == panel_id:
            _active_panel_id = panel_id
            logger.info(f"🔄 Переключение на панель: {panel['name']}")
            # Сбрасываем сессию xui_api для новой панели
            try:
                from xui_api import session
                session.cookies.clear()
                session.headers.clear()
                session.verify = panel.get('verify_ssl', True)
                logger.info(f"   Сессия сброшена, SSL: {session.verify}")
            except Exception as e:
                logger.warning(f"   Не удалось сбросить сессию: {e}")
            return True
    return False

def get_panels_list() -> List[Dict]:
    """Возвращает список всех панелей"""
    return PANELS

def get_panel_name(panel_id: int) -> str:
    """Возвращает название панели по ID"""
    for panel in PANELS:
        if panel['id'] == panel_id:
            return f"{panel['emoji']} {panel['name']}"
    return "Неизвестная панель"

