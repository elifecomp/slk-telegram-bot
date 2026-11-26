from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_hosts_list_keyboard(hosts: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, h in enumerate(hosts):
        gid = str(h.get("groupId") or idx)
        remark = str(h.get("remark") or "").strip()
        endpoints = h.get("hosts") or []
        first_ep = str(endpoints[0]).strip() if endpoints else ""
        title = remark or first_ep or f"Хост #{idx + 1}"
        icon = "🔴" if h.get("isDisabled") else "🟢"
        label = f"{icon} {title}"
        if len(label) > 36:
            label = label[:33] + "..."
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"hst_vw:{idx}:{gid[:12]}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="➕ Добавить хост", callback_data="hst_add"),
        InlineKeyboardButton(text="🔄 Обновить", callback_data="hst_ref"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_host_detail_keyboard(idx: int, is_disabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "✅ Включить" if is_disabled else "⛔ Выключить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=toggle_text, callback_data=f"hst_tgl:{idx}"),
            ],
            [
                InlineKeyboardButton(text="✏️ Примечание", callback_data=f"hst_fld:{idx}:remark"),
                InlineKeyboardButton(text="🌐 Адрес/хост", callback_data=f"hst_fld:{idx}:hosts"),
            ],
            [
                InlineKeyboardButton(text="📥 Инбаунды", callback_data=f"hst_fld:{idx}:inboundIds"),
                InlineKeyboardButton(text="📝 Описание", callback_data=f"hst_fld:{idx}:serverDescription"),
            ],
            [
                InlineKeyboardButton(text="🔌 Порт", callback_data=f"hst_fld:{idx}:port"),
                InlineKeyboardButton(text="🛡 Безопасность", callback_data=f"hst_fld:{idx}:security"),
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"hst_del:{idx}"),
                InlineKeyboardButton(text="⬅️ К списку", callback_data="hst_ref"),
            ],
        ]
    )


def build_host_cancel_keyboard(back_cb: str = "hst_ref") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=back_cb)]
        ]
    )
