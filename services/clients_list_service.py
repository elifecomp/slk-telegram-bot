import json
from html import escape
from aiogram.types import InlineKeyboardMarkup
from api.inbounds_api import fetch_inbounds
from keyboards.clients_kb import build_inbounds_select_keyboard, build_inbound_clients_keyboard
from services.clients_cache import InboundSummary, create_client_session, get_session, register_inbound_clients


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


def _extract_inbound_emails(inbound: dict) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()

    settings_dict = _parse_json_dict(inbound.get("settings"))
    for c in settings_dict.get("clients") or []:
        if isinstance(c, dict):
            em = str(c.get("email") or "").strip()
            if em and em not in seen:
                seen.add(em)
                emails.append(em)

    for st in inbound.get("clientStats") or []:
        if isinstance(st, dict):
            em = str(st.get("email") or "").strip()
            if em and em not in seen:
                seen.add(em)
                emails.append(em)

    return emails


async def get_inbounds_picker_report() -> tuple[str, InlineKeyboardMarkup | None]:
    ok, inbounds, source = await fetch_inbounds()
    if not ok:
        return f"⚠️ <b>Ошибка получения инбаундов</b>\n<code>{escape(str(source))}</code>", None

    if not inbounds:
        return "👥 <b>КЛИЕНТЫ</b>\n────────────────────\nИнбаунды не найдены.", None

    summaries: list[InboundSummary] = []
    for ib in inbounds:
        if not isinstance(ib, dict):
            continue
        ib_id = ib.get("id", "?")
        remark = str(ib.get("remark") or "").strip() or f"Inbound #{ib_id}"
        protocol = str(ib.get("protocol") or "").strip().lower()
        port = ib.get("port")
        clients = _extract_inbound_emails(ib)
        summaries.append(
            InboundSummary(
                inbound_id=ib_id,
                remark=remark,
                protocol=protocol,
                port=port,
                clients=clients,
            )
        )

    sid, pairs = create_client_session(summaries)
    total_clients = sum(len(x.clients) for x in summaries)

    text = (
        "👥 <b>КЛИЕНТЫ</b>\n"
        f"Инбаундов: <b>{len(summaries)}</b> • Клиентов: <b>{total_clients}</b>"
    )
    return text, build_inbounds_select_keyboard(sid, pairs)


async def get_inbound_clients_report(sid: str, ib_slot: str) -> tuple[str, InlineKeyboardMarkup | None]:
    state = get_session(sid)
    if not state or ib_slot not in state.inbounds:
        return "⚠️ Сессия устарела. Нажмите <b>«Клиенты»</b> заново.", None

    ib = state.inbounds[ib_slot]
    pairs = register_inbound_clients(sid, ib_slot)

    text = (
        f"👥 <b>{escape(ib.remark)}</b> <code>#{escape(str(ib.inbound_id))}</code>\n"
        f"Протокол: <code>{escape(ib.protocol or 'n/a')}</code> • Клиентов: <b>{len(pairs)}</b>"
    )
    return text, build_inbound_clients_keyboard(sid, ib_slot, pairs)
