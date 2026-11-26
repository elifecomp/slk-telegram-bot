from urllib.parse import quote
from api.client_detail_api import fetch_client_hwids_post
from api.panel_client import Panel3XUIClient


def _extract_devices(data: dict | None) -> list[dict]:
    if not isinstance(data, dict):
        return []
    obj = data.get("obj")
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for key in ("devices", "list", "items", "hwids", "data"):
            val = obj.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


async def fetch_client_hwid_devices(
    email: str,
    uuid_or_id: str | None = None,
    sub_id: str | None = None,
) -> tuple[list[dict], str | None]:
    """Получает список устройств HWID клиента (приоритет — POST /clients/hwids/{email})."""
    post_devices = await fetch_client_hwids_post(email)
    if post_devices:
        return post_devices, "POST /clients/hwids/{email}"

    client = Panel3XUIClient()
    enc_email = quote(email, safe="")
    candidates_get: list[str] = [
        f"/clients/hwid/{enc_email}",
        f"/clients/{enc_email}/hwid",
        f"/hwid/devices/{enc_email}",
        f"/hwid/{enc_email}",
    ]
    if uuid_or_id:
        enc_id = quote(str(uuid_or_id), safe="")
        candidates_get.extend([
            f"/clients/hwid/{enc_id}",
            f"/hwid/devices/{enc_id}",
        ])
    if sub_id:
        enc_sub = quote(str(sub_id), safe="")
        candidates_get.append(f"/hwid/sub/{enc_sub}")

    for ep in candidates_get:
        status, data = await client.try_get_api(ep)
        if status == 404 or data is None:
            continue
        if data.get("success", True):
            devices = _extract_devices(data)
            if devices:
                return devices, f"GET {ep}"

    return [], None
