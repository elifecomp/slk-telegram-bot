from html import escape
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    FSInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    Message,
    ReplyKeyboardMarkup,
)

from keyboards.main_kb import get_main_keyboard
from services.clients_db import (
    get_client_by_id,
    grant_manual_user_access,
    get_client_by_tg_id,
    is_admin_user,
    list_clients,
    update_client_field,
)

router = Router(name="client_portal")

BTN_CLIENT_PANEL = "👤 Панель клиента"
BTN_USERS_LIST = "👥 Пользователи"
BTN_ADD_USER_TG = "➕ Добавить пользователя по ТГ"
REQUEST_ADD_USER_ID = 3101
BTN_MY_SUB = "📡 Моя подписка"
BTN_APP = "📱 Приложение"
BTN_BACK_ADMIN = "⬅️ В админ-панель"

FIELD_LABELS = {
    "name": "имя",
    "phone": "номер телефона",
    "city": "город",
    "birthday": "дату рождения (например, 02.03.1983)",
}


class EditClientState(StatesGroup):
    waiting_value = State()


def get_admin_keyboard_with_portal() -> ReplyKeyboardMarkup:
    return get_main_keyboard()


def get_users_manage_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=BTN_ADD_USER_TG,
                    request_users=KeyboardButtonRequestUsers(
                        request_id=REQUEST_ADD_USER_ID,
                        user_is_bot=False,
                        max_quantity=1,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ],
            [KeyboardButton(text=BTN_BACK_ADMIN)],
        ],
        resize_keyboard=True,
    )


def get_client_reply_keyboard(include_back_admin: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=BTN_MY_SUB), KeyboardButton(text=BTN_APP)],
    ]
    if include_back_admin:
        rows.append([KeyboardButton(text=BTN_BACK_ADMIN)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел...",
    )


def build_users_inline_keyboard(users: list[dict]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for u in users:
        uid = u.get("id")
        display_name = (u.get("name") or u.get("login") or f"ID {uid}").strip()
        row.append(
            InlineKeyboardButton(
                text=display_name,
                callback_data=f"portal_user:{uid}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_user_card_keyboard(client_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Изменить имя", callback_data=f"edit_user:{client_id}:name"),
                InlineKeyboardButton(text="Изменить номер", callback_data=f"edit_user:{client_id}:phone"),
            ],
            [
                InlineKeyboardButton(text="Изменить город", callback_data=f"edit_user:{client_id}:city"),
                InlineKeyboardButton(text="Изменить рождение", callback_data=f"edit_user:{client_id}:birthday"),
            ],
            [
                InlineKeyboardButton(text="⬅️ К списку пользователей", callback_data="portal_users_back"),
            ],
        ]
    )


def _extract_model_and_client(dev: dict | str) -> tuple[str | None, str | None]:
    if isinstance(dev, str):
        s = dev.strip()
        if "(" in s and ")" in s:
            inner = s[s.find("(") + 1:s.rfind(")")].strip()
            return (inner or None), s
        return None, (s or None)

    if not isinstance(dev, dict):
        return None, None

    model = (
        dev.get("model")
        or dev.get("deviceModel")
        or dev.get("device_model")
        or dev.get("device")
        or dev.get("deviceName")
        or dev.get("device_name")
    )
    client_app = (
        dev.get("userAgent")
        or dev.get("user_agent")
        or dev.get("client")
        or dev.get("app")
        or dev.get("name")
    )

    model_str = str(model).strip() if model not in (None, "") else None
    client_str = str(client_app).strip() if client_app not in (None, "") else None

    if not model_str and client_str and "(" in client_str and ")" in client_str:
        inner = client_str[client_str.find("(") + 1:client_str.rfind(")")].strip()
        if inner:
            model_str = inner

    if model_str and any(x in model_str for x in ("CFNetwork/", "Darwin/", "INCY/")):
        if not client_str:
            client_str = model_str
        model_str = None

    return model_str, client_str


