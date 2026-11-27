import asyncio
import json
import logging
import os
import sqlite3
from html import escape
from aiogram import Bot
from api.panel_client import Panel3XUIClient
from config import ADMIN_ID, ADMIN_IDS
from services.clients_db import list_clients, resolve_clients_db_path

logger = logging.getLogger("low_traffic_watcher")

GIB_BYTES = 1024 ** 3
LOW_TRAFFIC_THRESHOLD_BYTES = 1.0 * GIB_BYTES


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
            CREATE TABLE IF NOT EXISTS subscription_low_traffic_state (
                telegram_id INTEGER PRIMARY KEY,
                login TEXT DEFAULT '',
                last_limit_bytes REAL NOT NULL,
                notified_low INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _get_state(telegram_id: int) -> tuple[float, bool] | None:
    _ensure_table()
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT last_limit_bytes, notified_low FROM subscription_low_traffic_state WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            return None
        return float(row["last_limit_bytes"]), bool(int(row["notified_low"]))


def _set_state(telegram_id: int, login: str, limit_bytes: float, notified_low: bool) -> None:
    _ensure_table()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO subscription_low_traffic_state (telegram_id, login, last_limit_bytes, notified_low, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id) DO UPDATE SET
                login = excluded.login,
                last_limit_bytes = excluded.last_limit_bytes,
                notified_low = excluded.notified_low,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, login, float(limit_bytes), 1 if notified_low else 0),
        )
        conn.commit()


def _fmt_size(num_bytes: float) -> str:
    val = max(0.0, float(num_bytes))
    gb = val / GIB_BYTES
    if gb >= 1.0:
        if abs(gb - round(gb)) < 0.05:
            return f"{round(gb)} ГБ"
        return f"{gb:.2f} ГБ"
    mb = val / (1024 ** 2)
    return f"{mb:.0f} МБ"


def _collect_usage_and_limits(inbounds_obj: list) -> dict[str, tuple[float, float]]:
    """Возвращает {email: (limit_bytes, used_bytes)}."""
    limits: dict[str, float] = {}
    used_map: dict[str, float] = {}

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
                try:
                    lim = float(c.get("totalGB") or 0)
                except (TypeError, ValueError):
                    lim = 0.0
                if em not in limits or (lim > 0 and limits[em] <= 0):
                    limits[em] = lim

        for st in ib.get("clientStats") or []:
            if not isinstance(st, dict):
                continue
            em = str(st.get("email") or "").strip()
            if not em:
                continue
            u_b = float(st.get("up") or 0) + float(st.get("down") or 0)
            if u_b > used_map.get(em, 0.0):
                used_map[em] = u_b
            if em not in limits:
                try:
                    limits[em] = float(st.get("total") or 0)
                except (TypeError, ValueError):
                    limits[em] = 0.0

    out: dict[str, tuple[float, float]] = {}
    for em in set(limits.keys()) | set(used_map.keys()):
        out[em] = (float(limits.get(em, 0.0)), float(used_map.get(em, 0.0)))
    return out


def _admin_targets() -> set[int]:
    targets: set[int] = set(ADMIN_IDS or set())
    if ADMIN_ID:
        targets.add(int(ADMIN_ID))
    return {x for x in targets if x > 0}


def _build_client_low_card(client_name: str, remain_bytes: float, limit_bytes: float, used_bytes: float) -> str:
    return (
        "⚠️ <b>ЗАКАНЧИВАЕТСЯ ТРАФИК</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{escape(client_name)}</b>!\n\n"
        f"Ваш трафик заканчивается — осталось: <b>{escape(_fmt_size(remain_bytes))}</b>\n"
        f"📊 Лимит: <code>{escape(_fmt_size(limit_bytes))}</code> • Использовано: <code>{escape(_fmt_size(used_bytes))}</code>\n"
        "Вы можете запросить смену тарифа в разделе <b>«💳 Тарифы»</b>."
    )


def _build_admin_low_card(client_name: str, login: str, tg_id: int, remain_bytes: float, limit_bytes: float) -> str:
    return (
        "⚠️ <b>МАЛО ТРАФИКА У КЛИЕНТА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• Клиент: <b>{escape(client_name)}</b>\n"
        f"• Логин: <code>{escape(login)}</code>\n"
        f"• Telegram ID: <code>{tg_id}</code>\n"
        f"• Осталось: <b>{escape(_fmt_size(remain_bytes))}</b> из <code>{escape(_fmt_size(limit_bytes))}</code>"
    )


async def check_and_notify_low_traffic(bot: Bot) -> None:
    _ensure_table()
    clients = list_clients(limit=100000)
    if not clients:
        return

    panel = Panel3XUIClient()
    resp = await panel.get_api("/inbounds/list")
    if not resp.get("success") or not isinstance(resp.get("obj"), list):
        return

    data_map = _collect_usage_and_limits(resp["obj"])
    if not data_map:
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

        matched_pair = None
        matched_login = logins[0]
        for lg in logins:
            if lg in data_map:
                matched_pair = data_map[lg]
                matched_login = lg
                break

        if not matched_pair:
            continue

        limit_bytes, used_bytes = matched_pair
        prev = _get_state(tg_id)
        prev_limit, notified_low = prev if prev else (limit_bytes, False)

        # Если лимит увеличился (сменили тариф) или трафик сбросился — сбрасываем флаг предупреждения
        if limit_bytes > prev_limit + (50 * 1024 * 1024):
            notified_low = False

        if limit_bytes <= 0:
            _set_state(tg_id, matched_login, limit_bytes, False)
            continue

        remain_bytes = limit_bytes - used_bytes
        if remain_bytes > LOW_TRAFFIC_THRESHOLD_BYTES:
            if remain_bytes > LOW_TRAFFIC_THRESHOLD_BYTES * 1.5:
                notified_low = False
            _set_state(tg_id, matched_login, limit_bytes, notified_low)
            continue

        # Остаток <= 1 ГБ (и больше 0, чтобы не дублировать карточку полного исчерпания)
        if 0 < remain_bytes <= LOW_TRAFFIC_THRESHOLD_BYTES and not notified_low:
            _set_state(tg_id, matched_login, limit_bytes, True)
            client_name = str(row.get("name") or matched_login)
            try:
                await bot.send_message(
                    chat_id=tg_id,
                    text=_build_client_low_card(client_name, remain_bytes, limit_bytes, used_bytes),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.warning("Не удалось отправить предупреждение о трафике tg_id=%s: %s", tg_id, exc)

            for admin_id in _admin_targets():
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=_build_admin_low_card(client_name, matched_login, tg_id, remain_bytes, limit_bytes),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
        else:
            _set_state(tg_id, matched_login, limit_bytes, notified_low)


async def watch_low_traffic_loop(bot: Bot, interval_seconds: int = 60) -> None:
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await check_and_notify_low_traffic(bot)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в наблюдателе малого остатка трафика: %s", exc)
