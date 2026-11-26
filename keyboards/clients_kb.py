from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.clients_cache import InboundSummary


def build_inbounds_select_keyboard(
    sid: str,
    inbounds: list[tuple[str, InboundSummary]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for ib_slot, ib in inbounds:
        count = len(ib.clients)
        label = f"{ib.remark} ({count})"
        if len(label) > 28:
            label = label[:25] + "..."
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"cl_ib:{sid}:{ib_slot}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_inbound_clients_keyboard(
    sid: str,
    ib_slot: str,
    clients: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for idx, (c_slot, email) in enumerate(clients, start=1):
        btn_text = f"{idx}. {email}"
        if len(btn_text) > 30:
            btn_text = btn_text[:27] + "..."
        row.append(
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"cl_vw:{sid}:{c_slot}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            text="⬅️ К выбору инбаунда",
            callback_data=f"cl_back_ib:{sid}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_client_actions_keyboard(
    sid: str,
    c_slot: str,
    ib_slot: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Сброс трафика",
                    callback_data=f"cl_rst:{sid}:{c_slot}",
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить имя",
                    callback_data=f"cl_ren:{sid}:{c_slot}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⛔ Отключить",
                    callback_data=f"cl_off:{sid}:{c_slot}",
                ),
                InlineKeyboardButton(
                    text="✅ Включить",
                    callback_data=f"cl_on:{sid}:{c_slot}",
                ),
                InlineKeyboardButton(
                    text="📦 Изменить ГБ",
                    callback_data=f"cl_gb:{sid}:{c_slot}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К клиентам",
                    callback_data=f"cl_ib:{sid}:{ib_slot}",
                ),
                InlineKeyboardButton(
                    text="🏠 Инбаунды",
                    callback_data=f"cl_back_ib:{sid}",
                ),
            ],
        ]
    )


def build_cancel_input_keyboard(sid: str, c_slot: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"cl_vw:{sid}:{c_slot}",
                )
            ]
        ]
    )
