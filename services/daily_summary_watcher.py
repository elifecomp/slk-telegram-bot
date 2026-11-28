import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot

from api.panel_client import Panel3XUIClient
from services.clients_db import list_clients, resolve_clients_db_path
from services.tariff_plans import resolve_tariff_name

logger = logging.getLogger(__name__)
MSK_TZ = ZoneInfo("Europe/Moscow")

MONTHS_RU_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def _fmt_date_ru(dt: datetime) -> str:
    month_word = MONTHS_RU_GENITIVE.get(dt.month, "")
    return f"{dt.day} {month_word} {dt.year}"


def _fmt_gb(num_bytes: float) -> str:
    gb = max(0.0, float(num_bytes or 0)) / (1024 ** 3)
    return f"{gb:.2f} ГБ"


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


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(resolve_clients_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_traffic_snapshots (
                tg_id INTEGER PRIMARY KEY,
                last_up REAL NOT NULL DEFAULT 0,
                last_down REAL NOT NULL DEFAULT 0,
                last_sent_date TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )


def is_daily_summary_enabled(tg_id: int) -> bool:
    _ensure_table()
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_summary_prefs (
                tg_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        row = conn.execute(
            "SELECT enabled FROM daily_summary_prefs WHERE tg_id = ?",
            (int(tg_id),),
        ).fetchone()
        if row is None:
            return True
        return int(row["enabled"]) != 0


def set_daily_summary_enabled(tg_id: int, enabled: bool) -> bool:
    _ensure_table()
    now_iso = datetime.now(MSK_TZ).isoformat()
    val = 1 if enabled else 0
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_summary_prefs (
                tg_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT INTO daily_summary_prefs (tg_id, enabled, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (int(tg_id), val, now_iso),
        )
    return bool(enabled)


def _get_snapshot(tg_id: int) -> dict | None:
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT tg_id, last_up, last_down, last_sent_date, updated_at
            FROM daily_traffic_snapshots
            WHERE tg_id = ?
            """,
            (tg_id,),
        ).fetchone()
        return dict(row) if row else None


def _upsert_snapshot(
    tg_id: int,
    up_val: float,
    down_val: float,
    last_sent_date: str | None = None,
) -> None:
    now_iso = datetime.now(MSK_TZ).isoformat()
    current = _get_snapshot(tg_id)
    sent_date_val = (
        last_sent_date
        if last_sent_date is not None
        else (str(current.get("last_sent_date") or "") if current else "")
    )
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO daily_traffic_snapshots (tg_id, last_up, last_down, last_sent_date, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                last_up = excluded.last_up,
                last_down = excluded.last_down,
                last_sent_date = excluded.last_sent_date,
                updated_at = excluded.updated_at
            """,
            (tg_id, float(up_val), float(down_val), sent_date_val, now_iso),
        )


def _collect_panel_client_data(inbounds_list: list[dict]) -> dict[str, dict]:
    """Собирает по email: суммарный up/down, лимит, активные инбаунды и наличие клиента в settings.clients."""
    by_email: dict[str, dict] = {}

    for ib in inbounds_list:
        if not isinstance(ib, dict):
            continue
        ib_id = ib.get("id")
        remark = str(ib.get("remark") or ib.get("tag") or (f"#{ib_id}" if ib_id is not None else "")).strip()
        settings_dict = _parse_settings_dict(ib.get("settings"))

        active_emails_in_ib: set[str] = set()
        for c in settings_dict.get("clients") or []:
            if not isinstance(c, dict):
                continue
            em = str(c.get("email") or "").strip()
            if not em:
                continue
            active_emails_in_ib.add(em)
            entry = by_email.setdefault(
                em,
                {
                    "up": 0.0,
                    "down": 0.0,
                    "limit": 0.0,
                    "servers": [],
                    "in_any_inbound": False,
                },
            )
            entry["in_any_inbound"] = True
            if remark and remark not in entry["servers"]:
                entry["servers"].append(remark)
            for lk in ("totalGB", "total"):
                lv = c.get(lk)
                if lv not in (None, "", 0, "0"):
                    try:
                        lf = float(lv)
                        if lf > entry["limit"]:
                            entry["limit"] = lf
                    except (TypeError, ValueError):
                        pass

        for st in ib.get("clientStats") or []:
            if not isinstance(st, dict):
                continue
            em = str(st.get("email") or "").strip()
            if not em or em not in active_emails_in_ib:
                continue
            entry = by_email.setdefault(
                em,
                {
                    "up": 0.0,
                    "down": 0.0,
                    "limit": 0.0,
                    "servers": [],
                    "in_any_inbound": True,
                },
            )
            try:
                entry["up"] += float(st.get("up") or 0)
            except (TypeError, ValueError):
                pass
            try:
                entry["down"] += float(st.get("down") or 0)
            except (TypeError, ValueError):
                pass
            for lk in ("totalGB", "total"):
                lv = st.get(lk)
                if lv not in (None, "", 0, "0"):
                    try:
                        lf = float(lv)
                        if lf > entry["limit"]:
                            entry["limit"] = lf
                    except (TypeError, ValueError):
                        pass

    return by_email


def _build_daily_summary_card(
    now_msk: datetime,
    servers: list[str],
    day_in_bytes: float,
    day_out_bytes: float,
    day_total_bytes: float,
    limit_bytes: float,
    used_total_bytes: float,
    has_baseline: bool,
) -> str:
    today_str = _fmt_date_ru(now_msk)
    yesterday_str = _fmt_date_ru(now_msk - timedelta(days=1))

    lines = [
        f"Сегодня <b>{escape(today_str)}</b>.",
        "Сводка вашей подписки за сутки",
        f"С <b>{escape(yesterday_str)}</b> по <b>{escape(today_str)}</b>",
        "",
        "<b>Активные сервера</b>",
    ]
    if servers:
        for srv in servers:
            lines.append(f"• <b>{escape(srv)}</b>")
    else:
        lines.append("• Нет активных инбаундов")

    lines.extend(["", "<b>Трафик за сутки потрачен</b>"])
    if has_baseline:
        lines.extend([
            f"Входящий: <code>{_fmt_gb(day_in_bytes)}</code>",
            f"Исходящий: <code>{_fmt_gb(day_out_bytes)}</code>",
            f"Всего: <code>{_fmt_gb(day_total_bytes)}</code>",
        ])
    else:
        lines.append("Базовый замер зафиксирован сегодня — точный расход за сутки появится завтра утром.")

    tariff_title = resolve_tariff_name(limit_bytes)
    tariff_suffix = f" тариф <b>{escape(tariff_title)}</b>" if tariff_title else ""

    lines.extend(["", "<b>Остаток трафика</b>"])
    if limit_bytes > 0:
        remain_bytes = max(0.0, limit_bytes - used_total_bytes)
        lines.extend([
            f"Всего: <code>{_fmt_gb(limit_bytes)}</code>{tariff_suffix}",
            f"Потрачено: <code>{_fmt_gb(used_total_bytes)}</code>",
            f"Остаток: <code>{_fmt_gb(remain_bytes)}</code>",
        ])
    else:
        lines.extend([
            f"Всего: <b>Безлимит</b>{tariff_suffix}",
            f"Потрачено: <code>{_fmt_gb(used_total_bytes)}</code>",
            "Остаток: <b>—</b>",
        ])

    lines.extend([
        "",
        "<i>Информация предоставлена агентом бота SLK</i>",
    ])
    return "\n".join(lines)


async def send_daily_summaries(bot: Bot, now_msk: datetime | None = None) -> int:
    """Формирует и отправляет утреннюю сводку активным клиентам. Возвращает число отправленных карточек."""
    _ensure_table()
    now_dt = now_msk or datetime.now(MSK_TZ)
    today_key = now_dt.strftime("%Y-%m-%d")

    clients = list_clients(limit=100000)
    if not clients:
        return 0

    panel = Panel3XUIClient()
    resp = await panel.get_api("/inbounds/list")
    if not resp.get("success") or not isinstance(resp.get("obj"), list):
        logger.warning("Daily summary: не удалось получить /inbounds/list")
        return 0

    panel_map = _collect_panel_client_data(resp["obj"])
    sent_total = 0

    for row in clients:
        if row.get("is_active", 1) == 0:
            continue
        raw_tg = row.get("telegram_id")
        try:
            tg_id = int(raw_tg)
        except (TypeError, ValueError):
            continue
        if tg_id <= 0:
            continue
        if not is_daily_summary_enabled(tg_id):
            continue

        logins = [
            str(row.get("login") or "").strip(),
            str(row.get("login2") or "").strip(),
        ]
        logins = [x for x in logins if x]
        if not logins:
            continue

        matched_entries = [panel_map[lg] for lg in logins if lg in panel_map and panel_map[lg].get("in_any_inbound")]
        if not matched_entries:
            continue

        cur_up = sum(float(e.get("up") or 0) for e in matched_entries)
        cur_down = sum(float(e.get("down") or 0) for e in matched_entries)
        limit_bytes = max((float(e.get("limit") or 0) for e in matched_entries), default=0.0)

        servers: list[str] = []
        for e in matched_entries:
            for srv in e.get("servers") or []:
                if srv not in servers:
                    servers.append(srv)

        snap = _get_snapshot(tg_id)
        if snap and str(snap.get("last_sent_date") or "") == today_key:
            continue

        has_baseline = snap is not None and str(snap.get("last_sent_date") or "") != ""
        if snap is not None and has_baseline:
            prev_up = float(snap.get("last_up") or 0)
            prev_down = float(snap.get("last_down") or 0)
            day_out = (cur_up - prev_up) if cur_up >= prev_up else cur_up
            day_in = (cur_down - prev_down) if cur_down >= prev_down else cur_down
        elif snap is not None:
            prev_up = float(snap.get("last_up") or 0)
            prev_down = float(snap.get("last_down") or 0)
            day_out = (cur_up - prev_up) if cur_up >= prev_up else cur_up
            day_in = (cur_down - prev_down) if cur_down >= prev_down else cur_down
            has_baseline = True
        else:
            day_out = 0.0
            day_in = 0.0

        day_total = max(0.0, day_in) + max(0.0, day_out)
        used_total = max(0.0, cur_up) + max(0.0, cur_down)

        card_text = _build_daily_summary_card(
            now_msk=now_dt,
            servers=servers,
            day_in_bytes=max(0.0, day_in),
            day_out_bytes=max(0.0, day_out),
            day_total_bytes=day_total,
            limit_bytes=limit_bytes,
            used_total_bytes=used_total,
            has_baseline=has_baseline,
        )

        try:
            await bot.send_message(chat_id=tg_id, text=card_text, parse_mode="HTML")
            _upsert_snapshot(tg_id, cur_up, cur_down, last_sent_date=today_key)
            sent_total += 1
        except Exception as exc:
            logger.warning("Daily summary: не удалось отправить клиенту %s: %s", tg_id, exc)
            _upsert_snapshot(tg_id, cur_up, cur_down, last_sent_date=None)

        await asyncio.sleep(0.05)

    return sent_total


async def watch_daily_summary_loop(bot: Bot, poll_seconds: int = 30) -> None:
    """Ежедневно в 08:00 по МСК (Europe/Moscow) отправляет сводку за сутки."""
    _ensure_table()
    while True:
        try:
            now_msk = datetime.now(MSK_TZ)
            today_key = now_msk.strftime("%Y-%m-%d")
            if (now_msk.hour, now_msk.minute) >= (8, 0):
                with _connect_db() as conn:
                    already_any = conn.execute(
                        "SELECT 1 FROM daily_traffic_snapshots WHERE last_sent_date = ? LIMIT 1",
                        (today_key,),
                    ).fetchone()
                if not already_any:
                    await send_daily_summaries(bot, now_msk=now_msk)
            await asyncio.sleep(poll_seconds)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в наблюдателе ежедневной сводки: %s", exc)
            await asyncio.sleep(poll_seconds)
