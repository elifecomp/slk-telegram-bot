import os
import sqlite3
from typing import Any

try:
    from config import ADMIN_ID as CONFIG_ADMIN_ID
except Exception:
    CONFIG_ADMIN_ID = None


def resolve_clients_db_path() -> str:
    for env_key in ("CLIENTS_DB_PATH", "DB_PATH", "SQLITE_PATH"):
        val = (os.getenv(env_key) or "").strip()
        if val and os.path.exists(val):
            return val

    candidates = [
        "/opt/SLK_BOT_3X-UI/clients.db",
        "/opt/SLK_BOT_3X-UI/data/clients.db",
        "/opt/SLK_BOT_3X-UI/db/clients.db",
        "clients.db",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path

    for root, dirs, files in os.walk("/opt/SLK_BOT_3X-UI"):
        dirs[:] = [d for d in dirs if d not in ("venv", ".git", "__pycache__")]
        if "clients.db" in files:
            return os.path.join(root, "clients.db")

    return "/opt/SLK_BOT_3X-UI/clients.db"


def ensure_clients_table() -> None:
    db_path = resolve_clients_db_path()
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                login TEXT UNIQUE,
                phone TEXT DEFAULT '',
                name TEXT DEFAULT '',
                registration_date TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                login2 TEXT DEFAULT '',
                birthday TEXT DEFAULT '',
                hwid TEXT DEFAULT '',
                city TEXT DEFAULT ''
            )
            """
        )
        conn.commit()


def _connect() -> sqlite3.Connection:
    db_path = resolve_clients_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_client_by_tg_id(telegram_id: int | str | None) -> dict[str, Any] | None:
    if telegram_id is None:
        return None
    try:
        tg_int = int(telegram_id)
    except (TypeError, ValueError):
        return None

    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return None

    ensure_clients_table()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, telegram_id, login, phone, name, registration_date, is_active, city
            FROM clients
            WHERE telegram_id = ?
            LIMIT 1
            """,
            (tg_int,),
        ).fetchone()
        return dict(row) if row else None


def list_clients(limit: int = 100) -> list[dict[str, Any]]:
    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return []

    ensure_clients_table()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, telegram_id, login, phone, name, registration_date, is_active, login2, birthday, hwid, city
            FROM clients
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_client_by_id(client_id: int | str) -> dict[str, Any] | None:
    try:
        cid = int(client_id)
    except (TypeError, ValueError):
        return None

    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return None

    ensure_clients_table()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, telegram_id, login, phone, name, registration_date, is_active, login2, birthday, hwid, city
            FROM clients
            WHERE id = ?
            LIMIT 1
            """,
            (cid,),
        ).fetchone()
        return dict(row) if row else None


def is_admin_user(user_id: int | str | None) -> bool:
    if user_id is None:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False

    parsed_ids: set[int] = set()
    if CONFIG_ADMIN_ID is not None:
        try:
            parsed_ids.add(int(CONFIG_ADMIN_ID))
        except (TypeError, ValueError):
            pass

    for key in ("ADMIN_ID", "ADMIN_IDS", "ADMINS", "TG_ADMIN_ID", "OWNER_ID"):
        val = (os.getenv(key) or "").strip()
        if val:
            for part in val.replace(";", ",").replace(" ", ",").split(","):
                part = part.strip()
                if part.isdigit():
                    parsed_ids.add(int(part))

    return uid in parsed_ids


ALLOWED_EDIT_FIELDS = {"name", "phone", "city", "birthday"}


def update_client_field(client_id: int | str, field: str, value: str) -> bool:
    if field not in ALLOWED_EDIT_FIELDS:
        return False
    try:
        cid = int(client_id)
    except (TypeError, ValueError):
        return False

    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return False

    clean_value = value.strip()
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE clients SET {field} = ? WHERE id = ?",
            (clean_value, cid),
        )
        conn.commit()
        return cur.rowcount > 0


def ensure_access_tracking_table() -> None:
    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS client_access_notify (
                telegram_id INTEGER PRIMARY KEY,
                access_notified INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def ensure_client_registered(
    telegram_id: int | str,
    name: str | None = None,
    username: str | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    try:
        tg_int = int(telegram_id)
    except (TypeError, ValueError):
        return None, False

    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return None, False

    ensure_clients_table()
    ensure_access_tracking_table()
    display_name = (name or username or f"User {tg_int}").strip()[:100]
    base_login = (username or f"tg_{tg_int}").strip() or f"tg_{tg_int}"

    with _connect() as conn:
        existing = conn.execute(
            """
            SELECT id, telegram_id, login, phone, name, registration_date, is_active, login2, birthday, hwid, city
            FROM clients
            WHERE telegram_id = ?
            LIMIT 1
            """,
            (tg_int,),
        ).fetchone()
        if existing:
            conn.execute(
                "INSERT OR IGNORE INTO client_access_notify (telegram_id, access_notified) VALUES (?, 0)",
                (tg_int,),
            )
            conn.commit()
            return dict(existing), False

        login_candidate = base_login
        suffix = 1
        while conn.execute("SELECT 1 FROM clients WHERE login = ? LIMIT 1", (login_candidate,)).fetchone():
            login_candidate = f"{base_login}_{tg_int}_{suffix}"
            suffix += 1

        conn.execute(
            """
            INSERT INTO clients (telegram_id, login, phone, name, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (tg_int, login_candidate, "", display_name),
        )
        conn.execute(
            "INSERT OR IGNORE INTO client_access_notify (telegram_id, access_notified) VALUES (?, 0)",
            (tg_int,),
        )
        conn.commit()

        created = conn.execute(
            """
            SELECT id, telegram_id, login, phone, name, registration_date, is_active, login2, birthday, hwid, city
            FROM clients
            WHERE telegram_id = ?
            LIMIT 1
            """,
            (tg_int,),
        ).fetchone()
        return (dict(created) if created else None), True


