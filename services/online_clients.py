from html import escape
from aiogram.types import InlineKeyboardMarkup
from api.panel_client import Panel3XUIClient
from api.online_api import fetch_online_clients
from keyboards.online_kb import build_online_keyboard
from services.online_cache import OnlineClientEntry, store_online_batch


async def get_online_clients_report() -> tuple[str, InlineKeyboardMarkup | None]:
    ok, online_emails, source = await fetch_online_clients()
    if not ok:
        return (
            f"⚠️ <b>Ошибка получения онлайн-клиентов</b>\n"
            f"<code>{escape(str(source))}</code>",
            None,
        )

    if not online_emails:
        return (
            "🟢 <b>ОНЛАЙН КЛИЕНТЫ</b>\n"
            "Сейчас в сети никого нет (<b>0</b>).",
            None,
        )

    inbound_meta_map: dict[str, tuple[str, int | str | None, str, int | str | None]] = {}
    try:
        client = Panel3XUIClient()
        inbounds_resp = await client.get_api("/inbounds/list")
        if inbounds_resp.get("success") and isinstance(inbounds_resp.get("obj"), list):
            for inbound in inbounds_resp["obj"]:
                if not isinstance(inbound, dict):
                    continue
                remark = str(inbound.get("remark") or f"Inbound #{inbound.get('id')}").strip()
                inbound_id = inbound.get("id")
                protocol = str(inbound.get("protocol") or "").strip().lower()
                port = inbound.get("port")
                for stat in inbound.get("clientStats") or []:
                    if isinstance(stat, dict):
                        email = str(stat.get("email") or "").strip()
                        if email and email not in inbound_meta_map:
                            inbound_meta_map[email] = (remark, inbound_id, protocol, port)
    except Exception:
        pass

    entries: list[OnlineClientEntry] = []
    for name in online_emails:
        clean_name = str(name).strip()
        if not clean_name:
            continue
        remark, inbound_id, protocol, port = inbound_meta_map.get(
            clean_name, ("", None, "", None)
        )
        entries.append(
            OnlineClientEntry(
                email=clean_name,
                inbound_remark=remark,
                inbound_id=inbound_id,
                protocol=protocol,
                port=port,
            )
        )

    batch_id, pairs = store_online_batch(entries)

    text = (
        "🟢 <b>ОНЛАЙН КЛИЕНТЫ</b>\n"
        f"Активных подключений: <b>{len(pairs)}</b>"
    )
    keyboard = build_online_keyboard(batch_id, pairs)
    return text, keyboard
