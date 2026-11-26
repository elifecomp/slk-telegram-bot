from html import escape
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from api.inbounds_api import fetch_inbounds
from api.hosts_api import (
    fetch_hosts,
    build_host_payload,
    add_host,
    update_host,
    delete_host,
)
from keyboards.hosts_kb import (
    build_hosts_list_keyboard,
    build_host_detail_keyboard,
    build_host_cancel_keyboard,
)
from services.clients_db import is_admin_user

router = Router()

BTN_HOSTS = "Хосты"

_HOSTS_CACHE: list[dict] = []


class HostFormStates(StatesGroup):
    add_remark = State()
    add_hosts = State()
    add_inbounds = State()
    add_desc = State()
    edit_field = State()


async def _get_inbound_remarks_map() -> dict[int, str]:
    ok, inbounds, _ = await fetch_inbounds()
    if not ok or not isinstance(inbounds, list):
        return {}
    mapping: dict[int, str] = {}
    for ib in inbounds:
        if not isinstance(ib, dict):
            continue
        raw_id = ib.get("id")
        try:
            ib_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        remark = str(ib.get("remark") or ib.get("tag") or "").strip()
        if remark:
            mapping[ib_id] = remark
    return mapping


def _format_host_detail(h: dict, idx: int, inbound_names: dict[int, str] | None = None) -> str:
    names = inbound_names or {}
    remark = escape(str(h.get("remark") or "—"))
    desc = escape(str(h.get("serverDescription") or "—"))
    endpoints = h.get("hosts") or []
    endpoints_str = escape(", ".join(str(x) for x in endpoints)) if endpoints else "—"
    inbounds = h.get("inboundIds") or []
    if inbounds:
        parts: list[str] = []
        for x in inbounds:
            s_id = str(x).strip()
            try:
                num_id = int(s_id)
                ib_label = names.get(num_id)
            except (TypeError, ValueError):
                ib_label = None
            if ib_label:
                parts.append(f"{escape(s_id)} ({escape(ib_label)})")
            else:
                parts.append(escape(s_id))
        inbounds_str = ", ".join(parts)
    else:
        inbounds_str = "—"
    port = escape(str(h.get("port") or "—"))
    security = escape(str(h.get("security") or "same"))
    gid = escape(str(h.get("groupId") or "—"))
    status = "🔴 Выключен" if h.get("isDisabled") else "🟢 Включён"

    return (
        f"🌐 <b>ХОСТ #{idx + 1}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• Статус: <b>{status}</b>\n"
        f"• Примечание: <b>{remark}</b>\n"
        f"• Описание: <code>{desc}</code>\n"
        f"• Конечная точка: <code>{endpoints_str}</code>\n"
        f"• Входящие: {inbounds_str}\n"
        f"• Порт: <code>{port}</code>\n"
        f"• Безопасность: <code>{security}</code>\n"
        f"• Group ID: <code>{gid}</code>"
    )


async def _load_and_show_list(target_msg: Message, edit: bool = False) -> None:
    global _HOSTS_CACHE
    ok, hosts, err = await fetch_hosts()
    if not ok:
        text = f"❌ <b>Ошибка загрузки хостов:</b>\n<code>{escape(err)}</code>"
        if edit:
            await target_msg.edit_text(text, parse_mode="HTML")
        else:
            await target_msg.answer(text, parse_mode="HTML")
        return

    _HOSTS_CACHE = hosts
    text = (
        f"🌐 <b>ХОСТЫ ПАНЕЛИ</b> (всего: <b>{len(hosts)}</b>)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите хост для просмотра и редактирования или добавьте новый:"
    )
    kb = build_hosts_list_keyboard(hosts)
    if edit:
        await target_msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target_msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text == BTN_HOSTS)
async def cmd_hosts_menu(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else None
    if not is_admin_user(uid):
        return
    await state.clear()
    await _load_and_show_list(message, edit=False)


@router.callback_query(F.data == "hst_ref")
async def cb_hosts_refresh(callback: CallbackQuery, state: FSMContext) -> None:
    uid = callback.from_user.id if callback.from_user else None
    if not is_admin_user(uid):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await state.clear()
    await callback.answer("Обновлено")
    if callback.message:
        await _load_and_show_list(callback.message, edit=True)


@router.callback_query(F.data.startswith("hst_vw:"))
async def cb_host_view(callback: CallbackQuery, state: FSMContext) -> None:
    uid = callback.from_user.id if callback.from_user else None
    if not is_admin_user(uid):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await state.clear()
    parts = callback.data.split(":")
    try:
        idx = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный хост", show_alert=True)
        return

    if not _HOSTS_CACHE:
        ok, hosts, _ = await fetch_hosts()
        if ok:
            _HOSTS_CACHE[:] = hosts

    if idx < 0 or idx >= len(_HOSTS_CACHE):
        await callback.answer("Хост не найден, обновите список", show_alert=True)
        return

    h = _HOSTS_CACHE[idx]
    ib_names = await _get_inbound_remarks_map()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            _format_host_detail(h, idx, ib_names),
            reply_markup=build_host_detail_keyboard(idx, bool(h.get("isDisabled"))),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("hst_tgl:"))
