import json
from datetime import datetime, timezone
from html import escape
from api.client_detail_api import fetch_client_profile
from api.hwid_api import fetch_client_hwid_devices
from api.panel_client import Panel3XUIClient
from services.format_bytes import format_bytes
from services.hwid_formatter import format_hwid_devices_block
from services.online_cache import OnlineClientEntry


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


def _format_expiry(expiry_val) -> str:
    if expiry_val in (None, "", 0, "0"):
        return "бессрочно"
    try:
        ts = int(expiry_val)
        if ts <= 0:
            return "бессрочно"
        if ts > 10**11:
            ts //= 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return str(expiry_val)


def _pick_first(sources: list[dict], keys: tuple[str, ...]):
    for src in sources:
        if not isinstance(src, dict):
            continue
        for k in keys:
            val = src.get(k)
            if val not in (None, "", [], {}):
                return val
    return None


async def get_online_client_detail_report(entry: OnlineClientEntry) -> str:
    client = Panel3XUIClient()
    inbounds_resp = await client.get_api("/inbounds/list")
    profile_obj = await fetch_client_profile(entry.email)
    profile_client = profile_obj.get("client") if isinstance(profile_obj.get("client"), dict) else {}

    matched_inbound: dict | None = None
    matched_stat: dict = {}
    matched_cfg: dict = {}
    linked_inbounds: list[str] = []

    if inbounds_resp.get("success") and isinstance(inbounds_resp.get("obj"), list):
        for inbound in inbounds_resp["obj"]:
            if not isinstance(inbound, dict):
                continue

            stats_list = inbound.get("clientStats") or []
            stat_by_email = None
            if isinstance(stats_list, list):
                for st in stats_list:
                    if isinstance(st, dict) and str(st.get("email", "")).strip() == entry.email:
                        stat_by_email = st
                        break

            settings_dict = _parse_json_dict(inbound.get("settings"))
            clients_list = settings_dict.get("clients") or []
            cfg_by_email = None
            if isinstance(clients_list, list):
                for c in clients_list:
                    if isinstance(c, dict) and str(c.get("email", "")).strip() == entry.email:
                        cfg_by_email = c
                        break

            if stat_by_email is not None or cfg_by_email is not None:
                rem = str(inbound.get("remark") or f"#{inbound.get('id')}").strip()
                if rem not in linked_inbounds:
                    linked_inbounds.append(rem)

                if matched_inbound is None or (
                    entry.inbound_id is not None and str(inbound.get("id")) == str(entry.inbound_id)
                ):
                    matched_inbound = inbound
                    matched_stat = stat_by_email or {}
                    matched_cfg = cfg_by_email or {}

    sources = [profile_client, matched_stat, matched_cfg]
    email_esc = escape(entry.email)
    inbound_remark = escape(
        str(
            (matched_inbound or {}).get("remark")
            or entry.inbound_remark
            or "не определён"
        )
    )
    inbound_id = escape(str((matched_inbound or {}).get("id") or entry.inbound_id or "—"))
    protocol = escape(
        str((matched_inbound or {}).get("protocol") or entry.protocol or "—").upper()
    )
    port = escape(str((matched_inbound or {}).get("port") or entry.port or "—"))

    enabled_val = _pick_first(sources, ("enable",))
    client_status = "🟢 Включено" if enabled_val is not False else "🔴 Выключено"

    up_bytes = matched_stat.get("up", 0)
    down_bytes = matched_stat.get("down", 0)

    total_bytes = _pick_first([profile_obj, matched_stat, profile_client], ("totalGB", "total"))
    try:
        used_sum = float(up_bytes or 0) + float(down_bytes or 0)
    except (TypeError, ValueError):
        used_sum = 0.0

    try:
        limit_num = float(total_bytes or 0)
    except (TypeError, ValueError):
        limit_num = 0.0

    if limit_num > 0:
        remain_bytes = max(0.0, limit_num - used_sum)
        limit_str = f"{format_bytes(used_sum)} / {format_bytes(limit_num)}"
        remain_str = format_bytes(remain_bytes)
    else:
        limit_str = f"{format_bytes(used_sum)} / безлимит"
        remain_str = "∞"

    expiry_raw = _pick_first(sources, ("expiryTime", "expiry_time"))
    expiry_str = escape(_format_expiry(expiry_raw))

    client_uuid = _pick_first(sources, ("uuid", "id", "password")) or "—"
    sub_id = _pick_first(sources, ("subId", "sub_id")) or "—"
    flow = _pick_first(sources, ("flow",))
    limit_ip = _pick_first(sources, ("limitIp", "limit_ip"))
    hwid_limit = _pick_first(sources, ("limitHwid", "hwidLimit", "hwid_limit", "maxHwid", "max_hwid"))
    comment_val = _pick_first(sources, ("comment", "note", "description", "remark"))
    hwid_raw = _pick_first(
        sources,
        ("hwid", "HWID", "hwidList", "hwids", "deviceId", "device_id", "fingerprint"),
    )

    devices, _ = await fetch_client_hwid_devices(
        email=entry.email,
        uuid_or_id=str(client_uuid) if client_uuid != "—" else None,
        sub_id=str(sub_id) if sub_id != "—" else None,
    )

    hwid_limit_display = "∞" if hwid_limit in (None, "", 0, "0") else str(hwid_limit)
    hwid_count_display = str(len(devices))

    lines = [
        f"👤 <b>КАРТОЧКА КЛИЕНТА: {email_esc}</b>",
        "────────────────────",
        f"• Статус: <b>{client_status}</b> (🟢 в сети)",
        f"• Инбаунд: <b>{inbound_remark}</b> <code>#{inbound_id}</code>",
        f"• Протокол / порт: <code>{protocol}</code> • <code>{port}</code>",
    ]

    if len(linked_inbounds) > 1:
        linked_str = ", ".join(escape(x) for x in linked_inbounds)
        lines.append(f"• Привязанные входящие: <b>{linked_str}</b>")

    if comment_val and str(comment_val).strip() != entry.email:
        lines.append(f"• Комментарий: <b>{escape(str(comment_val).strip())}</b>")

    lines.extend([
        "────────────────────",
        f"• Трафик: ↑ <code>{format_bytes(up_bytes)}</code> / ↓ <code>{format_bytes(down_bytes)}</code>",
        f"• Использовано / лимит: <code>{escape(limit_str)}</code>",
        f"• Остаток: <code>{escape(remain_str)}</code>",
        f"• Дата окончания: <code>{expiry_str}</code>",
        "────────────────────",
        f"• <b>Лимит HWID:</b> <code>{escape(hwid_limit_display)}</code>  |  <b>Устройств:</b> <code>{escape(hwid_count_display)}</code>",
        format_hwid_devices_block(devices, hwid_raw),
        "────────────────────",
    ])

    if limit_ip not in (None, "", 0, "0"):
        lines.append(f"• Лимит IP: <code>{escape(str(limit_ip))}</code>")

    return "\n".join(lines)
