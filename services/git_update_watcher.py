import asyncio
import logging
import socket
import sqlite3
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from aiogram import Bot

from config import ADMIN_IDS
from services.clients_db import resolve_clients_db_path

logger = logging.getLogger("git_update_watcher")
REPO_DIR = Path("/opt/SLK_BOT_3X-UI")


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(resolve_clients_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS git_update_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_commit_hash TEXT NOT NULL DEFAULT '',
                notified_at TEXT NOT NULL DEFAULT ''
            )
            """
        )


def _get_last_notified_hash() -> str:
    _ensure_table()
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT last_commit_hash FROM git_update_state WHERE id = 1"
        ).fetchone()
        return str(row["last_commit_hash"] or "").strip() if row else ""


def _set_last_notified_hash(commit_hash: str) -> None:
    _ensure_table()
    now_iso = datetime.now(timezone.utc).isoformat()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO git_update_state (id, last_commit_hash, notified_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_commit_hash = excluded.last_commit_hash,
                notified_at = excluded.notified_at
            """,
            (commit_hash.strip(), now_iso),
        )


def _run_git(args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_DIR), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()
    except Exception:
        return None


def get_current_git_info() -> dict | None:
    full_hash = _run_git(["rev-parse", "HEAD"])
    if not full_hash:
        return None

    short_hash = _run_git(["rev-parse", "--short", "HEAD"]) or full_hash[:7]
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"]) or "HEAD"
    commit_msg = _run_git(["log", "-1", "--pretty=%B"]) or "(без описания коммита)"
    commit_date = _run_git(["log", "-1", "--format=%ci"]) or ""

    return {
        "full_hash": full_hash,
        "short_hash": short_hash,
        "branch": branch,
        "message": commit_msg.strip(),
        "date": commit_date.strip(),
    }


def _detect_local_ip() -> str:
    for target in ("1.1.1.1", "8.8.8.8"):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            sock.connect((target, 80))
            ip = sock.getsockname()[0]
            sock.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
    return socket.gethostname()


def _build_update_card(info: dict) -> str:
    host_ip = _detect_local_ip()
    hostname = socket.gethostname()
    short_hash = escape(str(info.get("short_hash") or ""))
    branch = escape(str(info.get("branch") or ""))
    commit_date = escape(str(info.get("date") or ""))
    msg_text = str(info.get("message") or "").strip()
    if len(msg_text) > 3000:
        msg_text = msg_text[:3000] + "\n…"

    lines = [
        "🚀 <b>БОТ ОБНОВЛЁН С GITHUB</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🖥 Сервер: <code>{escape(host_ip)}</code> (<b>{escape(hostname)}</b>)",
        f"📌 Коммит: <code>{short_hash}</code> (<code>{branch}</code>)",
    ]
    if commit_date:
        lines.append(f"🕒 Дата коммита: <code>{commit_date}</code>")
    lines.extend([
        "",
        "📝 <b>Описание изменений:</b>",
        escape(msg_text),
    ])
    return "\n".join(lines)


async def notify_if_new_git_commit(bot: Bot) -> bool:
    """Проверяет текущий HEAD репозитория и при новом коммите отправляет карточку админам."""
    info = get_current_git_info()
    if not info:
        return False

    full_hash = str(info.get("full_hash") or "").strip()
    if not full_hash:
        return False

    last_hash = _get_last_notified_hash()
    if not last_hash:
        # Первый запуск на сервере — фиксируем текущий коммит без лишнего шума
        _set_last_notified_hash(full_hash)
        return False

    if full_hash == last_hash:
        return False

    card_text = _build_update_card(info)
    sent_any = False

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=card_text,
                parse_mode="HTML",
            )
            sent_any = True
        except Exception as exc:
            logger.warning("Не удалось отправить карточку обновления Git админу %s: %s", admin_id, exc)

    if sent_any or not ADMIN_IDS:
        _set_last_notified_hash(full_hash)

    return sent_any


async def watch_git_update_loop(bot: Bot, poll_seconds: int = 120) -> None:
    """Проверяет появление нового коммита после запуска и периодически в фоне."""
    try:
        await notify_if_new_git_commit(bot)
    except Exception as exc:
        logger.warning("Ошибка первичной проверки обновления Git: %s", exc)

    while True:
        try:
            await asyncio.sleep(poll_seconds)
            await notify_if_new_git_commit(bot)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в наблюдателе обновления Git: %s", exc)
