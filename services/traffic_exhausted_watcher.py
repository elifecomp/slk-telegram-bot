import asyncio
import logging
import os
import sqlite3
from html import escape
from aiogram import Bot
from api.panel_client import Panel3XUIClient
from services.clients_db import list_clients, resolve_clients_db_path

logger = logging.getLogger("traffic_exhausted_watcher")


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
            CREATE TABLE IF NOT EXISTS traffic_exhausted_notifications (
                telegram_id INTEGER PRIMARY KEY,
                login TEXT DEFAULT '',
                notified_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _is_already_notified(telegram_id: int) -> bool:
    _ensure_state_table()
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM traffic_exhausted_notifications WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row is not None


def _mark_notified(telegram_id: int, login: str) -> None:
    _ensure_state_table()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO traffic_exhausted_notifications (telegram_id, login, notified_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id) DO UPDATE SET
                login = excluded.login,
                notified_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, login),
        )
        conn.commit()


def _clear_notified(telegram_id: int) -> None:
    _ensure_state_table()
    with _connect_db() as conn:
        conn.execute(
            "DELETE FROM traffic_exhausted_notifications WHERE telegram_id = ?",
            (telegram_id,),
        )
        conn.commit()


def _collect_usage_by_email(inbounds_obj: list) -> dict[str, tuple[float, float]]:
    """Возвращает {email: (used_bytes, limit_bytes)} по данным /inbounds/list."""
    usage: dict[str, tuple[float, float]] = {}

    for ib in inbounds_obj:
        if not isinstance(ib, dict):
            continue

        client_limits: dict[str, float] = {}
        settings_raw = ib.get("settings")
        if isinstance(settings_raw, str):
            import json
            try:
                settings_raw = json.loads(settings_raw)
            except Exception:
                settings_raw = {}
        if isinstance(settings_raw, dict):
            for c_item in settings_raw.get("clients") or []:
                if isinstance(c_item, dict):
                    em = str(c_item.get("email") or "").strip()
                    if em:
                        try:
                            client_limits[em] = float(c_item.get("totalGB") or 0)
                        except (TypeError, ValueError):
                            client_limits[em] = 0.0

        for st in ib.get("clientStats") or []:
            if not isinstance(st, dict):
                continue
            em = str(st.get("email") or "").strip()
            if not em:
                continue
            up_b = float(st.get("up") or 0)
            down_b = float(st.get("down") or 0)
            used_b = up_b + down_b
            lim_b = client_limits.get(em, 0.0)
            if lim_b <= 0:
                try:
                    lim_b = float(st.get("total") or 0)
                except (TypeError, ValueError):
                    lim_b = 0.0

            prev = usage.get(em)
            if prev is None or used_b > prev[0]:
                usage[em] = (used_b, max(lim_b, prev[1] if prev else 0.0))

    return usage


def _build_exhausted_card(client_name: str) -> str:
    safe_name = escape(client_name.strip() or "Клиент")
    return (
        "⛔ <b>ТРАФИК ЗАКОНЧИЛСЯ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{safe_name}</b>!\n\n"
        "Ваш трафик закончился, ваша подписка отключена.\n"
        "Для продления трафика обратитесь к администратору "
        "либо дождитесь первое число, и трафик ваш снова обновится."
    )


def _format_gb(num_bytes: float) -> str:
    gb = max(0.0, float(num_bytes)) / (1024 ** 3)
    if abs(gb - round(gb)) < 0.05:
        return f"{round(gb)} ГБ"
    return f"{gb:.1f} ГБ"


def _build_restored_card(client_name: str, used_bytes: float, limit_bytes: float) -> str:
    safe_name = escape(client_name.strip() or "Клиент")
    available_bytes = max(0.0, limit_bytes - used_bytes)
    avail_str = _format_gb(available_bytes)
    limit_str = _format_gb(limit_bytes)
    used_str = _format_gb(used_bytes)
    return (
        "✅ <b>ТРАФИК ВОССТАНОВЛЕН</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Здравствуйте, <b>{safe_name}</b>!\n\n"
        "Ваш трафик восстановлен, ваша подписка снова активна.\n"
        f"Вам доступно: <b>{escape(avail_str)}</b>\n\n"
        f"📊 <i>Лимит: {escape(limit_str)} • Использовано: {escape(used_str)}</i>"
    )


async def check_and_notify_exhausted_traffic(bot: Bot) -> None:
    _ensure_state_table()
    clients = list_clients(limit=100000)
    if not clients:
        return

    panel = Panel3XUIClient()
    resp = await panel.get_api("/inbounds/list")
    if not resp.get("success") or not isinstance(resp.get("obj"), list):
        return

    usage_map = _collect_usage_by_email(resp["obj"])
    if not usage_map:
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

        matched_entries = [usage_map[em] for em in logins if em in usage_map]
        if not matched_entries:
            continue

        max_used = max(x[0] for x in matched_entries)
        max_limit = max(x[1] for x in matched_entries)

        if max_limit <= 0:
            _clear_notified(tg_id)
            continue

        if max_used >= max_limit:
            if _is_already_notified(tg_id):
                continue
            client_name = str(row.get("name") or logins[0])
            try:
                await bot.send_message(
                    chat_id=tg_id,
                    text=_build_exhausted_card(client_name),
                    parse_mode="HTML",
                )
                _mark_notified(tg_id, logins[0])
            except Exception as exc:
                logger.warning("Не удалось отправить карточку окончания трафика tg_id=%s: %s", tg_id, exc)
        else:
            was_notified = _is_already_notified(tg_id)
            _clear_notified(tg_id)
            if was_notified:
                client_name = str(row.get("name") or logins[0])
                try:
                    await bot.send_message(
                        chat_id=tg_id,
                        text=_build_restored_card(client_name, max_used, max_limit),
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.warning("Не удалось отправить карточку восстановления трафика tg_id=%s: %s", tg_id, exc)


async def watch_exhausted_traffic_loop(bot: Bot, interval_seconds: int = 120) -> None:
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await check_and_notify_exhausted_traffic(bot)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в фоновой проверке окончания трафика: %s", exc)
