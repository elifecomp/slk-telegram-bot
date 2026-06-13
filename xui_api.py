# [file name]: xui_api.py (оптимизированная версия)
"""API клиент для 3x-ui панели"""

import logging, requests, json, time, re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_VERIFY_SSL

try:
    from traffic_cache import client_traffic_history
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    client_traffic_history = None

logger = logging.getLogger(__name__)

# API Token
import os; from dotenv import load_dotenv; load_dotenv()
XUI_API_TOKEN = os.getenv('XUI_API_TOKEN', '').strip()
USE_API_TOKEN = bool(XUI_API_TOKEN)

# Сессия
session = requests.Session()
session.verify = XUI_VERIFY_SSL
_csrf_token = None
_last_auth_time = None

logger.info(f"🔐 xui_api: {'API TOKEN' if USE_API_TOKEN else 'COOKIE'}, SSL: {XUI_VERIFY_SSL}")

# ==================== УТИЛИТЫ ====================

def _headers() -> dict:
    """Заголовки из активной панели"""
    from panel_manager import get_active_panel
    panel = get_active_panel()
    return {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {panel['api_token']}"
    }

def _url(endpoint: str) -> str:
    """URL из активной панели"""
    from panel_manager import get_active_panel
    panel = get_active_panel()
    session.verify = panel.get('verify_ssl', True)
    return f"{panel['url'].rstrip('/')}{endpoint}"

def _api(method: str, endpoint: str, **kwargs) -> dict:
    """Единый метод для всех API запросов"""
    url = _url(endpoint) if not endpoint.startswith('http') else endpoint
    kwargs.setdefault('headers', _headers())
    kwargs.setdefault('timeout', 15)

    for attempt in range(3):
        try:
            if attempt > 0: time.sleep(attempt * 2)
            r = session.request(method, url, **kwargs)
            if r.status_code == 200:
                try:
                    return r.json()
                except:
                    return {"success": True, "obj": r.text}
            elif r.status_code == 401 and not USE_API_TOKEN:
                login_to_panel()
                kwargs['headers'] = _headers()
                continue
            logger.error(f"API {r.status_code}: {endpoint}")
            return {"success": False, "msg": f"HTTP {r.status_code}"}
        except Exception as e:
            if attempt == 2:
                logger.error(f"Ошибка API: {e}")
                return {"success": False, "msg": str(e)}

def _get(endpoint: str) -> dict:
    return _api('GET', endpoint)

def _post(endpoint: str, data: dict = None) -> dict:
    return _api('POST', endpoint, json=data) if data else _api('POST', endpoint)

# ==================== АУТЕНТИФИКАЦИЯ ====================

def login_to_panel() -> bool:
    global _last_auth_time
    if USE_API_TOKEN: return True
    if _last_auth_time and (datetime.now() - _last_auth_time).seconds < 1800: return True

    try:
        # CSRF
        r = session.get(f"{XUI_PANEL_URL}/", timeout=10)
        csrf = re.search(r'csrf-token"\s+content="([^"]+)"', r.text)

        headers = {'Content-Type': 'application/json'}
        if csrf: headers['X-CSRF-TOKEN'] = csrf.group(1)

        r = session.post(f"{XUI_PANEL_URL}/login",
                        json={'username': XUI_USERNAME, 'password': XUI_PASSWORD},
                        headers=headers, timeout=10)

        if r.status_code in [200, 302]:
            _last_auth_time = datetime.now()
            return True
        return False
    except:
        return False

# ==================== INBOUNDS ====================

def get_inbounds_list() -> list:
    r = _get('/panel/api/inbounds/list')
    return r.get('obj', []) if r.get('success') else []

def get_inbound_by_id(inbound_id: int) -> dict:
    r = _get(f'/panel/api/inbounds/get/{inbound_id}')
    return r.get('obj') if r.get('success') else {}

# ==================== КЛИЕНТЫ ====================

def get_online_clients() -> list:
    r = _post('/panel/api/clients/onlines')
    return r.get('obj', []) if r.get('success') else []

def get_last_online() -> dict:
    r = _post('/panel/api/clients/lastOnline')
    return r.get('obj', {}) if r.get('success') else {}

def get_client_ips(email: str) -> list:
    r = _post(f'/panel/api/clients/ips/{email}')
    if r.get('success'):
        obj = r.get('obj', [])
        if isinstance(obj, list):
            return obj
    return []

