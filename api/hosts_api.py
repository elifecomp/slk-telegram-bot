import uuid
from api.panel_client import Panel3XUIClient


def _extract_hosts_list(data: dict | None) -> list[dict]:
    if not isinstance(data, dict):
        return []
    obj = data.get("obj")
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for key in ("hosts", "list", "items", "data"):
            val = obj.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


async def fetch_hosts() -> tuple[bool, list[dict], str]:
    client = Panel3XUIClient()
    status, data = await client.try_get_api("/hosts/list")
    if status == 404 or data is None:
        return False, [], "эндпоинт /hosts/list недоступен (404)"
    if isinstance(data, dict) and data.get("success") is False:
        return False, [], str(data.get("msg") or "ошибка получения хостов")
    return True, _extract_hosts_list(data), ""


def build_host_payload(base: dict | None = None, **overrides) -> dict:
    src = dict(base) if isinstance(base, dict) else {}
    group_id = str(src.get("groupId") or "").strip() or uuid.uuid4().hex[:16]

    inbound_ids_raw = overrides.get("inboundIds", src.get("inboundIds", []))
    inbound_ids: list[int] = []
    if isinstance(inbound_ids_raw, list):
        for item in inbound_ids_raw:
            try:
                inbound_ids.append(int(str(item).strip()))
            except (TypeError, ValueError):
                pass
    elif isinstance(inbound_ids_raw, str):
        for part in inbound_ids_raw.replace(";", ",").split(","):
            p = part.strip()
            if p.isdigit():
                inbound_ids.append(int(p))

    hosts_raw = overrides.get("hosts", src.get("hosts", []))
    hosts_list: list[str] = []
    if isinstance(hosts_raw, list):
        hosts_list = [str(h).strip() for h in hosts_raw if str(h).strip()]
    elif isinstance(hosts_raw, str):
        for part in hosts_raw.replace(";", ",").splitlines():
            for sub in part.split(","):
                s = sub.strip()
                if s:
                    hosts_list.append(s)

    port_val = overrides.get("port", src.get("port", 0))
    try:
        port_int = int(port_val or 0)
    except (TypeError, ValueError):
        port_int = 0

    if port_int <= 0 and hosts_list and ":" in hosts_list[0]:
        maybe_port = hosts_list[0].rsplit(":", 1)[-1].strip()
        if maybe_port.isdigit():
            port_int = int(maybe_port)

    payload: dict = {
        "groupId": group_id,
        "inboundIds": inbound_ids,
        "hosts": hosts_list,
        "sortOrder": int(overrides.get("sortOrder", src.get("sortOrder", 0)) or 0),
        "remark": str(overrides.get("remark", src.get("remark", "")) or "").strip(),
        "serverDescription": str(
            overrides.get("serverDescription", src.get("serverDescription", "")) or ""
        ).strip(),
        "isDisabled": bool(overrides.get("isDisabled", src.get("isDisabled", False))),
        "isHidden": bool(overrides.get("isHidden", src.get("isHidden", False))),
        "tags": list(src.get("tags") or []),
        "port": port_int,
        "security": str(overrides.get("security", src.get("security", "same")) or "same").strip(),
        "sni": str(overrides.get("sni", src.get("sni", "")) or ""),
        "snis": src.get("snis"),
        "sniSharedRandom": bool(src.get("sniSharedRandom", False)),
        "hostHeader": str(overrides.get("hostHeader", src.get("hostHeader", "")) or ""),
        "path": str(overrides.get("path", src.get("path", "")) or ""),
        "alpn": list(src.get("alpn") or []),
        "fingerprint": str(src.get("fingerprint", "") or ""),
        "cipherSuites": str(src.get("cipherSuites", "") or ""),
        "overrideSniFromAddress": bool(src.get("overrideSniFromAddress", False)),
        "keepSniBlank": bool(src.get("keepSniBlank", False)),
        "pinnedPeerCertSha256": list(src.get("pinnedPeerCertSha256") or []),
        "verifyPeerCertByName": str(src.get("verifyPeerCertByName", "") or ""),
        "allowInsecure": bool(src.get("allowInsecure", False)),
        "echConfigList": str(src.get("echConfigList", "") or ""),
        "muxParams": str(src.get("muxParams", "") or ""),
        "sockoptParams": str(src.get("sockoptParams", "") or ""),
        "finalMask": str(src.get("finalMask", "") or ""),
        "vlessRoute": str(src.get("vlessRoute", "") or ""),
        "excludeFromSubTypes": list(src.get("excludeFromSubTypes") or []),
        "nodeGuids": list(src.get("nodeGuids") or []),
        "mihomoIpVersion": str(src.get("mihomoIpVersion", "") or ""),
        "mihomoX25519": bool(src.get("mihomoX25519", False)),
        "shuffleHost": bool(src.get("shuffleHost", False)),
        "randomCount": int(src.get("randomCount", 1) or 1),
    }
    return payload


async def add_host(payload: dict) -> tuple[bool, str]:
    client = Panel3XUIClient()
    for ep in ("/hosts/add", "/hosts/create"):
        status, data = await client.try_post_api(ep, payload)
        if status == 404 or data is None:
            continue
        if isinstance(data, dict):
            if data.get("success") is False:
                return False, str(data.get("msg") or "ошибка валидации при добавлении хоста")
            return True, str(data.get("msg") or "хост добавлен")
        return True, "хост добавлен"
    return False, "эндпоинт добавления хоста не найден"


async def update_host(payload: dict) -> tuple[bool, str]:
    client = Panel3XUIClient()
    for ep in ("/hosts/update", "/hosts/edit", "/hosts/save", "/hosts/reorder"):
        status, data = await client.try_post_api(ep, payload)
        if status == 404 or data is None:
            continue
        if isinstance(data, dict):
            if data.get("success") is False:
                return False, str(data.get("msg") or "ошибка при обновлении хоста")
            return True, str(data.get("msg") or "хост обновлён")
        return True, "хост обновлён"
    return False, "эндпоинт обновления хоста не найден"


async def delete_host(group_id: str) -> tuple[bool, str]:
    client = Panel3XUIClient()
    body = {"groupId": group_id, "id": group_id}
    for ep in ("/hosts/delete", "/hosts/del", "/hosts/remove", f"/hosts/{group_id}/delete", f"/hosts/{group_id}"):
        status, data = await client.try_post_api(ep, body)
        if status == 404 or data is None:
            continue
        if isinstance(data, dict):
            if data.get("success") is False:
                return False, str(data.get("msg") or "ошибка при удалении хоста")
            return True, str(data.get("msg") or "хост удалён")
        return True, "хост удалён"
    return False, "эндпоинт удаления хоста не найден"
