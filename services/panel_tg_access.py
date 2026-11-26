import json
import time
from typing import Any

from api.inbounds_api import fetch_inbounds

_CACHE_TTL_SECONDS = 25.0
_cached_tg_ids: set[int] = set()
_cached_at: float = 0.0


def _parse_int_id(val: Any) -> int | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val if val > 0 else None
    s = str(val).strip()
    if s.isdigit():
        num = int(s)
        return num if num > 0 else None
    return None


def _extract_tg_ids_from_obj(obj: Any, found: set[int]) -> None:
    if isinstance(obj, dict):
        for key in ("tgId", "tg_id", "telegram_id", "telegramId"):
            if key in obj:
                parsed = _parse_int_id(obj.get(key))
                if parsed is not None:
                    found.add(parsed)

        for list_key in ("clients", "clientStats", "obj", "data", "list", "items", "inbounds"):
            if list_key in obj:
                _extract_tg_ids_from_obj(obj.get(list_key), found)

        settings_val = obj.get("settings")
        if isinstance(settings_val, str) and settings_val.strip():
            try:
                parsed_settings = json.loads(settings_val)
                _extract_tg_ids_from_obj(parsed_settings, found)
            except Exception:
                pass
        elif isinstance(settings_val, dict):
            _extract_tg_ids_from_obj(settings_val, found)

    elif isinstance(obj, list):
        for item in obj:
            _extract_tg_ids_from_obj(item, found)


async def _fetch_raw_panel_tg_ids() -> set[int] | None:
    ok, inbounds, _ = await fetch_inbounds()
    if not ok:
        return None
    found: set[int] = set()
    _extract_tg_ids_from_obj(inbounds or [], found)
    return found


async def get_panel_tg_ids(force_refresh: bool = False) -> set[int]:
    global _cached_tg_ids, _cached_at
    now = time.monotonic()
    if not force_refresh and (now - _cached_at) < _CACHE_TTL_SECONDS:
        return set(_cached_tg_ids)

    fresh = await _fetch_raw_panel_tg_ids()
    if fresh is not None:
        _cached_tg_ids = fresh
        _cached_at = now
        return set(_cached_tg_ids)

    return set(_cached_tg_ids)


async def has_panel_access(telegram_id: int | str | None, force_refresh: bool = False) -> bool:
    parsed = _parse_int_id(telegram_id)
    if parsed is None:
        return False
    tg_ids = await get_panel_tg_ids(force_refresh=force_refresh)
    return parsed in tg_ids