async def _resolve_panel_device_info(client_row: dict) -> tuple[str | None, str | None]:
    emails: list[str] = []
    for key in ("login", "login2"):
        val = str(client_row.get(key) or "").strip()
        if val and val not in emails:
            emails.append(val)

    if not emails:
        return None, None

    try:
        from api.hwid_api import fetch_client_hwid_devices
    except Exception:
        return None, None

    models: list[str] = []
    clients: list[str] = []

    for email in emails:
        try:
            devices, _ = await fetch_client_hwid_devices(email)
        except Exception:
            continue
        if not devices:
            continue

        for dev in devices:
            m, c = _extract_model_and_client(dev)
            if m and m not in models:
                models.append(m)
            if c and c not in clients:
                clients.append(c)

        if models or clients:
            break

    return (", ".join(models) if models else None), (", ".join(clients) if clients else None)


def _format_user_card_text(found: dict, panel_device: tuple[str | None, str | None] | str | None = None) -> str:
    name = escape(str(found.get("name") or "—"))
    login = escape(str(found.get("login") or "—"))
    tg_id = escape(str(found.get("telegram_id") or "—"))
    phone = escape(str(found.get("phone") or "—"))
    city = escape(str(found.get("city") or "—"))
    birthday = escape(str(found.get("birthday") or "—"))
    reg_date = escape(str(found.get("registration_date") or "—"))
    status = "🟢 Активен" if found.get("is_active", 1) else "⚪ Отключён"

    db_model = str(found.get("hwid") or "").strip()
    panel_model: str | None = None
    panel_client: str | None = None

    if isinstance(panel_device, tuple):
        panel_model, panel_client = panel_device
    elif isinstance(panel_device, str) and panel_device.strip():
        panel_client = panel_device.strip()

    final_model = panel_model or db_model or "—"
    lines = [
        f"👤 <b>{name}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"• Статус: <code>{status}</code>",
        f"• Логин: <code>{login}</code>",
        f"• Telegram ID: <code>{tg_id}</code>",
        f"• Телефон: <code>{phone}</code>",
        f"• Город: <code>{city}</code>",
        f"• Дата рождения: <code>{birthday}</code>",
        f"• Модель телефона: <code>{escape(final_model)}</code>",
    ]
    if panel_client and panel_client != final_model:
        lines.append(f"• Клиент (панель): <code>{escape(panel_client)}</code>")
    lines.append(f"• Регистрация: <code>{reg_date}</code>")
    return "\n".join(lines)


async def send_client_menu(message: Message, client_name: str, is_preview: bool = False) -> None:
    title = "👁 <b>ПАНЕЛЬ КЛИЕНТА (ПРЕВЬЮ)</b>" if is_preview else "👋 <b>ЛИЧНЫЙ КАБИНЕТ</b>"
    text = (
        f"{title}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Пользователь: <b>{escape(client_name)}</b>\n\n"
        "Выберите раздел на клавиатуре ниже:"
    )
    await message.answer(
        text,
        reply_markup=get_client_reply_keyboard(include_back_admin=is_preview),
        parse_mode="HTML",
    )


