import json
from urllib.parse import quote
from api.panel_client import Panel3XUIClient


def _parse_json_dict(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_client_uuid_str(client_obj: dict) -> str:
    """Возвращает UUID клиента строго в виде строки."""
    for key in ("uuid", "id"):
        val = client_obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if val is not None and not isinstance(val, (dict, list, bool)):
            s = str(val).strip()
            if s and not s.isdigit():
                return s
    raw_id = client_obj.get("id")
    return "" if raw_id is None else str(raw_id)


def _build_clean_client_payload(raw_client: dict, email: str, updates: dict) -> dict:
    """Формирует полный JSON-объект клиента для POST /clients/update/{email}."""
    payload = dict(raw_client) if isinstance(raw_client, dict) else {}
    payload["email"] = email

    for k, v in updates.items():
        payload[k] = v

    uuid_str = _extract_client_uuid_str(payload)
    if uuid_str:
        payload["id"] = uuid_str
    elif "id" in payload:
        payload["id"] = str(payload["id"])

    payload.pop("uuid", None)
    return payload


async def reset_client_traffic_api(email: str) -> tuple[bool, str]:
    client = Panel3XUIClient()
    enc_email = quote(email, safe="")
    status, data = await client.try_post_api(f"/clients/resetTraffic/{enc_email}", {})
    if status == 404 or not isinstance(data, dict):
        return False, "эндпоинт сброса трафика не найден (404)"
    if data.get("success", False):
        return True, data.get("msg") or "трафик сброшен"
    return False, data.get("msg") or "ошибка сброса трафика"


async def get_raw_client_and_inbound(email: str, preferred_inbound_id=None) -> tuple[dict, int | str | None]:
    """Возвращает (словарь_клиента, inbound_id) из /inbounds/list и /clients/get/{email}."""
    client = Panel3XUIClient()
    client_obj: dict = {}
    inbound_id = preferred_inbound_id

    inbounds_resp = await client.get_api("/inbounds/list")
    if inbounds_resp.get("success") and isinstance(inbounds_resp.get("obj"), list):
        for ib in inbounds_resp["obj"]:
            if not isinstance(ib, dict):
                continue
            settings_dict = _parse_json_dict(ib.get("settings"))
            for c in settings_dict.get("clients") or []:
                if isinstance(c, dict) and str(c.get("email") or "").strip() == email:
                    if not client_obj:
                        client_obj = dict(c)
                    if inbound_id is None or str(ib.get("id")) == str(preferred_inbound_id):
                        inbound_id = ib.get("id")
                        client_obj = dict(c)
                    if inbound_id is not None and str(ib.get("id")) == str(preferred_inbound_id):
                        return client_obj, inbound_id

    enc_email = quote(email, safe="")
    status, data = await client.try_get_api(f"/clients/get/{enc_email}")
    if status != 404 and isinstance(data, dict) and data.get("success"):
        obj = data.get("obj")
        if isinstance(obj, dict):
            if isinstance(obj.get("client"), dict):
                for k, v in obj["client"].items():
                    if k == "id":
                        continue
                    client_obj.setdefault(k, v)
                if not client_obj.get("id") and obj["client"].get("uuid"):
                    client_obj["id"] = str(obj["client"]["uuid"])
            inbound_ids = obj.get("inboundIds")
            if inbound_id is None and isinstance(inbound_ids, list) and inbound_ids:
                inbound_id = inbound_ids[0]

    return client_obj, inbound_id


async def update_client_fields_api(
    email: str,
    updates: dict,
    preferred_inbound_id=None,
) -> tuple[bool, str]:
    """Обновляет поля клиента через POST /clients/update/{email}."""
    raw_client, _ = await get_raw_client_and_inbound(email, preferred_inbound_id)
    prepared_client = _build_clean_client_payload(raw_client, email, updates)

    client = Panel3XUIClient()
    enc_email = quote(email, safe="")

    status, data = await client.try_post_api(f"/clients/update/{enc_email}", prepared_client)
    if status == 404 or not isinstance(data, dict):
        return False, "эндпоинт обновления клиента не найден (404)"
    if data.get("success", False):
        return True, data.get("msg") or "обновлено"
    return False, str(data.get("msg") or "ошибка обновления клиента")
