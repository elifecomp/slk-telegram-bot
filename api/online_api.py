from api.panel_client import Panel3XUIClient

ONLINE_ENDPOINTS = [
    "/inbounds/onlines",
    "/clients/onlines",
    "/server/onlines",
]


def extract_online_names(data: dict) -> list[str]:
    """Нормализует список онлайн-клиентов из ответа панели."""
    obj = data.get("obj")
    if not obj:
        return []
    if isinstance(obj, list):
        names: list[str] = []
        for item in obj:
            if isinstance(item, dict):
                val = item.get("email") or item.get("name") or item.get("remark")
                if val:
                    names.append(str(val).strip())
            else:
                s = str(item).strip()
                if s:
                    names.append(s)
        return names
    if isinstance(obj, dict):
        names = []
        for v in obj.values():
            if isinstance(v, list):
                names.extend(str(x).strip() for x in v if str(x).strip())
            elif v:
                names.append(str(v).strip())
        return names
    return []


async def fetch_online_clients() -> tuple[bool, list[str], str]:
    """Возвращает (успех, список_имен, источник_или_ошибка)."""
    client = Panel3XUIClient()

    for endpoint in ONLINE_ENDPOINTS:
        status, data = await client.try_post_api(endpoint)
        if status == 404 or data is None:
            continue
        if not data.get("success", False):
            return False, [], data.get("msg") or f"ошибка на {endpoint}"
        return True, extract_online_names(data), endpoint

    # Резервная проверка через /inbounds/list, если отдельный эндпоинт онлайн-клиентов переименован
    inbounds_data = await client.get_api("/inbounds/list")
    if not inbounds_data.get("success", False):
        return False, [], "не найден эндпоинт онлайн-клиентов (404)"

    found_online: list[str] = []
    for inbound in inbounds_data.get("obj") or []:
        for stat in inbound.get("clientStats") or []:
            if stat.get("online") is True:
                email = stat.get("email")
                if email:
                    found_online.append(str(email).strip())

    return True, found_online, "/inbounds/list (clientStats.online)"
