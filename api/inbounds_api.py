from api.panel_client import Panel3XUIClient

INBOUND_GET_ENDPOINTS = [
    "/inbounds/list",
    "/inbounds/list/slim",
    "/inbounds",
]


def _extract_inbounds_list(data: dict) -> list[dict]:
    """Нормализует список inbound'ов из ответа панели."""
    obj = data.get("obj")
    if not obj:
        return []
    if isinstance(obj, list):
        return [item for item in obj if isinstance(item, dict)]
    if isinstance(obj, dict):
        for key in ("inbounds", "list", "items", "data"):
            val = obj.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
    return []


async def fetch_inbounds() -> tuple[bool, list[dict], str]:
    """Возвращает (успех, список_инбаундов, источник_или_ошибка)."""
    client = Panel3XUIClient()

    for endpoint in INBOUND_GET_ENDPOINTS:
        status, data = await client.try_get_api(endpoint)
        if status == 404 or data is None:
            continue
        if not data.get("success", True):
            return False, [], data.get("msg") or f"ошибка на GET {endpoint}"
        inbounds = _extract_inbounds_list(data)
        if inbounds or "obj" in data:
            return True, inbounds, f"GET {endpoint}"

    return False, [], "не найден эндпоинт инбаундов (404)"
