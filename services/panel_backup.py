import asyncio
import datetime
import json
import logging
import socket
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from aiogram import Bot
from aiogram.types import BufferedInputFile

from api.panel_client import Panel3XUIClient
from config import ADMIN_IDS, PANEL_URL

logger = logging.getLogger("panel_backup")
BACKUP_DIR = Path("/opt/SLK_BOT_3X-UI/backups")
KEEP_LAST_FILES = 14


async def _detect_server_ip() -> str:
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

    ip_endpoints = (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    )
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for ep in ip_endpoints:
            try:
                async with session.get(ep) as resp:
                    if resp.status == 200:
                        txt = (await resp.text()).strip()
                        if txt:
                            return txt.splitlines()[0].strip()
            except Exception:
                continue

    parsed = urlparse(PANEL_URL)
    if parsed.hostname:
        try:
            return socket.gethostbyname(parsed.hostname)
        except Exception:
            return parsed.hostname
    return socket.gethostname()


def _normalize_config_json_bytes(raw_bytes: bytes) -> bytes:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return b"{}\n"
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and set(parsed.keys()) <= {"success", "msg", "obj"} and "obj" in parsed:
            obj = parsed["obj"]
            if isinstance(obj, str):
                try:
                    obj = json.loads(obj)
                except Exception:
                    pass
            return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        return (json.dumps(parsed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except Exception:
        return raw_bytes


def _cleanup_old_backups(ext: str) -> None:
    if not BACKUP_DIR.exists():
        return
    files = sorted(
        [p for p in BACKUP_DIR.iterdir() if p.is_file() and p.name.endswith(ext)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old_file in files[KEEP_LAST_FILES:]:
        try:
            old_file.unlink()
        except Exception:
            pass


async def run_panel_backup_and_send(bot: Bot) -> tuple[Path, Path]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    client = Panel3XUIClient(timeout=20)

    db_bytes = await client.get_raw_bytes("/server/getDb")
    cfg_raw = await client.get_raw_bytes("/server/getConfigJson")
    cfg_bytes = _normalize_config_json_bytes(cfg_raw)

    ip = await _detect_server_ip()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    prefix = f"{ip}.{now_str}"

    db_path = BACKUP_DIR / f"{prefix}.db"
    json_path = BACKUP_DIR / f"{prefix}.json"

    db_path.write_bytes(db_bytes)
    json_path.write_bytes(cfg_bytes)

    _cleanup_old_backups(".db")
    _cleanup_old_backups(".json")

    caption = f"📦 Бэкап панели 3X-UI\n🖥 Хост: <code>{ip}</code>\n🕒 Время: <code>{now_str}</code>"

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_document(
                chat_id=int(admin_id),
                document=BufferedInputFile(db_bytes, filename=db_path.name),
                caption=caption,
                parse_mode="HTML",
            )
            await bot.send_document(
                chat_id=int(admin_id),
                document=BufferedInputFile(cfg_bytes, filename=json_path.name),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить бэкап админу %s: %s", admin_id, exc)

    return db_path, json_path


def _seconds_until_next_5am() -> float:
    now = datetime.datetime.now()
    target = now.replace(hour=5, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + datetime.timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def daily_backup_loop(bot: Bot) -> None:
    logger.info("Запущен ежедневный планировщик бэкапов 3X-UI в 05:00")
    while True:
        try:
            delay = _seconds_until_next_5am()
            logger.info("Следующий автоматический бэкап через %.0f сек.", delay)
            await asyncio.sleep(delay)
            db_path, json_path = await run_panel_backup_and_send(bot)
            logger.info("Бэкап выполнен и отправлен: %s, %s", db_path.name, json_path.name)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в ежедневном бэкапе 3X-UI: %s", exc)
            await asyncio.sleep(60)