async def cb_host_toggle(callback: CallbackQuery) -> None:
    uid = callback.from_user.id if callback.from_user else None
    if not is_admin_user(uid):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    try:
        idx = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    if idx < 0 or idx >= len(_HOSTS_CACHE):
        await callback.answer("Хост не найден", show_alert=True)
        return

    current = _HOSTS_CACHE[idx]
    new_disabled = not bool(current.get("isDisabled"))
    payload = build_host_payload(current, isDisabled=new_disabled)
    ok, msg = await update_host(payload)
    if not ok:
        await callback.answer(f"Ошибка: {msg}", show_alert=True)
        return

    ok_list, hosts, _ = await fetch_hosts()
    if ok_list:
        _HOSTS_CACHE[:] = hosts
        updated = _HOSTS_CACHE[idx] if idx < len(_HOSTS_CACHE) else {**current, "isDisabled": new_disabled}
    else:
        updated = {**current, "isDisabled": new_disabled}
        _HOSTS_CACHE[idx] = updated

    ib_names = await _get_inbound_remarks_map()
    await callback.answer("Выключен" if new_disabled else "Включён")
    if callback.message:
        await callback.message.edit_text(
            _format_host_detail(updated, idx, ib_names),
            reply_markup=build_host_detail_keyboard(idx, bool(updated.get("isDisabled"))),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("hst_del:"))
async def cb_host_delete(callback: CallbackQuery) -> None:
    uid = callback.from_user.id if callback.from_user else None
    if not is_admin_user(uid):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    try:
        idx = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    if idx < 0 or idx >= len(_HOSTS_CACHE):
        await callback.answer("Хост не найден", show_alert=True)
        return

    gid = str(_HOSTS_CACHE[idx].get("groupId") or "")
    ok, msg = await delete_host(gid)
    if not ok:
        await callback.answer(f"Ошибка: {msg}", show_alert=True)
        return

    await callback.answer("Удалено")
    if callback.message:
        await _load_and_show_list(callback.message, edit=True)


@router.callback_query(F.data.startswith("hst_fld:"))
async def cb_host_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    uid = callback.from_user.id if callback.from_user else None
    if not is_admin_user(uid):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка", show_alert=True)
        return
    try:
        idx = int(parts[1])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return
    field = parts[2]
    if idx < 0 or idx >= len(_HOSTS_CACHE):
        await callback.answer("Хост не найден", show_alert=True)
        return

    prompts = {
        "remark": "Введите новое <b>Примечание</b> для хоста:",
        "hosts": "Введите <b>Конечную точку / хосты</b> (например: <code>slk-pl.altagen1.ru:2053</code>):",
        "inboundIds": "Введите <b>ID входящих</b> через запятую (например: <code>5</code> или <code>5, 9</code>):",
        "serverDescription": "Введите новое <b>Описание</b> (или <code>-</code> чтобы очистить):",
        "port": "Введите новый <b>Порт</b> (число, например <code>2053</code>):",
        "security": "Введите <b>Безопасность</b> (например: <code>same</code>, <code>tls</code>, <code>reality</code>):",
    }
    if field not in prompts:
        await callback.answer("Неизвестное поле", show_alert=True)
        return

    await state.set_state(HostFormStates.edit_field)
    await state.update_data(edit_idx=idx, edit_field=field)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            prompts[field],
            reply_markup=build_host_cancel_keyboard(f"hst_vw:{idx}:x"),
            parse_mode="HTML",
        )


