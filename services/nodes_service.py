from html import escape
from api.nodes_api import fetch_nodes


def _format_node_status(node: dict) -> tuple[str, str]:
    raw_state = str(
        node.get("status")
        or node.get("state")
        or node.get("connectionState")
        or ("online" if node.get("enable", True) is not False else "offline")
    ).strip()
    low = raw_state.lower()

    if low in ("online", "connected", "up", "running", "ok", "active"):
        return "🟢", "онлайн"
    if low in ("offline", "disconnected", "down", "error", "failed"):
        return "🔴", "офлайн"
    return "🟡", raw_state or "неизвестно"


def _extract_address(node: dict) -> str:
    ip = str(
        node.get("ip")
        or node.get("ipv4")
        or node.get("host")
        or node.get("address")
        or ""
    ).strip()
    port = node.get("port") or node.get("apiPort") or node.get("panelPort")

    if ip and port not in (None, "", 0, "0"):
        return f"{ip}:{port}"
    if ip:
        return ip
    if port not in (None, "", 0, "0"):
        return f":{port}"
    return "—"


def _clean_ver(val) -> str | None:
    if val in (None, "", "unknown", "none", "null"):
        return None
    s = str(val).strip().lstrip("vV")
    return f"v{s}" if s else None


def _extract_node_panel_version(node: dict) -> str | None:
    keys = (
        "panelVersion",
        "3xuiVersion",
        "xuiVersion",
        "appVersion",
        "panel_version",
        "xui_version",
    )
    for k in keys:
        v = _clean_ver(node.get(k))
        if v:
            return v

    for sub_key in ("panel", "info", "status", "system", "meta"):
        sub = node.get(sub_key)
        if isinstance(sub, dict):
            for k in keys + ("version",):
                v = _clean_ver(sub.get(k))
                if v:
                    return v
    return None


def _extract_node_xray_version(node: dict) -> str | None:
    for k in ("xrayVersion", "xray_version", "coreVersion", "version"):
        v = _clean_ver(node.get(k))
        if v:
            return v

    xray_obj = node.get("xray")
    if isinstance(xray_obj, dict):
        for k in ("version", "xrayVersion", "ver"):
            v = _clean_ver(xray_obj.get(k))
            if v:
                return v
    return None


def _extract_extra_metrics(node: dict) -> list[str]:
    extras: list[str] = []

    cpu = node.get("cpu")
    if isinstance(cpu, (int, float)):
        extras.append(f"CPU {cpu:.1f}%")
    elif isinstance(cpu, str) and cpu.strip():
        extras.append(f"CPU {cpu.strip()}")

    ping = node.get("ping") or node.get("latency")
    if ping not in (None, "", 0, "0"):
        extras.append(f"Ping {ping} мс")

    return extras


async def get_nodes_report() -> str:
    ok, nodes_data, source = await fetch_nodes()

    if not ok:
        return (
            "🌐 <b>УЗЛЫ ПАНЕЛИ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Ошибка получения данных: <code>{escape(str(source))}</code>"
        )

    if isinstance(nodes_data, dict):
        for key in ("nodes", "list", "items", "data", "obj"):
            if isinstance(nodes_data.get(key), list):
                nodes_data = nodes_data[key]
                break

    if not isinstance(nodes_data, list) or not nodes_data:
        return (
            "🌐 <b>УЗЛЫ ПАНЕЛИ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Узлы не найдены (<b>0</b>)."
        )

    valid_nodes = [n for n in nodes_data if isinstance(n, dict)]
    online_count = sum(1 for n in valid_nodes if _format_node_status(n)[1] == "онлайн")

    lines = [
        "🌐 <b>УЗЛЫ ПАНЕЛИ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"• Всего узлов: <b>{len(valid_nodes)}</b>  |  В сети: <b>{online_count}</b>",
        "",
    ]

    for idx, node in enumerate(valid_nodes, start=1):
        name = str(
            node.get("name")
            or node.get("remark")
            or node.get("title")
            or f"Узел #{node.get('id', idx)}"
        ).strip()
        icon, state_label = _format_node_status(node)
        addr = _extract_address(node)
        panel_ver = _extract_node_panel_version(node)
        xray_ver = _extract_node_xray_version(node)
        extras = _extract_extra_metrics(node)

        lines.append(f"<b>{idx}.</b> {icon} <b>{escape(name)}</b> — <b>{escape(state_label)}</b>")
        lines.append(f"   • Адрес: <code>{escape(addr)}</code>")
        if panel_ver:
            lines.append(f"   • 3X-UI: <code>{escape(panel_ver)}</code>")
        if xray_ver:
            lines.append(f"   • Xray:  <code>{escape(xray_ver)}</code>")
        if extras:
            lines.append(f"   • Инфо:  <code>{escape(' • '.join(extras))}</code>")
        if idx < len(valid_nodes):
            lines.append("")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━",
        f"<i>Источник: {escape(str(source or '/nodes/list'))}</i>",
    ])

    return "\n".join(lines)
