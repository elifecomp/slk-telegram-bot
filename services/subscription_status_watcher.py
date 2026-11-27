import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from html import escape
from aiogram import Bot
from api.panel_client import Panel3XUIClient
from services.clients_db import list_clients, resolve_clients_db_path

logger = logging.getLogger("subscription_status_watcher")


def _connect_db() -> sqlite3.Connection:
    db_path = resolve_clients_db_path()
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_state_table() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription_enable_state (
                telegram_id INTEGER PRIMARY KEY,
                login TEXT DEFAULT '',
                last_enabled INTEGER NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _get_last_enabled(telegram_id: int) -> bool | None:
    _ensure_state_table()
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT last_enabled FROM subscription_enable_state WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            return None
        return bool(int(row["last_enabled"]))


def _set_last_enabled(telegram_id: int, login: str, enabled: bool) -> None:
    _ensure_state_table()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO subscription_enable_state (telegram_id, login, last_enabled, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id) DO UPDATE SET
                login = excluded.login,
                last_enabled = excluded.last_enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, login, 1 if enabled else 0),
        )
        conn.commit()


def _parse_bool(val) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        low = val.strip().lower()
        if low in ("true", "1", "yes", "on", "enabled", "active"):
            return True
        if low in ("false", "0", "no", "off", "disabled", "inactive"):
            return False
    return None


def _format_expiry_date(expiry_raw) -> str | None:
    if expiry_raw in (None, "", 0, "0"):
        return None
    try:
        val = float(expiry_raw)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    if val > 1e12:
        val = val / 1000.0
    try:
        dt = datetime.fromtimestamp(val, tz=timezone.utc).astimezone()
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return None


def _collect_client_states(inbounds_obj: list) -> dict[str, dict]:
    """Собирает {email: {"enabled": bool | None, "expiry": str | None}} из /inbounds/list."""
    result: dict[str, dict] = {}

    for ib in inbounds_obj:
        if not isinstance(ib, dict):
            continue

        settings_raw = ib.get("settings")
        if isinstance(settings_raw, str):
            try:
                settings_raw = json.loads(settings_raw)
            except Exception:
                settings_raw = {}

        if isinstance(settings_raw, dict):
            for c_item in settings_raw.get("clients") or []:
                if not isinstance(c_item, dict):
                    continue
                em = str(c_item.get("email") or "").strip()
                if not em:
                    continue
                en = _parse_bool(c_item.get("enable"))
                exp_str = _format_expiry_date(c_item.get("expiryTime"))
                prev = result.get(em)
                if prev is None:
                    result[em] = {"enabled": en, "expiry": exp_str}
                else:
                    if en is not None:
                        prev["enabled"] = en
                    if exp_str and not prev.get("expiry"):
                        prev["expiry"] = exp_str

        for st in ib.get("clientStats") or []:
            if not isinstance(st, dict):
                continue
            em = str(st.get("email") or "").strip()
            if not em:
                continue
            en_st = _parse_bool(st.get("enable"))
            exp_st = _format_expiry_date(st.get("expiryTime"))
            prev = result.get(em)
            if prev is None:
                result[em] = {"enabled": en_st, "expiry": exp_st}
            else:
                if prev.get("enabled") is None and en_st is not None:
                    prev["enabled"] = en_st
                if exp_st and not prev.get("expiry"):
                    prev["expiry"] = exp_st

    return result


def _build_disabled_card(client_name: str) -> str:
    safe_name = escape(client_name.strip() or "Клиент")
    return (
        "🔴 <b>ПОДПИСКА ОТКЛЮЧЕНА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{safe_name}</b>!\n\n"
        "Ваша подписка отключена за неуплату.\n"
        "Пожалуйста, оплатите подписку и обратитесь к администратору для активации."
    )


def _build_enabled_card(client_name: str, expiry_date: str | None) -> str:
    safe_name = escape(client_name.strip() or "Клиент")
    if expiry_date:
        date_line = f"📅 Действует до: <b>{escape(expiry_date)}</b>\n\n"
    else:
        date_line = "📅 Срок действия: <b>без ограничения по дате</b>\n\n"
    return (
        "🟢 <b>ПОДПИСКА СНОВА АКТИВНА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{safe_name}</b>!\n\n"
        "Поздравляем! Ваша подписка снова активна.\n"
        f"{date_line}"
        "Приятного пользования сервисом <b>SLK</b>!"
    )


async def check_and_notify_subscription_status(bot: Bot) -> None:
    _ensure_state_table()
    clients = list_clients(limit=100000)
    if not clients:
        return

    panel = Panel3XUIClient()
    resp = await panel.get_api("/inbounds/list")
    if not resp.get("success") or not isinstance(resp.get("obj"), list):
        return

    states_map = _collect_client_states(resp["obj"])
    if not states_map:
        return

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

        matched_info = None
        matched_login = logins[0]
        for lg in logins:
            if lg in states_map and states_map[lg].get("enabled") is not None:
                matched_info = states_map[lg]
                matched_login = lg
                break

        if not matched_info:
            continue

        current_enabled = bool(matched_info["enabled"])
        expiry_date = matched_info.get("expiry")
        prev_enabled = _get_last_enabled(tg_id)

        if prev_enabled is None:
            _set_last_enabled(tg_id, matched_login, current_enabled)
            continue

        if prev_enabled == current_enabled:
            continue

        _set_last_enabled(tg_id, matched_login, current_enabled)
        client_name = str(row.get("name") or matched_login)

        logger.info(
            "Изменение статуса подписки: tg_id=%s login=%s %s -> %s (expiry=%s)",
            tg_id,
            matched_login,
            prev_enabled,
            current_enabled,
            expiry_date,
        )
        try:
            if current_enabled:
                await bot.send_message(
                    chat_id=tg_id,
                    text=_build_enabled_card(client_name, expiry_date),
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=tg_id,
                    text=_build_disabled_card(client_name),
                    parse_mode="HTML",
                )
        except Exception as exc:
            logger.warning("Не удалось отправить карточку статуса подписки tg_id=%s: %s", tg_id, exc)


async def watch_subscription_status_loop(bot: Bot, interval_seconds: int = 60) -> None:
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await check_and_notify_subscription_status(bot)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в фоновой проверке статуса подписки: %s", exc)
