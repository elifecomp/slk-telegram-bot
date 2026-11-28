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


def _normalize_allowed_ips(val) -> list[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if x is not None and str(x).strip()]
    if isinstance(val, (tuple, set)):
        return [str(x).strip() for x in val if x is not None and str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if x is not None and str(x).strip()]
            except Exception:
                pass
        return [part.strip() for part in s.replace(";", ",").split(",") if part.strip()]
    return []


def _build_clean_client_payload(raw_client: dict, email: str, updates: dict) -> dict:
    """Формирует полный JSON-объект клиента для POST /clients/update/{email}."""
    payload = dict(raw_client) if isinstance(raw_client, dict) else {}
    payload["email"] = email

    for k, v in updates.items():
        payload[k] = v

    payload["allowedIPs"] = _normalize_allowed_ips(payload.get("allowedIPs"))

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



async def add_client_to_inbounds_api(
    email: str,
    inbound_ids: list[int],
    total_gb_bytes: int | None = None,
) -> tuple[list[int], list[str]]:
    """Добавляет клиента (email) в указанные inbound_id через обновление settings инбаунда (/inbounds/update/{id}).
    Возвращает (список_успешно_добавленных_или_уже_присутствующих_id, список_ошибок).
    """
    raw_client, _ = await get_raw_client_and_inbound(email)
    if not raw_client:
        return [], [f"{email}: клиент не найден в панели"]

    client = Panel3XUIClient()
    inbounds_resp = await client.get_api("/inbounds/list")
    if not inbounds_resp.get("success") or not isinstance(inbounds_resp.get("obj"), list):
        return [], ["не удалось получить список инбаундов"]

    by_id: dict[int, dict] = {}
    for ib in inbounds_resp["obj"]:
        if isinstance(ib, dict) and ib.get("id") is not None:
            try:
                by_id[int(ib["id"])] = ib
            except (TypeError, ValueError):
                pass

    added_ids: list[int] = []
    errors: list[str] = []

    for ib_id in inbound_ids:
        ib = by_id.get(int(ib_id))
        if not ib:
            errors.append(f"ID {ib_id}: инбаунд не найден")
            continue

        settings_dict = _parse_json_dict(ib.get("settings"))
        clients_list = settings_dict.get("clients")
        if not isinstance(clients_list, list):
            clients_list = []

        already_exists = any(
            isinstance(c, dict) and str(c.get("email") or "").strip() == email
            for c in clients_list
        )
        if already_exists:
            added_ids.append(int(ib_id))
            continue

        new_client = dict(raw_client)
        new_client["email"] = email
        new_client["enable"] = True
        new_client["allowedIPs"] = _normalize_allowed_ips(new_client.get("allowedIPs"))
        uuid_str = _extract_client_uuid_str(new_client)
        if uuid_str:
            new_client["id"] = uuid_str
        new_client.pop("uuid", None)
        if total_gb_bytes is not None:
            new_client["totalGB"] = int(total_gb_bytes)

        updated_clients = list(clients_list) + [new_client]
        new_settings = dict(settings_dict)
        new_settings["clients"] = updated_clients

        inbound_payload = dict(ib)
        inbound_payload.pop("clientStats", None)
        inbound_payload["settings"] = json.dumps(new_settings, ensure_ascii=False, separators=(",", ":"))
        for json_field in ("streamSettings", "sniffing"):
            val = inbound_payload.get(json_field)
            if isinstance(val, dict):
                inbound_payload[json_field] = json.dumps(val, ensure_ascii=False, separators=(",", ":"))

        status, data = await client.try_post_api(f"/inbounds/update/{int(ib_id)}", inbound_payload)
        if status != 404 and isinstance(data, dict) and data.get("success", False):
            added_ids.append(int(ib_id))
        else:
            msg = str((data or {}).get("msg") or f"HTTP {status}")
            errors.append(f"ID {ib_id}: {msg}")

    return added_ids, errors