@router.message(HostFormStates.edit_field)
async def msg_host_edit_field(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else None
    if not is_admin_user(uid):
        return
    data = await state.get_data()
    idx = int(data.get("edit_idx", -1))
    field = str(data.get("edit_field") or "")
    val = (message.text or "").strip()

    if idx < 0 or idx >= len(_HOSTS_CACHE):
        await state.clear()
        await message.answer("⚠️ Хост не найден, обновите список.")
        return

    current = _HOSTS_CACHE[idx]
    if field == "serverDescription" and val == "-":
        val = ""
    elif field == "port":
        if not val.isdigit():
            await message.answer("⚠️ Введите корректный номер порта (число).")
            return
        val = int(val)

    payload = build_host_payload(current, **{field: val})
    ok, msg_res = await update_host(payload)
    await state.clear()

    if not ok:
        await message.answer(f"❌ Не удалось сохранить: <code>{escape(msg_res)}</code>", parse_mode="HTML")
        return

    ok_list, hosts, _ = await fetch_hosts()
    if ok_list:
        _HOSTS_CACHE[:] = hosts
        updated = _HOSTS_CACHE[idx] if idx < len(_HOSTS_CACHE) else payload
    else:
        updated = payload
        _HOSTS_CACHE[idx] = updated

    ib_names = await _get_inbound_remarks_map()
    await message.answer(
        f"✅ Сохранено!\n\n{_format_host_detail(updated, idx, ib_names)}",
        reply_markup=build_host_detail_keyboard(idx, bool(updated.get("isDisabled"))),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "hst_add")
async def cb_host_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    uid = callback.from_user.id if callback.from_user else None
    if not is_admin_user(uid):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await state.set_state(HostFormStates.add_remark)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "➕ <b>Новый хост (1/4)</b>\nВведите <b>Примечание</b> (например: <code>Ru Poland</code>):",
            reply_markup=build_host_cancel_keyboard("hst_ref"),
            parse_mode="HTML",
        )


@router.message(HostFormStates.add_remark)
async def msg_host_add_remark(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else None
    if not is_admin_user(uid):
        return
    remark = (message.text or "").strip()
    if not remark:
        await message.answer("⚠️ Примечание не может быть пустым. Введите текст:")
        return
    await state.update_data(new_remark=remark)
    await state.set_state(HostFormStates.add_hosts)
    await message.answer(
        "➕ <b>Новый хост (2/4)</b>\nВведите <b>Конечную точку / хост</b> (например: <code>slk-pl.altagen1.ru:2053</code>):",
        reply_markup=build_host_cancel_keyboard("hst_ref"),
        parse_mode="HTML",
    )


@router.message(HostFormStates.add_hosts)
async def msg_host_add_hosts(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else None
    if not is_admin_user(uid):
        return
    hosts_text = (message.text or "").strip()
    if not hosts_text:
        await message.answer("⚠️ Укажите адрес хоста (например: <code>slk-pl.altagen1.ru:2053</code>):", parse_mode="HTML")
        return
    await state.update_data(new_hosts=hosts_text)
    await state.set_state(HostFormStates.add_inbounds)
    await message.answer(
        "➕ <b>Новый хост (3/4)</b>\nВведите <b>ID входящих</b> через запятую (например: <code>5</code>):",
        reply_markup=build_host_cancel_keyboard("hst_ref"),
        parse_mode="HTML",
    )


@router.message(HostFormStates.add_inbounds)
async def msg_host_add_inbounds(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else None
    if not is_admin_user(uid):
        return
    raw_ib = (message.text or "").strip()
    ids = [int(x.strip()) for x in raw_ib.replace(";", ",").split(",") if x.strip().isdigit()]
    if not ids:
        await message.answer("⚠️ Укажите хотя бы один числовой ID входящего (например: <code>5</code>):", parse_mode="HTML")
        return
    await state.update_data(new_inbounds=ids)
    await state.set_state(HostFormStates.add_desc)
    await message.answer(
        "➕ <b>Новый хост (4/4)</b>\nВведите <b>Описание</b> (например: <code>Россия Польша</code>) или отправьте <code>-</code>:",
        reply_markup=build_host_cancel_keyboard("hst_ref"),
        parse_mode="HTML",
    )


@router.message(HostFormStates.add_desc)
async def msg_host_add_desc(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id if message.from_user else None
    if not is_admin_user(uid):
        return
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    data = await state.get_data()
    await state.clear()

    payload = build_host_payload(
        None,
        remark=data.get("new_remark", ""),
        hosts=data.get("new_hosts", ""),
        inboundIds=data.get("new_inbounds", []),
        serverDescription=desc,
        security="same",
    )
    ok, msg_res = await add_host(payload)
    if not ok:
        await message.answer(f"❌ Ошибка добавления хоста: <code>{escape(msg_res)}</code>", parse_mode="HTML")
        return

    await message.answer(f"✅ Хост <b>{escape(payload['remark'])}</b> добавлен!", parse_mode="HTML")
    await _load_and_show_list(message, edit=False)
