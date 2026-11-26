import os
from urllib.parse import urlparse
from api.panel_client import Panel3XUIClient


def _extract_panel_host() -> str | None:
    raw_url = (os.getenv("PANEL_URL") or "").strip()
    if not raw_url:
        try:
            with open("/opt/SLK_BOT_3X-UI/.env", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("PANEL_URL="):
                        raw_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except OSError:
            return None
    if not raw_url:
        return None
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").strip()
    return host or None


async def fetch_server_status() -> tuple[bool, dict | list | str | None, str]:
    client = Panel3XUIClient()
    data = await client.get_api("/server/status")
    if data.get("success"):
        obj = data.get("obj")
        if isinstance(obj, dict):
            obj = dict(obj)
            panel_host = _extract_panel_host()
            if panel_host:
                obj["_panelHost"] = panel_host
            if not obj.get("panelVersion") and not obj.get("version"):
                spec_status, spec_data = await client.try_get_api("/openapi.json")
                if spec_status == 200 and isinstance(spec_data, dict):
                    info = spec_data.get("info")
                    if isinstance(info, dict) and info.get("version"):
                        obj["_openapiVersion"] = str(info["version"]).strip()
        return True, obj, "GET /server/status"
    return False, None, data.get("msg") or "неизвестная ошибка /server/status"
