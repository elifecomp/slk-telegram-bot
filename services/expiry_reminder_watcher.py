import asyncio
import json
import logging
import math
import os
import sqlite3
from datetime import datetime, timezone
from html import escape
from aiogram import Bot
from api.panel_client import Panel3XUIClient
from config import ADMIN_ID, ADMIN_IDS
from services.clients_db import list_clients, resolve_clients_db_path

logger = logging.getLogger("expiry_reminder_watcher")


def _connect_db() -> sqlite3.Connection:
    db_path = resolve_clients_db_path()
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription_expiry_reminders (
                telegram_id INTEGER PRIMARY KEY,
                login TEXT DEFAULT '',
                last_expiry_ts INTEGER NOT NULL,
                last_stage TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _get_state(telegram_id: int) -> tuple[int, str] | None:
    _ensure_table()
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT last_expiry_ts, last_stage FROM subscription_expiry_reminders WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            return None
        return int(row["last_expiry_ts"]), str(row["last_stage"] or "")


def _set_state(telegram_id: int, login: str, expiry_ts: int, stage: str) -> None:
    _ensure_table()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO subscription_expiry_reminders (telegram_id, login, last_expiry_ts, last_stage, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id) DO UPDATE SET
                login = excluded.login,
                last_expiry_ts = excluded.last_expiry_ts,
                last_stage = excluded.last_stage,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, login, int(expiry_ts), stage),
        )
        conn.commit()


def _normalize_expiry_sec(raw_val) -> int | None:
    if raw_val in (None, "", 0, "0", -1, "-1"):
        return None
    try:
        num = float(raw_val)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    if num > 1e11:
        num = num / 1000.0
    return int(num)


def _collect_expiries(inbounds_obj: list) -> dict[str, int]:
    """Возвращает {email: expiry_ts_sec}."""
    exp_map: dict[str, int] = {}
    for ib in inbounds_obj:
        if not isinstance(ib, dict):
            continue
        s = ib.get("settings")
        if isinstance(s, str):
            try:
                s = json.loads(s)
            except Exception:
                s = {}
        if isinstance(s, dict):
            for c in s.get("clients") or []:
                if not isinstance(c, dict):
                    continue
                em = str(c.get("email") or "").strip()
                if not em:
                    continue
                ts = _normalize_expiry_sec(c.get("expiryTime") or c.get("expiry_time"))
                if ts is not None:
                    if em not in exp_map or ts > exp_map[em]:
                        exp_map[em] = ts
    return exp_map


def _admin_targets() -> set[int]:
    targets: set[int] = set(ADMIN_IDS or set())
    if ADMIN_ID:
        targets.add(int(ADMIN_ID))
    return {x for x in targets if x > 0}


def _build_client_card(client_name: str, expiry_ts: int, days_left: int) -> str:
    dt_str = datetime.fromtimestamp(expiry_ts, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    if days_left <= 0:
        left_label = "менее 1 дня (срок истекает сегодня)"
    elif days_left == 1:
        left_label = "1 день"
    elif days_left in (2, 3, 4):
        left_label = f"{days_left} дня"
    else:
        left_label = f"{days_left} дней"

    return (
        "⏳ <b>СКОРО ОКОНЧАНИЕ ПОДПИСКИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{escape(client_name)}</b>!\n\n"
        f"До окончания срока действия подписки осталось: <b>{escape(left_label)}</b>\n"
        f"📅 Дата окончания: <code>{escape(dt_str)}</code>\n"
        "Чтобы доступ не прервался, заранее свяжитесь с администратором для продления."
    )


def _build_admin_card(client_name: str, login: str, tg_id: int, expiry_ts: int, days_left: int) -> str:
    dt_str = datetime.fromtimestamp(expiry_ts, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    return (
        "⏳ <b>НАПОМИНАНИЕ О СРОКЕ ПОДПИСКИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• Клиент: <b>{escape(client_name)}</b>\n"
        f"• Логин: <code>{escape(login)}</code>\n"
        f"• Telegram ID: <code>{tg_id}</code>\n"
        f"• Осталось дней: <b>{max(0, days_left)}</b>\n"
        f"• Окончание: <code>{escape(dt_str)}</code>"
    )


async def check_and_notify_expiry_reminders(bot: Bot) -> None:
    _ensure_table()
    clients = list_clients(limit=100000)
    if not clients:
        return

    panel = Panel3XUIClient()
    resp = await panel.get_api("/inbounds/list")
    if not resp.get("success") or not isinstance(resp.get("obj"), list):
        return

    exp_map = _collect_expiries(resp["obj"])
    if not exp_map:
        return

    now_ts = int(datetime.now(timezone.utc).timestamp())

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

        matched_expiry = None
        matched_login = logins[0]
        for lg in logins:
            if lg in exp_map:
                matched_expiry = exp_map[lg]
                matched_login = lg
                break

        if matched_expiry is None:
            continue

        prev = _get_state(tg_id)
        prev_expiry, prev_stage = prev if prev else (None, "")

        # Если дата окончания в панели сдвинулась вперёд (продление), сбрасываем этап
        if prev_expiry is not None and matched_expiry > prev_expiry + 60:
            prev_stage = ""

        sec_left = matched_expiry - now_ts
        if sec_left <= 0:
            _set_state(tg_id, matched_login, matched_expiry, prev_stage)
            continue

        days_left = int(math.ceil(sec_left / 86400.0))
        if days_left > 3:
            _set_state(tg_id, matched_login, matched_expiry, prev_stage)
            continue

        stage = f"d_{days_left}"
        if prev_stage == stage and prev_expiry == matched_expiry:
            continue

        _set_state(tg_id, matched_login, matched_expiry, stage)
        client_name = str(row.get("name") or matched_login)

        try:
            await bot.send_message(
                chat_id=tg_id,
                text=_build_client_card(client_name, matched_expiry, days_left),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить напоминание о сроке tg_id=%s: %s", tg_id, exc)

        for admin_id in _admin_targets():
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=_build_admin_card(client_name, matched_login, tg_id, matched_expiry, days_left),
                    parse_mode="HTML",
                )
            except Exception:
                pass


async def watch_expiry_reminder_loop(bot: Bot, interval_seconds: int = 300) -> None:
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await check_and_notify_expiry_reminders(bot)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в наблюдателе срока подписки: %s", exc)
