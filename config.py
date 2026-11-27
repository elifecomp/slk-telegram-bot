import re
import os
from dotenv import load_dotenv

load_dotenv("/opt/SLK_BOT_3X-UI/.env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
raw_admin_ids = os.getenv("ADMIN_ID", "0")
ADMIN_IDS: set[int] = {
    int(part.strip())
    for part in re.split(r"[,;\s]+", raw_admin_ids)
    if part.strip() and re.fullmatch(r"-?\d+", part.strip())
}
ADMIN_ID: int = next(iter(ADMIN_IDS), 0)
PANEL_URL = os.getenv("PANEL_URL", "").strip().rstrip("/")
PANEL_TOKEN = os.getenv("PANEL_TOKEN", "").strip()
