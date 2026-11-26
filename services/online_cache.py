from dataclasses import dataclass
from uuid import uuid4


@dataclass
class OnlineClientEntry:
    email: str
    inbound_remark: str = ""
    inbound_id: int | str | None = None
    protocol: str = ""
    port: int | str | None = None


_SESSIONS: dict[str, dict[str, OnlineClientEntry]] = {}
_MAX_SESSIONS = 30


def store_online_batch(entries: list[OnlineClientEntry]) -> tuple[str, list[tuple[str, OnlineClientEntry]]]:
    """Сохраняет выборку онлайн-клиентов и возвращает (batch_id, [(slot_id, entry), ...])."""
    if len(_SESSIONS) >= _MAX_SESSIONS:
        oldest_key = next(iter(_SESSIONS))
        _SESSIONS.pop(oldest_key, None)

    batch_id = uuid4().hex[:8]
    slot_map: dict[str, OnlineClientEntry] = {}
    pairs: list[tuple[str, OnlineClientEntry]] = []

    for idx, entry in enumerate(entries):
        slot_id = f"{idx:x}"
        slot_map[slot_id] = entry
        pairs.append((slot_id, entry))

    _SESSIONS[batch_id] = slot_map
    return batch_id, pairs


def get_cached_client(batch_id: str, slot_id: str) -> OnlineClientEntry | None:
    batch = _SESSIONS.get(batch_id)
    if not batch:
        return None
    return batch.get(slot_id)