@router.message(F.text == BTN_CLIENT_PANEL)
async def open_client_panel_preview(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else None
    if not is_admin_user(uid):
        return
    await state.clear()
    db_client = get_client_by_tg_id(uid) if uid else None
    display_name = (
        str((db_client or {}).get("name") or "").strip()
        or (message.from_user.full_name if message.from_user and message.from_user.full_name else "")
        or "Администратор"
    )
    await send_client_menu(message, client_name=display_name, is_preview=True)


@router.message(F.text == BTN_BACK_ADMIN)
async def back_to_admin_panel(message: Message, state: FSMContext) -> None:
    if not is_admin_user(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await message.answer(
        "🛠 <b>АДМИН-ПАНЕЛЬ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Вы вернулись в меню администратора.",
        reply_markup=get_admin_keyboard_with_portal(),
        parse_mode="HTML",
    )


@router.message(F.text == BTN_USERS_LIST)
async def open_users_inline_list(message: Message, state: FSMContext) -> None:
    if not is_admin_user(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    users = list_clients()
    if not users:
        await message.answer(
            "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "В базе <code>clients.db</code> пока нет пользователей.\n\n"
            "Нажмите <b>«➕ Добавить пользователя по ТГ»</b> на клавиатуре ниже, чтобы выбрать контакт.",
            reply_markup=get_users_manage_reply_keyboard(),
            parse_mode="HTML",
        )
        return

    await message.answer(
        f"👥 <b>ПОЛЬЗОВАТЕЛИ</b> (<code>{len(users)}</code>)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите пользователя из списка или нажмите <b>«➕ Добавить пользователя по ТГ»</b> ниже:",
        reply_markup=build_users_inline_keyboard(users),
        parse_mode="HTML",
    )
    await message.answer(
        "👇 Управление пользователями:",
        reply_markup=get_users_manage_reply_keyboard(),
    )


@router.message(F.users_shared)
async def on_users_shared_add_client(message: Message, state: FSMContext) -> None:
    if not is_admin_user(message.from_user.id if message.from_user else None):
        return
    shared = message.users_shared
    if not shared or shared.request_id != REQUEST_ADD_USER_ID or not shared.users:
        return

    await state.clear()
    picked = shared.users[0]
    target_tg_id = int(picked.user_id)
    first_name = getattr(picked, "first_name", None) or ""
    last_name = getattr(picked, "last_name", None) or ""
    full_name = " ".join(p for p in (first_name.strip(), last_name.strip()) if p).strip() or None
    username = getattr(picked, "username", None)

    client_row, is_new = grant_manual_user_access(
        telegram_id=target_tg_id,
        name=full_name,
        username=username,
    )
    saved_name = escape(str((client_row or {}).get("name") or full_name or f"User {target_tg_id}"))
    saved_login = escape(str((client_row or {}).get("login") or (f"@{username}" if username else f"tg_{target_tg_id}")))
    status_title = "✅ <b>ПОЛЬЗОВАТЕЛЬ ДОБАВЛЕН</b>" if is_new else "✅ <b>ДОСТУП ОБНОВЛЁН</b>"

    await message.answer(
        f"{status_title}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• Имя: <b>{saved_name}</b>\n"
        f"• Логин: <code>{saved_login}</code>\n"
        f"• Telegram ID: <code>{target_tg_id}</code>\n\n"
        "Данные сохранены в <code>clients.db</code>. "
        "Когда пользователь зайдёт в бот и нажмёт <code>/start</code>, "
        "он сразу получит доступ в личный кабинет.",
        reply_markup=get_users_manage_reply_keyboard(),
        parse_mode="HTML",
    )

    users = list_clients()
    if users:
        await message.answer(
            f"👥 <b>ПОЛЬЗОВАТЕЛИ</b> (<code>{len(users)}</code>)\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Обновлённый список пользователей:",
            reply_markup=build_users_inline_keyboard(users),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "portal_users_back")
async def on_users_back_click(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user.id if callback.from_user else None):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.clear()
    users = list_clients()
    if not users:
        await callback.answer("Список пуст", show_alert=True)
        return

    await callback.message.edit_text(
        f"👥 <b>ПОЛЬЗОВАТЕЛИ</b> (<code>{len(users)}</code>)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите пользователя:",
        reply_markup=build_users_inline_keyboard(users),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("portal_user:"))
async def on_user_button_click(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user.id if callback.from_user else None):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    await state.clear()
    raw_id = callback.data.split(":", 1)[1]
    found = get_client_by_id(raw_id)
    if not found:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    panel_device = await _resolve_panel_device_info(found)
    await callback.message.edit_text(
        _format_user_card_text(found, panel_device=panel_device),
        reply_markup=build_user_card_keyboard(found["id"]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_user:"))
async def on_edit_user_field_click(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user.id if callback.from_user else None):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    _, raw_id, field = parts
    if field not in FIELD_LABELS:
        await callback.answer("Поле недоступно для редактирования", show_alert=True)
        return

    found = get_client_by_id(raw_id)
    if not found:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    await state.set_state(EditClientState.waiting_value)
    await state.update_data(client_id=int(raw_id), field=field)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_edit_user:{raw_id}")]
        ]
    )
    user_name = escape(str(found.get("name") or found.get("login") or raw_id))
    await callback.message.answer(
        f"✏️ Редактирование клиента <b>{user_name}</b>\n"
        f"Введите новое значение для поля <b>{FIELD_LABELS[field]}</b>:",
        reply_markup=cancel_kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_edit_user:"))
async def on_cancel_edit_user(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user.id if callback.from_user else None):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    raw_id = callback.data.split(":", 1)[1]
    await state.clear()
    found = get_client_by_id(raw_id)
    if found:
        panel_device = await _resolve_panel_device_info(found)
        await callback.message.edit_text(
            _format_user_card_text(found, panel_device=panel_device),
            reply_markup=build_user_card_keyboard(found["id"]),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text("❌ Редактирование отменено.")
    await callback.answer("Отменено")


@router.message(EditClientState.waiting_value)
async def process_edit_user_value(message: Message, state: FSMContext) -> None:
    if not is_admin_user(message.from_user.id if message.from_user else None):
        await state.clear()
        return

    new_val = (message.text or "").strip()
    if not new_val:
        await message.answer("⚠️ Отправьте текстовое значение.")
        return

    data = await state.get_data()
    client_id = data.get("client_id")
    field = data.get("field")
    await state.clear()

    if not client_id or not field or not update_client_field(client_id, field, new_val):
        await message.answer("⚠️ Не удалось обновить данные в базе.")
        return

    found = get_client_by_id(client_id)
    if not found:
        await message.answer("✅ Значение обновлено.")
        return

    panel_device = await _resolve_panel_device_info(found)
    await message.answer(
        f"✅ Данные обновлены!\n\n{_format_user_card_text(found, panel_device=panel_device)}",
        reply_markup=build_user_card_keyboard(found["id"]),
        parse_mode="HTML",
    )


def _fmt_bytes(val) -> str:
    if val is None or isinstance(val, bool):
        return "—"
    try:
        num = float(val)
    except (TypeError, ValueError):
        return "—"
    if num <= 0:
        return "0 Б" if num == 0 else "—"
    try:
        from services.format_bytes import format_bytes
        return str(format_bytes(num))
    except Exception:
        for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
            if num < 1024 or unit == "ТБ":
                return f"{num:.1f} {unit}" if unit != "Б" else f"{int(num)} {unit}"
            num /= 1024.0
        return "—"


def _fmt_expiry(raw_ts) -> str:
    if raw_ts in (None, "", 0, "0", False):
        return "Бессрочно"
    try:
        ts = int(raw_ts)
    except (TypeError, ValueError):
        return str(raw_ts)
    if ts <= 0:
        return "Бессрочно"
    if ts > 10_000_000_000:
        ts //= 1000
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    return dt.strftime("%d.%m.%Y %H:%M")


async def _build_subscription_text(uid: int, client_row: dict | None) -> str:
    emails: list[str] = []
    for key in ("login", "login2"):
        v = str((client_row or {}).get(key) or "").strip()
        if v and v not in emails:
            emails.append(v)

    profile: dict = {}
    raw_client: dict = {}
    inbound_id = None
    matched_email: str | None = None
    linked_inbound_ids: list[str] = []

    up_sum = 0.0
    down_sum = 0.0
    found_stats = False
    limit_num = 0.0
    expiry_candidates = []
    enable_candidates = []
    sub_id_candidate = None

    try:
        from api.client_detail_api import fetch_client_profile
        from api.clients_manage_api import get_raw_client_and_inbound
        from api.inbounds_api import fetch_inbounds
    except Exception:
        fetch_client_profile = None
        get_raw_client_and_inbound = None
        fetch_inbounds = None

    for em in emails:
        if fetch_client_profile:
            try:
                p = await fetch_client_profile(em)
                if isinstance(p, dict) and p:
                    profile = p
                    matched_email = em
            except Exception:
                pass
        if get_raw_client_and_inbound:
            try:
                rc, ib_id = await get_raw_client_and_inbound(em)
                if isinstance(rc, dict) and rc:
                    raw_client = rc
                    inbound_id = ib_id
                    matched_email = matched_email or em
                    break
            except Exception:
                pass

    if not matched_email and emails:
        matched_email = emails[0]

    target_emails = set(emails)
    if matched_email:
        target_emails.add(matched_email)

    if fetch_inbounds and target_emails:
        try:
            ok, inbounds_list, _ = await fetch_inbounds()
        except Exception:
            ok, inbounds_list = False, []

        if ok and isinstance(inbounds_list, list):
            for ib in inbounds_list:
                if not isinstance(ib, dict):
                    continue
                ib_num = ib.get("id")
                stats_list = ib.get("clientStats") or []
                if isinstance(stats_list, list):
                    for st in stats_list:
                        if not isinstance(st, dict):
                            continue
                        st_email = str(st.get("email") or "").strip()
                        if st_email in target_emails:
                            matched_email = matched_email or st_email
                            found_stats = True
                            try:
                                up_sum += float(st.get("up") or 0)
                            except (TypeError, ValueError):
                                pass
                            try:
                                down_sum += float(st.get("down") or 0)
                            except (TypeError, ValueError):
                                pass
                            for lk in ("totalGB", "total"):
                                lv = st.get(lk)
                                if lv not in (None, "", 0, "0"):
                                    try:
                                        lf = float(lv)
                                        if lf > limit_num:
                                            limit_num = lf
                                    except (TypeError, ValueError):
                                        pass
                            if st.get("expiryTime") not in (None, "", 0, "0"):
                                expiry_candidates.append(st.get("expiryTime"))
                            if "enable" in st and st.get("enable") is not None:
                                enable_candidates.append(st.get("enable"))
                            if ib_num is not None and str(ib_num) not in linked_inbound_ids:
                                linked_inbound_ids.append(str(ib_num))
                                if inbound_id is None:
                                    inbound_id = ib_num

                settings_raw = ib.get("settings")
                settings_dict = {}
                if isinstance(settings_raw, dict):
                    settings_dict = settings_raw
                elif isinstance(settings_raw, str) and settings_raw.strip():
                    try:
                        import json
                        parsed_s = json.loads(settings_raw)
                        if isinstance(parsed_s, dict):
                            settings_dict = parsed_s
                    except Exception:
                        pass

                for c in settings_dict.get("clients") or []:
                    if isinstance(c, dict) and str(c.get("email") or "").strip() in target_emails:
                        if not raw_client:
                            raw_client = dict(c)
                        if ib_num is not None and str(ib_num) not in linked_inbound_ids:
                            linked_inbound_ids.append(str(ib_num))
                            if inbound_id is None:
                                inbound_id = ib_num
                        if c.get("expiryTime") not in (None, "", 0, "0"):
                            expiry_candidates.append(c.get("expiryTime"))
                        if "enable" in c and c.get("enable") is not None:
                            enable_candidates.append(c.get("enable"))
                        if c.get("subId") and not sub_id_candidate:
                            sub_id_candidate = c.get("subId")
                        for lk in ("totalGB", "total"):
                            lv = c.get(lk)
                            if lv not in (None, "", 0, "0"):
                                try:
                                    lf = float(lv)
                                    if lf > limit_num:
                                        limit_num = lf
                                except (TypeError, ValueError):
                                    pass

    sub_client = profile.get("client") if isinstance(profile.get("client"), dict) else {}
    merged: dict = {}
    merged.update(raw_client)
    merged.update(sub_client)
    if isinstance(profile, dict):
        for k, v in profile.items():
            if k != "client":
                merged.setdefault(k, v)

    if not found_stats:
        for uk in ("up",):
            if merged.get(uk) not in (None, ""):
                try:
                    up_sum += float(merged.get(uk) or 0)
                    found_stats = True
                except (TypeError, ValueError):
                    pass
        for dk in ("down",):
            if merged.get(dk) not in (None, ""):
                try:
                    down_sum += float(merged.get(dk) or 0)
                    found_stats = True
                except (TypeError, ValueError):
                    pass

    if limit_num <= 0:
        for lk in ("totalGB", "total"):
            lv = merged.get(lk)
            if lv not in (None, "", 0, "0"):
                try:
                    limit_num = float(lv)
                    break
                except (TypeError, ValueError):
                    pass

    name = escape(str((client_row or {}).get("name") or merged.get("comment") or merged.get("email") or f"ID {uid}"))
    email_disp = escape(str(matched_email or merged.get("email") or "—"))

    if enable_candidates:
        enabled_raw = any(bool(x) for x in enable_candidates)
    else:
        enabled_raw = merged.get("enable")

    if enabled_raw is None:
        status_text = "🟢 Активна" if (merged or found_stats or (client_row or {}).get("is_active", 1)) else "⚪ Неактивна"
    else:
        status_text = "🟢 Активна" if bool(enabled_raw) else "🔴 Отключена"

    used_total = up_sum + down_sum
    used_str = _fmt_bytes(used_total) if (found_stats or used_total > 0) else "—"

    if limit_num > 0:
        limit_str = _fmt_bytes(limit_num)
        remain_str = _fmt_bytes(max(0.0, limit_num - used_total))
    else:
        limit_str = "Безлимит"
        remain_str = "—"

    expiry_raw = expiry_candidates[0] if expiry_candidates else (
        merged.get("expiryTime") if merged.get("expiryTime") is not None else merged.get("expiry_time")
    )
    expiry_str = _fmt_expiry(expiry_raw)

    lines = [
        "📡 <b>МОЯ ПОДПИСКА</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"• Клиент: <b>{name}</b>",
        f"• Аккаунт (email): <code>{email_disp}</code>",
        f"• Статус: <code>{status_text}</code>",
        f"• Использовано: <code>{used_str}</code>",
        f"• Лимит трафика: <code>{limit_str}</code>",
    ]
    if remain_str != "—":
        lines.append(f"• Остаток трафика: <code>{remain_str}</code>")
    lines.append(f"• Срок действия: <code>{escape(expiry_str)}</code>")
    if inbound_id is not None:
        lines.append(f"• Входящий (Inbound): <code>#{escape(str(inbound_id))}</code>")

    sub_id = sub_id_candidate or merged.get("subId") or profile.get("subId")
    if sub_id:
        lines.append(f"• ID подписки: <code>{escape(str(sub_id))}</code>")

    return "\n".join(lines)


@router.message(F.text == BTN_MY_SUB)
async def stub_my_subscription(message: Message) -> None:
    uid = message.from_user.id if message.from_user else None
    if uid is None:
        return
    client = get_client_by_tg_id(uid)
    if not client and not is_admin_user(uid):
        return

    text = await _build_subscription_text(uid, client)
    await message.answer(text, parse_mode="HTML")


def build_app_platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="iPhone", callback_data="client_app:iphone"),
                InlineKeyboardButton(text="Android", callback_data="client_app:android"),
            ]
        ]
    )


@router.message(F.text == BTN_APP)
async def stub_client_app(message: Message) -> None:
    uid = message.from_user.id if message.from_user else None
    client = get_client_by_tg_id(uid)
    if not client and not is_admin_user(uid):
        return

    await message.answer(
        "📱 <b>ПРИЛОЖЕНИЕ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите платформу:",
        reply_markup=build_app_platform_keyboard(),
        parse_mode="HTML",
    )


def _find_latest_apk_in_apps() -> str | None:
    import os
    apps_dir = "/opt/SLK_BOT_3X-UI/apps"
    if not os.path.isdir(apps_dir):
        return None
    apk_files = []
    for name in os.listdir(apps_dir):
        full_path = os.path.join(apps_dir, name)
        if os.path.isfile(full_path) and name.lower().endswith(".apk"):
            try:
                mtime = os.path.getmtime(full_path)
            except OSError:
                mtime = 0.0
            apk_files.append((mtime, full_path))
    if not apk_files:
        return None
    apk_files.sort(key=lambda item: item[0], reverse=True)
    return apk_files[0][1]


@router.callback_query(F.data.startswith("client_app:"))
async def on_client_app_platform(callback: CallbackQuery) -> None:
    uid = callback.from_user.id if callback.from_user else None
    client = get_client_by_tg_id(uid)
    if not client and not is_admin_user(uid):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    platform = callback.data.split(":", 1)[1]
    if platform == "iphone":
        await callback.answer("Открываю ссылку для iPhone")
        if callback.message:
            app_url = "https://apps.apple.com/us/app/incy/id6756943388"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=" Скачать в App Store", url=app_url)]
                ]
            )
            await callback.message.answer(
                f"📱 <b>iPhone (App Store)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Ссылка на приложение: <a href=\"{app_url}\">{app_url}</a>",
                reply_markup=kb,
                parse_mode="HTML",
            )
        return

    apk_path = _find_latest_apk_in_apps()
    if not apk_path:
        await callback.answer("APK-файл не найден", show_alert=True)
        if callback.message:
            await callback.message.answer(
                "⚠️ В папке <code>apps</code> пока нет <b>.apk</b> файла.",
                parse_mode="HTML",
            )
        return

    await callback.answer("Отправляю APK...")
    if callback.message:
        import os
        filename = os.path.basename(apk_path)
        await callback.message.answer_document(
            document=FSInputFile(apk_path, filename=filename),
            caption=f"📲 <b>Android ({escape(filename)})</b>",
            parse_mode="HTML",
        )
