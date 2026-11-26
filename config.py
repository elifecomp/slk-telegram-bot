import os
from dotenv import load_dotenv

load_dotenv("/opt/SLK_BOT_3X-UI/.env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip())
PANEL_URL = os.getenv("PANEL_URL", "").strip().rstrip("/")
PANEL_TOKEN = os.getenv("PANEL_TOKEN", "").strip()
