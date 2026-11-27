from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

GIB_BYTES = 1024 ** 3

TARIFFS: list[dict] = [
    {"key": "mini_50", "name": "Тариф Мини", "short": "Мини • 50 ГБ", "gb": 50},
    {"key": "std_100", "name": "Тариф Стандарт", "short": "Стандарт • 100 ГБ", "gb": 100},
    {"key": "ultra_150", "name": "Тариф Ультра", "short": "Ультра • 150 ГБ", "gb": 150},
    {"key": "ultra_200", "name": "Тариф Про 200", "short": "Про 200 • 200 ГБ", "gb": 200},
    {"key": "unlim", "name": "Тариф Безлимитный", "short": "Безлимитный", "gb": 0},
]

TARIFF_BY_KEY: dict[str, dict] = {item["key"]: item for item in TARIFFS}


def resolve_tariff_name(limit_bytes: float | int | None) -> str | None:
    """Возвращает название тарифа, если лимит совпадает с известным тарифом или безлимитом."""
    try:
        val = float(limit_bytes or 0)
    except (TypeError, ValueError):
        return None

    if val <= 0:
        return "Тариф Безлимитный"

    actual_gb = val / GIB_BYTES
    for item in TARIFFS:
        target_gb = item["gb"]
        if target_gb > 0 and abs(actual_gb - target_gb) <= 0.25:
            return str(item["name"])
    return None


def build_tariffs_inline_keyboard() -> InlineKeyboardMarkup:
    """Строит инлайн-клавиатуру тарифов аккуратно в 2 ряда."""
    row1 = [
        InlineKeyboardButton(text="🔹 Мини (50 ГБ)", callback_data="tariff_req:mini_50"),
        InlineKeyboardButton(text="🔸 Стандарт (100 ГБ)", callback_data="tariff_req:std_100"),
    ]
    row2 = [
        InlineKeyboardButton(text="💎 Ультра (150 ГБ)", callback_data="tariff_req:ultra_150"),
        InlineKeyboardButton(text="👑 Про 200 (200 ГБ)", callback_data="tariff_req:ultra_200"),
        InlineKeyboardButton(text="♾️ Безлимитный", callback_data="tariff_req:unlim"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])
