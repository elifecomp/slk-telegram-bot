from urllib.parse import quote
from api.panel_client import Panel3XUIClient


async def fetch_client_profile(email: str) -> dict:
    """Возвращает объект ответа /clients/get/{email} или пустой словарь."""
    client = Panel3XUIClient()
    enc_email = quote(email, safe="")
    status, data = await client.try_get_api(f"/clients/get/{enc_email}")
    if status == 404 or not isinstance(data, dict):
        return {}
    if not data.get("success", True):
        return {}
    obj = data.get("obj")
    return obj if isinstance(obj, dict) else {}


async def fetch_client_hwids_post(email: str) -> list[dict]:
    """Запрашивает список HWID-устройств клиента через POST /clients/hwids/{email}."""
    client = Panel3XUIClient()
    enc_email = quote(email, safe="")
    status, data = await client.try_post_api(f"/clients/hwids/{enc_email}", {})
    if status == 404 or not isinstance(data, dict):
        return []
    if not data.get("success", True):
        return []
    obj = data.get("obj")
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    return []
