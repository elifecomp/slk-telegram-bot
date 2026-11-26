def format_bytes(num_bytes: int | float | None) -> str:
    """Переводит байты в читаемый вид."""
    if num_bytes is None:
        return "н/д"
    try:
        val = float(num_bytes)
    except (TypeError, ValueError):
        return "н/д"
    if val < 0:
        val = 0.0

    units = ["Б", "КБ", "МБ", "ГБ", "ТБ", "ПБ"]
    idx = 0
    while val >= 1024.0 and idx < len(units) - 1:
        val /= 1024.0
        idx += 1
    return f"{val:.2f} {units[idx]}" if idx > 0 else f"{int(val)} {units[0]}"


def format_uptime(seconds: int | float | None) -> str:
    """Форматирует аптайм в секундах."""
    if seconds is None:
        return "н/д"
    try:
        sec = int(float(seconds))
    except (TypeError, ValueError):
        return "н/д"
    if sec < 0:
        sec = 0

    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}д")
    if hours:
        parts.append(f"{hours}ч")
    parts.append(f"{minutes}м")
    return " ".join(parts)
