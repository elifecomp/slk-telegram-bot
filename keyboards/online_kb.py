from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.online_cache import OnlineClientEntry


def build_online_keyboard(
    batch_id: str,
    clients: list[tuple[str, OnlineClientEntry]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for idx, (slot_id, entry) in enumerate(clients, start=1):
        btn_text = f"{idx}. {entry.email}"
        if entry.inbound_remark:
            btn_text += f" • {entry.inbound_remark}"
        if len(btn_text) > 30:
            btn_text = btn_text[:27] + "..."

        row.append(
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"onl_c:{batch_id}:{slot_id}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            text="🔄 Обновить список",
            callback_data=f"onl_ref:{batch_id}",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_client_detail_keyboard(batch_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ К списку онлайн",
                    callback_data=f"onl_ref:{batch_id}",
                )
            ]
        ]
    )
