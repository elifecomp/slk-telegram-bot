from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class InboundSummary:
    inbound_id: int | str
    remark: str
    protocol: str
    port: int | str | None
    clients: list[str] = field(default_factory=list)


@dataclass
class ClientSessionState:
    inbounds: dict[str, InboundSummary] = field(default_factory=dict)
    client_slots: dict[str, tuple[str, str]] = field(default_factory=dict)  # slot_id -> (ib_slot, email)


_SESSIONS: dict[str, ClientSessionState] = {}
_MAX_SESSIONS = 40


def create_client_session(inbound_list: list[InboundSummary]) -> tuple[str, list[tuple[str, InboundSummary]]]:
    if len(_SESSIONS) >= _MAX_SESSIONS:
        oldest = next(iter(_SESSIONS))
        _SESSIONS.pop(oldest, None)

    sid = uuid4().hex[:8]
    state = ClientSessionState()
    pairs: list[tuple[str, InboundSummary]] = []

    for idx, ib in enumerate(inbound_list):
        ib_slot = f"{idx:x}"
        state.inbounds[ib_slot] = ib
        pairs.append((ib_slot, ib))

    _SESSIONS[sid] = state
    return sid, pairs


def get_session(sid: str) -> ClientSessionState | None:
    return _SESSIONS.get(sid)


def register_inbound_clients(sid: str, ib_slot: str) -> list[tuple[str, str]]:
    state = _SESSIONS.get(sid)
    if not state:
        return []
    ib = state.inbounds.get(ib_slot)
    if not ib:
        return []

    state.client_slots.clear()
    pairs: list[tuple[str, str]] = []
    for idx, email in enumerate(ib.clients):
        c_slot = f"{idx:x}"
        state.client_slots[c_slot] = (ib_slot, email)
        pairs.append((c_slot, email))
    return pairs


def resolve_client_slot(sid: str, c_slot: str) -> tuple[str, str] | None:
    state = _SESSIONS.get(sid)
    if not state:
        return None
    return state.client_slots.get(c_slot)


def update_cached_client_email(sid: str, c_slot: str, old_email: str, new_email: str) -> None:
    state = _SESSIONS.get(sid)
    if not state:
        return
    mapping = state.client_slots.get(c_slot)
    if not mapping:
        return
    ib_slot, _ = mapping
    state.client_slots[c_slot] = (ib_slot, new_email)
    ib = state.inbounds.get(ib_slot)
    if ib and old_email in ib.clients:
        pos = ib.clients.index(old_email)
        ib.clients[pos] = new_email
