import json
from datetime import datetime, timezone
from html import escape


def _format_ts(val) -> str | None:
    if val in (None, "", 0, "0"):
        return None
    try:
        ts = int(val)
        if ts <= 0:
            return None
        if ts > 10**11:
            ts //= 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError, OSError):
        s = str(val).strip()
        return s or None


def format_hwid_devices_block(devices: list[dict], fallback_hwid_raw=None) -> str:
    if devices:
        blocks: list[str] = []
        for i, dev in enumerate(devices, start=1):
            fp = (
                dev.get("fingerprint")
                or dev.get("hwid")
                or dev.get("hash")
                or dev.get("id")
                or "не указан"
            )
            model = dev.get("deviceModel") or dev.get("model") or dev.get("device") or ""
            os_name = dev.get("deviceOs") or dev.get("os") or dev.get("platform") or ""
            os_ver = dev.get("osVersion") or ""
            ua = dev.get("userAgent") or dev.get("ua") or ""
            first_seen = _format_ts(dev.get("firstSeen") or dev.get("createdAt") or dev.get("first_seen"))
            last_seen = _format_ts(dev.get("lastSeen") or dev.get("updatedAt") or dev.get("last_seen"))

            os_full = " ".join(x for x in (str(os_name).strip(), str(os_ver).strip()) if x)
            dev_title = " • ".join(x for x in (str(model).strip(), os_full) if x)

            lines = [f"   {i}. Отпечаток HWID: <code>{escape(str(fp).strip())}</code>"]
            if dev_title:
                lines.append(f"      Устройство: <b>{escape(dev_title)}</b>")
            if first_seen:
                lines.append(f"      Первое появление: <code>{escape(first_seen)}</code>")
            if last_seen:
                lines.append(f"      Последнее появление: <code>{escape(last_seen)}</code>")
            if ua:
                lines.append(f"      Клиент: <code>{escape(str(ua)[:90])}</code>")
            blocks.append("\n".join(lines))
        return "\n".join(blocks)

    if fallback_hwid_raw not in (None, "", [], {}):
        if isinstance(fallback_hwid_raw, (list, tuple, dict)):
            formatted = json.dumps(fallback_hwid_raw, ensure_ascii=False)
        else:
            formatted = str(fallback_hwid_raw).strip()
        return f"   • <code>{escape(formatted)}</code>"

    return "   • устройств HWID нет"
