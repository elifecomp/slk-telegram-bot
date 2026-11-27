import asyncio
import json
import logging
import os
import sqlite3
from html import escape
from aiogram import Bot
from api.panel_client import Panel3XUIClient
from services.clients_db import list_clients, resolve_clients_db_path
from services.tariff_plans import GIB_BYTES, resolve_tariff_name

logger = logging.getLogger("tariff_change_watcher")


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
            CREATE TABLE IF NOT EXISTS subscription_tariff_state (
                telegram_id INTEGER PRIMARY KEY,
                login TEXT DEFAULT '',
                last_limit_bytes REAL NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _get_last_limit(telegram_id: int) -> float | None:
    _ensure_state_table()
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT last_limit_bytes FROM subscription_tariff_state WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            return None
        return float(row["last_limit_bytes"])


def _set_last_limit(telegram_id: int, login: str, limit_bytes: float) -> None:
    _ensure_state_table()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO subscription_tariff_state (telegram_id, login, last_limit_bytes, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id) DO UPDATE SET
                login = excluded.login,
                last_limit_bytes = excluded.last_limit_bytes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, login, float(limit_bytes)),
        )
        conn.commit()


def _format_gb(num_bytes: float) -> str:
    gb = max(0.0, float(num_bytes)) / GIB_BYTES
    if abs(gb - round(gb)) < 0.05:
        return f"{round(gb)} ГБ"
    return f"{gb:.1f} ГБ"


def _collect_limits_and_usage(inbounds_obj: list) -> dict[str, tuple[float, float]]:
    """Возвращает {email: (limit_bytes, used_bytes)} по данным /inbounds/list."""
    limits: dict[str, float] = {}
    used_map: dict[str, float] = {}

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
                try:
                    lim = float(c_item.get("totalGB") or 0)
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
            up_b = float(st.get("up") or 0)
            down_b = float(st.get("down") or 0)
            u_b = up_b + down_b
            if u_b > used_map.get(em, 0.0):
                used_map[em] = u_b
            if em not in limits:
                try:
                    limits[em] = float(st.get("total") or 0)
                except (TypeError, ValueError):
                    limits[em] = 0.0

    out: dict[str, tuple[float, float]] = {}
    all_emails = set(limits.keys()) | set(used_map.keys())
    for em in all_emails:
        out[em] = (float(limits.get(em, 0.0)), float(used_map.get(em, 0.0)))
    return out


def _build_tariff_changed_card(client_name: str, new_limit_bytes: float, used_bytes: float) -> str:
    safe_name = escape(client_name.strip() or "Клиент")
    tariff_label = resolve_tariff_name(new_limit_bytes) or f"Лимит {_format_gb(new_limit_bytes)}"
    safe_tariff = escape(tariff_label)

    if new_limit_bytes <= 0:
        traffic_block = "♾️ Трафик: <b>Безлимитный</b>"
    else:
        avail_bytes = max(0.0, new_limit_bytes - used_bytes)
        traffic_block = (
            f"📦 Доступно трафика: <b>{escape(_format_gb(avail_bytes))}</b>\n"
            f"📊 Лимит: <b>{escape(_format_gb(new_limit_bytes))}</b> • Использовано: <b>{escape(_format_gb(used_bytes))}</b>"
        )

    return (
        "🔄 <b>ТАРИФ ИЗМЕНЁН</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{safe_name}</b>!\n\n"
        f"Ваш тариф изменён на: <b>{safe_tariff}</b>\n"
        f"{traffic_block}"
    )


async def check_and_notify_tariff_change(bot: Bot) -> None:
    _ensure_state_table()
    clients = list_clients(limit=100000)
    if not clients:
        return

    panel = Panel3XUIClient()
    resp = await panel.get_api("/inbounds/list")
    if not resp.get("success") or not isinstance(resp.get("obj"), list):
        return

    data_map = _collect_limits_and_usage(resp["obj"])
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

        current_limit, current_used = matched_pair
        prev_limit = _get_last_limit(tg_id)

        if prev_limit is None:
            _set_last_limit(tg_id, matched_login, current_limit)
            continue

        if abs(current_limit - prev_limit) < (50 * 1024 * 1024):
            continue

        _set_last_limit(tg_id, matched_login, current_limit)
        client_name = str(row.get("name") or matched_login)
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=_build_tariff_changed_card(client_name, current_limit, current_used),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить карточку смены тарифа tg_id=%s: %s", tg_id, exc)


async def watch_tariff_change_loop(bot: Bot, interval_seconds: int = 60) -> None:
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await check_and_notify_tariff_change(bot)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в фоновой проверке смены тарифа: %s", exc)