def delete_client_by_email(inbound_id: int, email: str) -> bool:
    r = _post(f'/panel/api/inbounds/{inbound_id}/delClientByEmail/{email}')
    return r.get('success', False)

def reset_client_traffic(inbound_id: int, email: str) -> bool:
    r = _post(f'/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}')
    return r.get('success', False)

def get_sub_links(sub_id: str) -> list:
    r = _get(f'/panel/api/inbounds/getSubLinks/{sub_id}')
    return r.get('obj', []) if r.get('success') else []

def get_client_url(inbound_id: int, email: str) -> list:
    r = _get(f'/panel/api/inbounds/getClientUrl/{inbound_id}/{email}')
    return r.get('obj', []) if r.get('success') else []

# ==================== СЕРВЕР ====================

def get_sub_links_new(sub_id: str) -> list:
    """Получает прямые ссылки подписки через новый API (3.2.x)"""
    r = _get(f'/panel/api/clients/subLinks/{sub_id}')
    return r.get('obj', []) if r.get('success') else []



def get_sub_settings() -> dict:
    """Получает настройки подписки из панели (subPort, subPath, subJsonPath, subDomain)"""
    r = _post('/panel/api/setting/all', {})
    if r.get('success'):
        obj = r.get('obj', {})
        return {
            'sub_port': obj.get('subPort', 8543),
            'sub_path': obj.get('subPath', '/sub/'),
            'sub_json_path': obj.get('subJsonPath', '/json/'),
            'sub_domain': obj.get('subDomain', ''),
            'web_domain': obj.get('webDomain', ''),
            'cert_path': obj.get('webCertFile', ''),
        }
    return {}

def get_server_status() -> dict:
    r = _get('/panel/api/server/status')
    return r.get('obj', {}) if r.get('success') else {}

def get_xray_version() -> list:
    r = _get('/panel/api/server/getXrayVersion')
    return r.get('obj', []) if r.get('success') else []

def get_panel_update_info() -> dict:
    r = _get('/panel/api/server/getPanelUpdateInfo')
    return r.get('obj', {}) if r.get('success') else {}

def generate_uuid() -> str:
    import uuid
    r = _get('/panel/api/server/getNewUUID')
    return r.get('obj') if r.get('success') else str(uuid.uuid4())

# ==================== ТРАФИК (КЭШ) ====================

def update_traffic_history(email: str, up: int, down: int) -> bool:
    if not CACHE_AVAILABLE: return False
    now = datetime.now()
    total = up + down
    h = client_traffic_history.get(email)
    if not h:
        client_traffic_history.set(email, {'last_total': total, 'last_update': now, 'last_seen': now, 'is_active': False})
        return False
    changed = total > h.get('last_total', 0)
    h.update({'last_total': total, 'last_update': now, 'last_seen': now, 'is_active': changed})
    client_traffic_history.update(email, **h)
    return changed

def get_client_connection_status(email: str, up: int, down: int) -> bool:
    return update_traffic_history(email, up, down)

def get_client_online_status(email: str, up: int, down: int) -> str:
    return "🟢 Онлайн" if get_client_connection_status(email, up, down) else "🔴 Офлайн"

def get_client_last_seen(email: str) -> str:
    if not CACHE_AVAILABLE: return "Неизвестно"
    h = client_traffic_history.get(email)
    if h and h.get('last_seen'):
        diff = (datetime.now() - h['last_seen']).total_seconds()
        if diff <= 10: return "Только что"
        if diff <= 60: return f"{int(diff)} сек. назад"
        if diff <= 3600: return f"{int(diff/60)} мин. назад"
        return f"{int(diff/3600)} ч. назад"
    return "Никогда"

def get_traffic_cache_stats() -> dict:
    if CACHE_AVAILABLE and hasattr(client_traffic_history, 'get_stats'):
        return client_traffic_history.get_stats()
    return {"error": "Cache not available"}

# ==================== СОВМЕСТИМОСТЬ ====================

def get_panel_info() -> dict:
    inbounds = get_inbounds_list()
    return {'status': 'connected', 'inbounds_count': len(inbounds)} if inbounds else {'status': 'error'}

def get_xray_config() -> dict:
    inbounds = get_inbounds_list()
    clients = sum(len(i.get('clientStats', [])) for i in inbounds)
    return {'status': 'running', 'total_clients': clients, 'total_inbounds': len(inbounds)}