def list_unnotified_clients() -> list[dict[str, Any]]:
    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return []
    ensure_access_tracking_table()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.telegram_id, c.login, c.name
            FROM clients c
            LEFT JOIN client_access_notify n ON n.telegram_id = c.telegram_id
            WHERE c.telegram_id IS NOT NULL
              AND COALESCE(n.access_notified, 0) = 0
            ORDER BY c.id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def mark_access_notified(telegram_id: int | str, notified: bool = True) -> None:
    try:
        tg_int = int(telegram_id)
    except (TypeError, ValueError):
        return
    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return
    ensure_access_tracking_table()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO client_access_notify (telegram_id, access_notified, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id) DO UPDATE SET
                access_notified = excluded.access_notified,
                updated_at = CURRENT_TIMESTAMP
            """,
            (tg_int, 1 if notified else 0),
        )
        conn.commit()


def ensure_manual_access_table() -> None:
    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manual_allowed_users (
                telegram_id INTEGER PRIMARY KEY,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def has_manual_user_access(telegram_id: int | str | None) -> bool:
    if telegram_id is None:
        return False
    try:
        tg_int = int(telegram_id)
    except (TypeError, ValueError):
        return False
    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return False
    ensure_manual_access_table()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM manual_allowed_users WHERE telegram_id = ? LIMIT 1",
            (tg_int,),
        ).fetchone()
        return row is not None


def grant_manual_user_access(
    telegram_id: int | str,
    name: str | None = None,
    username: str | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    client_row, is_new = ensure_client_registered(
        telegram_id=telegram_id,
        name=name,
        username=username,
    )
    try:
        tg_int = int(telegram_id)
    except (TypeError, ValueError):
        return client_row, is_new

    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return client_row, is_new

    ensure_manual_access_table()
    ensure_access_tracking_table()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO manual_allowed_users (telegram_id) VALUES (?)",
            (tg_int,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO client_access_notify (telegram_id, access_notified) VALUES (?, 1)",
            (tg_int,),
        )
        if name and name.strip():
            conn.execute(
                "UPDATE clients SET name = ?, is_active = 1 WHERE telegram_id = ?",
                (name.strip()[:100], tg_int),
            )
        else:
            conn.execute(
                "UPDATE clients SET is_active = 1 WHERE telegram_id = ?",
                (tg_int,),
            )
        if username and username.strip():
            clean_un = username.strip().lstrip("@")
            if clean_un:
                existing_login = conn.execute(
                    "SELECT login FROM clients WHERE telegram_id = ? LIMIT 1",
                    (tg_int,),
                ).fetchone()
                cur_login = str(existing_login["login"] or "") if existing_login else ""
                if not cur_login or cur_login.startswith("tg_"):
                    candidate = clean_un
                    suffix = 1
                    while conn.execute(
                        "SELECT 1 FROM clients WHERE login = ? AND telegram_id != ? LIMIT 1",
                        (candidate, tg_int),
                    ).fetchone():
                        candidate = f"{clean_un}_{tg_int}_{suffix}"
                        suffix += 1
                    conn.execute(
                        "UPDATE clients SET login = ? WHERE telegram_id = ?",
                        (candidate, tg_int),
                    )
        conn.commit()
        updated = conn.execute(
            """
            SELECT id, telegram_id, login, phone, name, registration_date, is_active, login2, birthday, hwid, city
            FROM clients
            WHERE telegram_id = ?
            LIMIT 1
            """,
            (tg_int,),
        ).fetchone()
        return (dict(updated) if updated else client_row), is_new


def sync_client_profile_from_tg(
    telegram_id: int | str,
    full_name: str | None = None,
    username: str | None = None,
) -> dict[str, Any] | None:
    try:
        tg_int = int(telegram_id)
    except (TypeError, ValueError):
        return None
    db_path = resolve_clients_db_path()
    if not os.path.exists(db_path):
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, login FROM clients WHERE telegram_id = ? LIMIT 1",
            (tg_int,),
        ).fetchone()
        if not row:
            return None
        cur_name = str(row["name"] or "").strip()
        cur_login = str(row["login"] or "").strip()
        if full_name and full_name.strip() and (not cur_name or cur_name.startswith("User ")):
            conn.execute(
                "UPDATE clients SET name = ? WHERE telegram_id = ?",
                (full_name.strip()[:100], tg_int),
            )
        if username and username.strip() and (not cur_login or cur_login.startswith("tg_")):
            clean_un = username.strip().lstrip("@")
            if clean_un and not conn.execute(
                "SELECT 1 FROM clients WHERE login = ? AND telegram_id != ? LIMIT 1",
                (clean_un, tg_int),
            ).fetchone():
                conn.execute(
                    "UPDATE clients SET login = ? WHERE telegram_id = ?",
                    (clean_un, tg_int),
                )
        conn.commit()
        updated = conn.execute(
            """
            SELECT id, telegram_id, login, phone, name, registration_date, is_active, login2, birthday, hwid, city
            FROM clients
            WHERE telegram_id = ?
            LIMIT 1
            """,
            (tg_int,),
        ).fetchone()
        return dict(updated) if updated else None
