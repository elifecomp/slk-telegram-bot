from html import escape
from urllib.parse import quote
from api.clients_manage_api import (
    get_raw_client_and_inbound,
    reset_client_traffic_api,
    update_client_fields_api,
)
from api.hwid_api import fetch_client_hwid_devices
from api.panel_client import Panel3XUIClient
from services.format_bytes import format_bytes
from services.hwid_formatter import format_hwid_devices_block


async def _fetch_client_traffic_counters(email: str, preferred_inbound_id=None) -> tuple[float, float, float | None]:
    """Возвращает (up_bytes, down_bytes, profile_used_traffic)."""
    client = Panel3XUIClient()
    up_val: float | None = None
    down_val: float | None = None
    profile_used: float | None = None

    inbounds_resp = await client.get_api("/inbounds/list")
    if inbounds_resp.get("success") and isinstance(inbounds_resp.get("obj"), list):
        fallback_up: float | None = None
        fallback_down: float | None = None

        for ib in inbounds_resp["obj"]:
            if not isinstance(ib, dict):
                continue
            for st in ib.get("clientStats") or []:
                if isinstance(st, dict) and str(st.get("email") or "").strip() == email:
                    st_up = float(st.get("up") or 0)
                    st_down = float(st.get("down") or 0)
                    if preferred_inbound_id is not None and str(ib.get("id")) == str(preferred_inbound_id):
                        up_val = st_up
                        down_val = st_down
                    if fallback_up is None or (st_up + st_down) > ((fallback_up or 0) + (fallback_down or 0)):
                        fallback_up = st_up
                        fallback_down = st_down

        if up_val is None and fallback_up is not None:
            up_val = fallback_up
            down_val = fallback_down

    enc_email = quote(email, safe="")
    status, data = await client.try_get_api(f"/clients/get/{enc_email}")
    if status != 404 and isinstance(data, dict) and data.get("success"):
        obj = data.get("obj")
        if isinstance(obj, dict) and obj.get("usedTraffic") is not None:
            try:
                profile_used = float(obj.get("usedTraffic") or 0)
            except (TypeError, ValueError):
                profile_used = None

    return float(up_val or 0), float(down_val or 0), profile_used


async def get_managed_client_card(email: str, preferred_inbound_id=None) -> str:
    client_obj, inbound_id = await get_raw_client_and_inbound(email, preferred_inbound_id)
    up_bytes, down_bytes, profile_used = await _fetch_client_traffic_counters(
        email, preferred_inbound_id=inbound_id if inbound_id is not None else preferred_inbound_id
    )

    enabled = client_obj.get("enable", True) is not False
    status_str = "🟢 Включён" if enabled else "🔴 Отключён"

    stat_sum = up_bytes + down_bytes
    if stat_sum > 0:
        used_total = stat_sum
    elif profile_used is not None and profile_used > 0:
        used_total = profile_used
    else:
        used_total = 0.0

    total_gb_raw = client_obj.get("totalGB", 0)
    try:
        limit_bytes = float(total_gb_raw or 0)
    except (TypeError, ValueError):
        limit_bytes = 0.0

    if limit_bytes > 0:
        limit_str = f"{format_bytes(used_total)} / {format_bytes(limit_bytes)}"
        remain_str = format_bytes(max(0.0, limit_bytes - used_total))
    else:
        limit_str = f"{format_bytes(used_total)} / безлимит"
        remain_str = "∞"

    uuid_val = client_obj.get("uuid") or client_obj.get("id") or "—"
    sub_id = client_obj.get("subId") or "—"
    limit_hwid = client_obj.get("limitHwid")
    hwid_str = "∞" if limit_hwid in (None, "", 0, "0") else str(limit_hwid)
    comment = str(client_obj.get("comment") or "").strip()

    devices, _ = await fetch_client_hwid_devices(
        email=email,
        uuid_or_id=str(uuid_val) if uuid_val != "—" else None,
        sub_id=str(sub_id) if sub_id != "—" else None,
    )

    lines = [
        f"👤 <b>КЛИЕНТ: {escape(email)}</b>",
        "────────────────────",
        f"• Статус: <b>{status_str}</b>",
        f"• Инбаунд ID: <code>{escape(str(inbound_id if inbound_id is not None else '—'))}</code>",
    ]
    if comment:
        lines.append(f"• Комментарий: <b>{escape(comment)}</b>")

    lines.extend([
        "────────────────────",
        f"• Трафик: ↑ <code>{format_bytes(up_bytes)}</code> / ↓ <code>{format_bytes(down_bytes)}</code>",
        f"• Использовано / лимит: <code>{escape(limit_str)}</code>",
        f"• Остаток: <code>{escape(remain_str)}</code>",
        "────────────────────",
        f"• <b>Лимит HWID:</b> <code>{escape(hwid_str)}</code>  |  <b>Устройств:</b> <code>{len(devices)}</code>",
        format_hwid_devices_block(devices),
        "────────────────────",
        f"• UUID: <code>{escape(str(uuid_val))}</code>",
        f"• SubID: <code>{escape(str(sub_id))}</code>",
    ])
    return "\n".join(lines)


async def apply_reset_traffic(email: str) -> tuple[bool, str]:
    return await reset_client_traffic_api(email)


async def apply_set_enabled(email: str, enabled: bool, preferred_inbound_id=None) -> tuple[bool, str]:
    return await update_client_fields_api(email, {"enable": enabled}, preferred_inbound_id)


async def apply_rename_client(email: str, new_email: str, preferred_inbound_id=None) -> tuple[bool, str]:
    clean_new = new_email.strip()
    if not clean_new:
        return False, "имя клиента не может быть пустым"
    return await update_client_fields_api(email, {"email": clean_new}, preferred_inbound_id)


async def apply_set_limit_gb(email: str, gb_value: float, preferred_inbound_id=None) -> tuple[bool, str]:
    if gb_value < 0:
        return False, "лимит ГБ не может быть отрицательным"
    total_bytes = int(round(gb_value * (1024**3)))
    return await update_client_fields_api(email, {"totalGB": total_bytes}, preferred_inbound_id)
