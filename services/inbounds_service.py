from datetime import datetime, timezone
from html import escape
from api.inbounds_api import fetch_inbounds
from services.format_bytes import format_bytes


def _format_expiry(expiry_ms) -> str | None:
    if not expiry_ms:
        return None
    try:
        ts = int(expiry_ms)
        if ts <= 0:
            return None
        if ts > 10**11:
            ts //= 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%d.%m.%Y")
    except (TypeError, ValueError, OSError):
        return None


def _progress_bar(used: float, total: float, length: int = 8) -> str:
    if total <= 0:
        return ""
    ratio = max(0.0, min(1.0, used / total))
    filled = round(ratio * length)
    return f"[{'█' * filled}{'░' * (length - filled)}] {ratio * 100:.0f}%"


def _format_inbound_card(idx: int, item: dict) -> str:
    inbound_id = escape(str(item.get("id", "?")))
    raw_remark = (item.get("remark") or "").strip() or f"Inbound #{inbound_id}"
    remark = escape(raw_remark)
    protocol = escape(str(item.get("protocol") or "n/a").upper())
    port = item.get("port")
    enabled = item.get("enable") is not False

    status_badge = "🟢 <b>ВКЛ</b>" if enabled else "🔴 <b>ВЫКЛ</b>"

    up_val = float(item.get("up") or 0)
    down_val = float(item.get("down") or 0)
    total_limit_val = float(item.get("total") or 0)

    client_stats = item.get("clientStats") or []
    clients_count = len(client_stats) if isinstance(client_stats, list) else 0
    online_count = sum(1 for c in client_stats if isinstance(c, dict) and c.get("online") is True)

    line1 = f"<b>{idx}.</b> {status_badge}  <b>{remark}</b>  <code>#{inbound_id}</code>"

    spec_parts = [f"<code>{protocol}</code>"]
    if port:
        spec_parts.append(f"порт <code>{escape(str(port))}</code>")
    spec_parts.append(
        f"клиенты: <b>{clients_count}</b>" + (f" (🟢 {online_count})" if online_count else "")
    )
    line2 = f"    └ {' • '.join(spec_parts)}"

    traffic_parts = [f"↑ <code>{format_bytes(up_val)}</code>", f"↓ <code>{format_bytes(down_val)}</code>"]
    line3 = f"    └ трафик: {' / '.join(traffic_parts)}"

    extra_lines: list[str] = []
    if total_limit_val > 0:
        used_total = up_val + down_val
        bar = _progress_bar(used_total, total_limit_val)
        extra_lines.append(
            f"    └ лимит: <code>{format_bytes(used_total)}</code> / <code>{format_bytes(total_limit_val)}</code>  {bar}"
        )

    expiry_str = _format_expiry(item.get("expiryTime"))
    if expiry_str:
        extra_lines.append(f"    └ срок действия: до <code>{escape(expiry_str)}</code>")

    return "\n".join([line1, line2, line3, *extra_lines])


async def get_inbounds_report() -> str:
    ok, inbounds, source = await fetch_inbounds()
    if not ok:
        return f"⚠️ <b>Ошибка получения инбаундов</b>\n<code>{escape(str(source))}</code>"

    if not inbounds:
        return (
            "📥 <b>Инбаунды</b>\n"
            "────────────────────\n"
            "Список инбаундов пуст.\n\n"
            f"<i>Источник: <code>{escape(str(source))}</code></i>"
        )

    total_count = len(inbounds)
    enabled_count = sum(1 for x in inbounds if x.get("enable") is not False)
    total_clients = 0
    total_up = 0.0
    total_down = 0.0

    for item in inbounds:
        stats = item.get("clientStats") or []
        if isinstance(stats, list):
            total_clients += len(stats)
        total_up += float(item.get("up") or 0)
        total_down += float(item.get("down") or 0)

    header_lines = [
        "📥 <b>СПИСОК ИНБАУНДОВ</b>",
        "────────────────────",
        f"• Активно: <b>{enabled_count}</b> из <b>{total_count}</b>",
        f"• Всего клиентов: <b>{total_clients}</b>",
        f"• Суммарно: ↑ <code>{format_bytes(total_up)}</code> / ↓ <code>{format_bytes(total_down)}</code>",
        "────────────────────",
    ]

    cards = [_format_inbound_card(idx, item) for idx, item in enumerate(inbounds, start=1)]
    footer = f"\n────────────────────\n<i>Источник: <code>{escape(str(source))}</code></i>"

    body = "\n\n".join(cards)
    full_text = "\n".join(header_lines) + "\n" + body + footer

    if len(full_text) > 4050:
        kept_cards: list[str] = []
        base_len = len("\n".join(header_lines)) + len(footer) + 120
        for card in cards:
            if base_len + len(card) + 4 < 4000:
                kept_cards.append(card)
                base_len += len(card) + 2
            else:
                break
        omitted = len(cards) - len(kept_cards)
        notice = f"\n<i>… ещё инбаундов: {omitted} (сокращено под лимит Telegram)</i>" if omitted > 0 else ""
        full_text = "\n".join(header_lines) + "\n" + "\n\n".join(kept_cards) + notice + footer

    return full_text
