import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from html import escape

from aiogram import Bot

from api.panel_client import Panel3XUIClient
from services.clients_db import list_clients, resolve_clients_db_path

logger = logging.getLogger(__name__)


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(resolve_clients_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_state_table() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS client_inbounds_state (
                tg_id INTEGER PRIMARY KEY,
                inbounds_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )


def _get_saved_inbounds(tg_id: int) -> list[dict] | None:
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT inbounds_json FROM client_inbounds_state WHERE tg_id = ?",
            (int(tg_id),),
        ).fetchone()
        if row is None:
            return None
        raw = str(row["inbounds_json"] or "[]")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except Exception:
            pass
        return []


def _save_inbounds(tg_id: int, items: list[dict]) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    serialized = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO client_inbounds_state (tg_id, inbounds_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                inbounds_json = excluded.inbounds_json,
                updated_at = excluded.updated_at
            """,
            (int(tg_id), serialized, now_iso),
        )


def _parse_settings_dict(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _collect_email_inbounds(inbounds_list: list[dict]) -> dict[str, list[dict]]:
    """Возвращает {email: [{"id": int|str, "name": str}, ...]} строго по settings.clients."""
    by_email: dict[str, list[dict]] = {}

    for ib in inbounds_list:
        if not isinstance(ib, dict):
            continue
        ib_id = ib.get("id")
        remark = str(ib.get("remark") or ib.get("tag") or (f"Inbound #{ib_id}" if ib_id is not None else "Инбаунд")).strip()
        settings_dict = _parse_settings_dict(ib.get("settings"))
        clients_arr = settings_dict.get("clients")
        if not isinstance(clients_arr, list):
            continue

        for c in clients_arr:
            if not isinstance(c, dict):
                continue
            em = str(c.get("email") or "").strip()
            if not em:
                continue
            lst = by_email.setdefault(em, [])
            key_str = str(ib_id) if ib_id is not None else remark
            if not any(str(item.get("key")) == key_str for item in lst):
                lst.append(
                    {
                        "key": key_str,
                        "id": ib_id,
                        "name": remark,
                    }
                )

    for em in by_email:
        by_email[em].sort(key=lambda x: str(x.get("key") or ""))

    return by_email


def _format_inbound_line(item: dict) -> str:
    name = escape(str(item.get("name") or "Инбаунд"))
    ib_id = item.get("id")
    if ib_id is not None and str(ib_id).strip() != "":
        return f"• <b>{name}</b> (ID: <code>{escape(str(ib_id))}</code>)"
    return f"• <b>{name}</b>"


def _build_added_card(client_name: str, added_items: list[dict]) -> str:
    safe_name = escape(client_name.strip() or "Клиент")
    items_block = "\n".join(_format_inbound_line(x) for x in added_items)
    if len(added_items) == 1:
        item = added_items[0]
        name = escape(str(item.get("name") or "Инбаунд"))
        ib_id = item.get("id")
        id_part = f" (ID: <code>{escape(str(ib_id))}</code>)" if ib_id is not None else ""
        body = f"Инбаунд <b>{name}</b>{id_part} добавлен в вашу подписку. Поздравляем вас!"
    else:
        body = (
            "В вашу подписку добавлены новые инбаунды. Поздравляем вас!\n\n"
            f"{items_block}"
        )

    return (
        "➕ <b>ОБНОВЛЕНИЕ ПОДПИСКИ: ДОБАВЛЕН СЕРВЕР</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{safe_name}</b>!\n\n"
        f"{body}\n\n"
        "🔄 <i>Обновите подписку в приложении, чтобы изменения вступили в силу.</i>"
    )


def _build_removed_card(client_name: str, removed_items: list[dict]) -> str:
    safe_name = escape(client_name.strip() or "Клиент")
    items_block = "\n".join(_format_inbound_line(x) for x in removed_items)
    if len(removed_items) == 1:
        item = removed_items[0]
        name = escape(str(item.get("name") or "Инбаунд"))
        ib_id = item.get("id")
        id_part = f" (ID: <code>{escape(str(ib_id))}</code>)" if ib_id is not None else ""
        body = (
            f"Инбаунд <b>{name}</b>{id_part} удалён из вашей подписки "
            "в связи с изменением клиентской учётной записи."
        )
    else:
        body = (
            "Следующие инбаунды удалены из вашей подписки в связи с изменением клиентской учётной записи:\n\n"
            f"{items_block}"
        )

    return (
        "➖ <b>ОБНОВЛЕНИЕ ПОДПИСКИ: УДАЛЁН СЕРВЕР</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{safe_name}</b>!\n\n"
        f"{body}\n\n"
        "🔄 <i>Обновите подписку в приложении для синхронизации списка серверов.</i>"
    )


async def check_and_notify_inbound_changes(bot: Bot) -> None:
    _ensure_state_table()
    clients = list_clients(limit=100000)
    if not clients:
        return

    panel = Panel3XUIClient()
    resp = await panel.get_api("/inbounds/list")
    if not resp.get("success") or not isinstance(resp.get("obj"), list):
        return

    email_map = _collect_email_inbounds(resp["obj"])

    for row in clients:
        raw_tg = row.get("telegram_id")
        try:
            tg_id = int(raw_tg)
        except (TypeError, ValueError):
            continue
        if tg_id <= 0:
            continue

        logins = [
            str(row.get("login") or "").strip(),
            str(row.get("login2") or "").strip(),
        ]
        logins = [x for x in logins if x]
        if not logins:
            continue

        # Объединяем все активные инбаунды по логинам клиента
        merged_current: dict[str, dict] = {}
        for lg in logins:
            for item in email_map.get(lg) or []:
                k = str(item.get("key") or "")
                if k and k not in merged_current:
                    merged_current[k] = item

        current_list = sorted(merged_current.values(), key=lambda x: str(x.get("key") or ""))
        saved_list = _get_saved_inbounds(tg_id)

        # Первый запуск для клиента — фиксируем базовое состояние без спама
        if saved_list is None:
            _save_inbounds(tg_id, current_list)
            continue

        old_by_key = {str(x.get("key") or ""): x for x in saved_list if str(x.get("key") or "")}
        new_by_key = {str(x.get("key") or ""): x for x in current_list if str(x.get("key") or "")}

        if set(old_by_key.keys()) == set(new_by_key.keys()):
            # Если изменилось только название (remark) инбаунда — тихо обновляем снимок
            if saved_list != current_list:
                _save_inbounds(tg_id, current_list)
            continue

        added_items = [new_by_key[k] for k in sorted(new_by_key.keys()) if k not in old_by_key]
        removed_items = [old_by_key[k] for k in sorted(old_by_key.keys()) if k not in new_by_key]

        client_name = str(row.get("name") or row.get("login") or "Клиент").strip()

        if added_items:
            try:
                await bot.send_message(
                    chat_id=tg_id,
                    text=_build_added_card(client_name, added_items),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.warning("Не удалось отправить уведомление о добавлении инбаунда клиенту %s: %s", tg_id, exc)

        if removed_items:
            try:
                await bot.send_message(
                    chat_id=tg_id,
                    text=_build_removed_card(client_name, removed_items),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.warning("Не удалось отправить уведомление об удалении инбаунда клиенту %s: %s", tg_id, exc)

        _save_inbounds(tg_id, current_list)
        await asyncio.sleep(0.05)


async def watch_inbound_change_loop(bot: Bot, interval_seconds: int = 60) -> None:
    _ensure_state_table()
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await check_and_notify_inbound_changes(bot)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в наблюдателе изменения инбаундов: %s", exc)
