from api.panel_client import Panel3XUIClient

NODE_GET_ENDPOINTS = [
    "/nodes/list",
    "/nodes",
    "/node/list",
    "/nodes/status",
    "/nodes/stats",
]

NODE_POST_ENDPOINTS = [
    "/nodes/list",
    "/nodes",
    "/node/list",
    "/nodes/status",
    "/nodes/stats",
]


def _extract_nodes_list(data: dict) -> list[dict]:
    """Нормализует список узлов из ответа панели."""
    obj = data.get("obj")
    if not obj:
        return []
    if isinstance(obj, list):
        return [item if isinstance(item, dict) else {"name": str(item)} for item in obj]
    if isinstance(obj, dict):
        for key in ("nodes", "list", "items", "data"):
            val = obj.get(key)
            if isinstance(val, list):
                return [item if isinstance(item, dict) else {"name": str(item)} for item in val]
        # Если словарь вида {id: {...}}
        items = []
        for k, v in obj.items():
            if isinstance(v, dict):
                entry = dict(v)
                entry.setdefault("id", k)
                items.append(entry)
        return items
    return []


async def fetch_nodes() -> tuple[bool, list[dict], str]:
    """Возвращает (успех, список_узлов, источник_или_ошибка)."""
    client = Panel3XUIClient()

    for endpoint in NODE_GET_ENDPOINTS:
        status, data = await client.try_get_api(endpoint)
        if status == 404 or data is None:
            continue
        if not data.get("success", True):
            return False, [], data.get("msg") or f"ошибка на GET {endpoint}"
        nodes = _extract_nodes_list(data)
        if nodes or "obj" in data:
            return True, nodes, f"GET {endpoint}"

    for endpoint in NODE_POST_ENDPOINTS:
        status, data = await client.try_post_api(endpoint)
        if status == 404 or data is None:
            continue
        if not data.get("success", True):
            return False, [], data.get("msg") or f"ошибка на POST {endpoint}"
        nodes = _extract_nodes_list(data)
        if nodes or "obj" in data:
            return True, nodes, f"POST {endpoint}"

    return False, [], "не найден API-эндпоинт для узлов (404)"
