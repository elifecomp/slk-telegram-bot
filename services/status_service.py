import socket
from html import escape
from api.status_api import fetch_server_status
from services.format_bytes import format_bytes


def _format_uptime(seconds_val) -> str:
    try:
        total_sec = int(float(seconds_val or 0))
    except (TypeError, ValueError):
        return "—"
    if total_sec <= 0:
        return "—"

    days, rem = divmod(total_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}д")
    if hours or days:
        parts.append(f"{hours}ч")
    parts.append(f"{minutes}м")
    return " ".join(parts)


def _format_la(la_val) -> str:
    if isinstance(la_val, (list, tuple)) and la_val:
        items = []
        for x in la_val[:3]:
            try:
                items.append(f"{float(x):.2f}")
            except (TypeError, ValueError):
                items.append(str(x))
        return ", ".join(items)
    if la_val not in (None, ""):
        return str(la_val)
    return "—"


def _pct(used, total) -> str:
    try:
        u = float(used or 0)
        t = float(total or 0)
        if t <= 0:
            return "0.0%"
        return f"{(u / t) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _extract_panel_version(data: dict) -> str | None:
    for key in (
        "version",
        "panelVersion",
        "appVersion",
        "3xuiVersion",
        "xuiVersion",
        "_openapiVersion",
    ):
        val = data.get(key)
        if val not in (None, "", "unknown"):
            clean = str(val).strip().lstrip("vV")
            if clean:
                return f"v{clean}"
    return None


def _extract_server_ip(data: dict) -> str | None:
    for key in ("ip", "ipv4", "publicIp", "publicIP", "serverIp", "externalIp", "host"):
        val = data.get(key)
        if isinstance(val, dict):
            for sub_k in ("ipv4", "ip", "address", "v4"):
                if val.get(sub_k):
                    return str(val[sub_k]).strip()
        elif val not in (None, "", "0.0.0.0", "127.0.0.1", "localhost"):
            s = str(val).strip()
            if s:
                return s

    host = str(data.get("_panelHost") or "").strip()
    if host:
        try:
            resolved = socket.gethostbyname(host)
            if resolved and resolved != "127.0.0.1":
                return resolved
        except OSError:
            pass
        return host
    return None


async def get_server_status_report() -> str:
    ok, payload, source = await fetch_server_status()
    if not ok:
        return (
            "🛑 <b>СТАТУС СЕРВЕРА ПАНЕЛИ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Ошибка получения данных: <code>{escape(str(source))}</code>"
        )

    data = payload if isinstance(payload, dict) else {}
    if isinstance(data.get("obj"), dict):
        merged = dict(data["obj"])
        for k, v in data.items():
            if k != "obj":
                merged.setdefault(k, v)
        data = merged

    panel_ver = _extract_panel_version(data)
    server_ip = _extract_server_ip(data)

    cpu_raw = data.get("cpu")
    try:
        cpu_str = f"{float(cpu_raw):.1f}%"
    except (TypeError, ValueError):
        cpu_str = "—"

    la_str = _format_la(data.get("loads") or data.get("loadAverage"))

    mem = data.get("mem") if isinstance(data.get("mem"), dict) else {}
    mem_cur = mem.get("current", data.get("memCurrent", 0))
    mem_tot = mem.get("total", data.get("memTotal", 0))
    mem_pct = _pct(mem_cur, mem_tot)

    swap = data.get("swap") if isinstance(data.get("swap"), dict) else {}
    swap_cur = swap.get("current", 0)
    swap_tot = swap.get("total", 0)

    disk = data.get("disk") if isinstance(data.get("disk"), dict) else {}
    disk_cur = disk.get("current", data.get("diskCurrent", 0))
    disk_tot = disk.get("total", data.get("diskTotal", 0))
    disk_pct = _pct(disk_cur, disk_tot)

    net_io = data.get("netIO") if isinstance(data.get("netIO"), dict) else {}
    io_up = net_io.get("up", data.get("netUp", 0))
    io_down = net_io.get("down", data.get("netDown", 0))

    net_traffic = data.get("netTraffic") if isinstance(data.get("netTraffic"), dict) else {}
    tr_up = net_traffic.get("sent", net_traffic.get("up", data.get("trafficSent", 0)))
    tr_down = net_traffic.get("recv", net_traffic.get("down", data.get("trafficRecv", 0)))

    uptime_str = _format_uptime(data.get("uptime"))

    xray = data.get("xray") if isinstance(data.get("xray"), dict) else {}
    xray_state = str(xray.get("state") or data.get("xrayState") or "unknown").strip()
    xray_ver = str(xray.get("version") or data.get("xrayVersion") or "").strip()
    xray_icon = "🟢" if xray_state.lower() in ("running", "active", "ok") else "🟡"
    xray_line = f"{xray_icon} <code>{escape(xray_state)}</code>"
    if xray_ver:
        xray_line += f" <code>(v{escape(xray_ver.lstrip('v'))})</code>"

    lines = [
        "🖥 <b>СТАТУС СЕРВЕРА ПАНЕЛИ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "<b>⚙️ Вычисления и память</b>",
        f"  • CPU: <code>{escape(cpu_str)}</code>  |  LA: <code>{escape(la_str)}</code>",
        f"  • RAM: <code>{format_bytes(mem_cur)} / {format_bytes(mem_tot)}</code> (<code>{escape(mem_pct)}</code>)",
    ]

    try:
        if float(swap_tot or 0) > 0:
            lines.append(
                f"  • Swap: <code>{format_bytes(swap_cur)} / {format_bytes(swap_tot)}</code>"
            )
    except (TypeError, ValueError):
        pass

    lines.extend([
        f"  • Диск: <code>{format_bytes(disk_cur)} / {format_bytes(disk_tot)}</code> (<code>{escape(disk_pct)}</code>)",
        "",
        "<b>🌐 Сеть и трафик</b>",
        f"  • Сеть (IO): ↑ <code>{format_bytes(io_up)}</code> / ↓ <code>{format_bytes(io_down)}</code>",
        f"  • Трафик:  ↑ <code>{format_bytes(tr_up)}</code> / ↓ <code>{format_bytes(tr_down)}</code>",
        "",
        "<b>⏱ Система и ядро</b>",
    ])

    if server_ip:
        lines.append(f"  • IP:     <code>{escape(server_ip)}</code>")

    lines.extend([
        f"  • Аптайм: <code>{escape(uptime_str)}</code>",
        f"  • 3X-UI:  <code>{escape(panel_ver)}</code>" if panel_ver else "  • 3X-UI:  <code>—</code>",
        f"  • Xray:   {xray_line}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<i>Источник: {escape(str(source or '/server/status'))}</i>",
    ])

    return "\n".join(lines)
