import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from config import ADMIN_ID
from keyboards.clients_kb import (
    build_cancel_input_keyboard,
    build_client_actions_keyboard,
)
from services.client_edit_service import (
    apply_rename_client,
    apply_reset_traffic,
    apply_set_enabled,
    apply_set_limit_gb,
    get_managed_client_card,
)
from services.clients_cache import get_session, resolve_client_slot, update_cached_client_email
from services.clients_list_service import (
    get_inbound_clients_report,
    get_inbounds_picker_report,
)

router = Router()
logger = logging.getLogger(__name__)


class ClientEditStates(StatesGroup):
    waiting_new_name = State()
    waiting_new_gb = State()


@router.message(F.text == "Клиенты")
async def handle_clients_menu(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()

    wait_msg = await message.answer("⏳ Загружаю список инбаундов...")
    try:
        text, kb = await get_inbounds_picker_report()
        await wait_msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.exception("Ошибка при загрузке инбаундов для раздела Клиенты")
        await wait_msg.edit_text(f"❌ Ошибка:\n<code>{e}</code>", parse_mode="HTML")


@router.callback_query(F.data.startswith("cl_back_ib:"))
async def handle_back_to_inbounds(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    text, kb = await get_inbounds_picker_report()
    if callback.message:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("cl_ib:"))
async def handle_select_inbound(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await state.clear()

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    _, sid, ib_slot = parts
    await callback.answer()
    text, kb = await get_inbound_clients_report(sid, ib_slot)
    if callback.message:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("cl_vw:"))
async def handle_view_client(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await state.clear()

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    _, sid, c_slot = parts
    resolved = resolve_client_slot(sid, c_slot)
    if not resolved:
        await callback.answer("Список устарел, нажмите «Клиенты»", show_alert=True)
        return

    ib_slot, email = resolved
    session_state = get_session(sid)
    ib_summary = session_state.inbounds.get(ib_slot) if session_state else None
    ib_id = ib_summary.inbound_id if ib_summary else None

    await callback.answer(f"Открываю {email}...")
    card = await get_managed_client_card(email, preferred_inbound_id=ib_id)
    kb = build_client_actions_keyboard(sid, c_slot, ib_slot)
    if callback.message:
        await callback.message.edit_text(card, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("cl_rst:"))
async def handle_reset_traffic(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        return
    _, sid, c_slot = parts
    resolved = resolve_client_slot(sid, c_slot)
    if not resolved:
        await callback.answer("Список устарел", show_alert=True)
        return

    ib_slot, email = resolved
    ok, msg = await apply_reset_traffic(email)
    await callback.answer("✅ Трафик сброшен" if ok else f"⚠️ {msg}", show_alert=not ok)

    session_state = get_session(sid)
    ib_id = session_state.inbounds[ib_slot].inbound_id if (session_state and ib_slot in session_state.inbounds) else None
    card = await get_managed_client_card(email, preferred_inbound_id=ib_id)
    if callback.message:
        await callback.message.edit_text(
            card,
            parse_mode="HTML",
            reply_markup=build_client_actions_keyboard(sid, c_slot, ib_slot),
        )


@router.callback_query(F.data.startswith("cl_off:"))
async def handle_disable_client(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        return
    _, sid, c_slot = parts
    resolved = resolve_client_slot(sid, c_slot)
    if not resolved:
        await callback.answer("Список устарел", show_alert=True)
        return

    ib_slot, email = resolved
    session_state = get_session(sid)
    ib_id = session_state.inbounds[ib_slot].inbound_id if (session_state and ib_slot in session_state.inbounds) else None

    ok, msg = await apply_set_enabled(email, False, preferred_inbound_id=ib_id)
    await callback.answer("⛔ Клиент отключён" if ok else f"⚠️ {msg}", show_alert=not ok)

    card = await get_managed_client_card(email, preferred_inbound_id=ib_id)
    if callback.message:
        await callback.message.edit_text(
            card,
            parse_mode="HTML",
            reply_markup=build_client_actions_keyboard(sid, c_slot, ib_slot),
        )


@router.callback_query(F.data.startswith("cl_on:"))
async def handle_enable_client(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        return
    _, sid, c_slot = parts
    resolved = resolve_client_slot(sid, c_slot)
    if not resolved:
        await callback.answer("Список устарел", show_alert=True)
        return

    ib_slot, email = resolved
    session_state = get_session(sid)
    ib_id = session_state.inbounds[ib_slot].inbound_id if (session_state and ib_slot in session_state.inbounds) else None

    ok, msg = await apply_set_enabled(email, True, preferred_inbound_id=ib_id)
    await callback.answer("✅ Клиент включён" if ok else f"⚠️ {msg}", show_alert=not ok)

    card = await get_managed_client_card(email, preferred_inbound_id=ib_id)
    if callback.message:
        await callback.message.edit_text(
            card,
            parse_mode="HTML",
            reply_markup=build_client_actions_keyboard(sid, c_slot, ib_slot),
        )


@router.callback_query(F.data.startswith("cl_ren:"))
async def handle_ask_rename(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        return
    _, sid, c_slot = parts
    resolved = resolve_client_slot(sid, c_slot)
    if not resolved:
        await callback.answer("Список устарел", show_alert=True)
        return

    _, email = resolved
    await state.set_state(ClientEditStates.waiting_new_name)
    await state.update_data(sid=sid, c_slot=c_slot, email=email)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"✏️ Введите новое имя (email) для клиента <b>{email}</b>:",
            parse_mode="HTML",
            reply_markup=build_cancel_input_keyboard(sid, c_slot),
        )


@router.message(ClientEditStates.waiting_new_name)
async def handle_save_rename(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    sid = data.get("sid", "")
    c_slot = data.get("c_slot", "")
    old_email = data.get("email", "")
    new_email = (message.text or "").strip()

    resolved = resolve_client_slot(sid, c_slot)
    ib_slot = resolved[0] if resolved else "0"
    session_state = get_session(sid)
    ib_id = session_state.inbounds[ib_slot].inbound_id if (session_state and ib_slot in session_state.inbounds) else None

    ok, msg = await apply_rename_client(old_email, new_email, preferred_inbound_id=ib_id)
    await state.clear()

    if ok:
        update_cached_client_email(sid, c_slot, old_email, new_email)
        card = await get_managed_client_card(new_email, preferred_inbound_id=ib_id)
        await message.answer(
            f"✅ Имя изменено: <b>{old_email}</b> → <b>{new_email}</b>\n\n{card}",
            parse_mode="HTML",
            reply_markup=build_client_actions_keyboard(sid, c_slot, ib_slot),
        )
    else:
        await message.answer(
            f"⚠️ Не удалось изменить имя: <code>{msg}</code>",
            parse_mode="HTML",
            reply_markup=build_client_actions_keyboard(sid, c_slot, ib_slot),
        )


@router.callback_query(F.data.startswith("cl_gb:"))
async def handle_ask_gb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        return
    _, sid, c_slot = parts
    resolved = resolve_client_slot(sid, c_slot)
    if not resolved:
        await callback.answer("Список устарел", show_alert=True)
        return

    _, email = resolved
    await state.set_state(ClientEditStates.waiting_new_gb)
    await state.update_data(sid=sid, c_slot=c_slot, email=email)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"📦 Введите новый лимит трафика в ГБ для клиента <b>{email}</b> (например <code>100</code> или <code>0</code> для безлимита):",
            parse_mode="HTML",
            reply_markup=build_cancel_input_keyboard(sid, c_slot),
        )


@router.message(ClientEditStates.waiting_new_gb)
async def handle_save_gb(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    sid = data.get("sid", "")
    c_slot = data.get("c_slot", "")
    email = data.get("email", "")
    raw_val = (message.text or "").strip().replace(",", ".")

    resolved = resolve_client_slot(sid, c_slot)
    ib_slot = resolved[0] if resolved else "0"
    session_state = get_session(sid)
    ib_id = session_state.inbounds[ib_slot].inbound_id if (session_state and ib_slot in session_state.inbounds) else None

    try:
        gb_val = float(raw_val)
    except ValueError:
        await message.answer("⚠️ Введите корректное число ГБ (например, <code>50</code> или <code>0</code>).", parse_mode="HTML")
        return

    ok, msg = await apply_set_limit_gb(email, gb_val, preferred_inbound_id=ib_id)
    await state.clear()

    if ok:
        card = await get_managed_client_card(email, preferred_inbound_id=ib_id)
        await message.answer(
            f"✅ Лимит обновлён ({gb_val:g} ГБ)\n\n{card}",
            parse_mode="HTML",
            reply_markup=build_client_actions_keyboard(sid, c_slot, ib_slot),
        )
    else:
        await message.answer(
            f"⚠️ Не удалось изменить лимит: <code>{msg}</code>",
            parse_mode="HTML",
            reply_markup=build_client_actions_keyboard(sid, c_slot, ib_slot),
        )
