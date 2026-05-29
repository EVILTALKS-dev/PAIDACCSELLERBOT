from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Filter

import database as db
from keyboards import (
    admin_main_kb, user_main_kb, cancel_kb,
    admin_account_kb, admin_approve_kb,
    admin_user_kb, admin_otp_kb, maintenance_kb
)
from config import ADMIN_IDS
from utils.logger import log_sale

router = Router()


class IsAdmin(Filter):
    async def __call__(self, obj) -> bool:
        return obj.from_user.id in ADMIN_IDS


# ── States ─────────────────────────────────────────────────────────────────────

class AddAccState(StatesGroup):
    number      = State()
    country     = State()
    price       = State()
    password    = State()
    twofa       = State()
    session_str = State()
    description = State()

class EditPriceState(StatesGroup):
    price = State()

class EditSessionState(StatesGroup):
    session = State()

class BroadcastState(StatesGroup):
    message = State()

class BanReasonState(StatesGroup):
    reason = State()

class MsgUserState(StatesGroup):
    message = State()

class MaintenanceMsgState(StatesGroup):
    message = State()


# ── Admin Entry ────────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "🏠 User Mode")
async def user_mode(msg: Message):
    await msg.answer("👤 User mode.", reply_markup=user_main_kb())


# ── Add Account ────────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "➕ Add Account")
async def add_start(msg: Message, state: FSMContext):
    await state.set_state(AddAccState.number)
    await msg.answer(
        "➕ <b>Add Account — Step 1/7</b>\n\n"
        "📱 Phone number (with country code):\n"
        "Example: <code>+917001234567</code>",
        parse_mode="HTML", reply_markup=cancel_kb()
    )

@router.message(IsAdmin(), AddAccState.number)
async def add_number(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    await state.update_data(number=msg.text.strip())
    await state.set_state(AddAccState.country)
    await msg.answer(
        "✅ Number saved!\n\n"
        "<b>Step 2/7 — Country + Flag:</b>\n\n"
        "Format: <code>🇮🇳 India</code>\n"
        "Examples:\n"
        "<code>🇺🇸 USA</code> · <code>🇷🇺 Russia</code> · <code>🇧🇩 Bangladesh</code>\n"
        "<code>🇵🇰 Pakistan</code> · <code>🇬🇧 UK</code> · <code>🇳🇬 Nigeria</code>\n\n"
        "Koi bhi country likh sakte ho!",
        parse_mode="HTML"
    )

@router.message(IsAdmin(), AddAccState.country)
async def add_country(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    text = msg.text.strip()
    parts = text.split(None, 1)
    flag    = parts[0].strip() if len(parts) == 2 else "🌍"
    country = parts[1].strip() if len(parts) == 2 else text
    await state.update_data(country=country, country_flag=flag)
    await state.set_state(AddAccState.price)
    await msg.answer(
        f"✅ {flag} {country}\n\n"
        f"<b>Step 3/7 — Price (₹):</b>\n"
        f"Example: <code>199</code>",
        parse_mode="HTML"
    )

@router.message(IsAdmin(), AddAccState.price)
async def add_price(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    try:
        price = float(msg.text.strip())
    except ValueError:
        return await msg.answer("❌ Valid number daalo. Example: <code>199</code>", parse_mode="HTML")
    await state.update_data(price=price)
    await state.set_state(AddAccState.password)
    await msg.answer(
        f"✅ Price: ₹{price:.2f}\n\n"
        f"<b>Step 4/7 — Password</b> (ya <code>skip</code>):",
        parse_mode="HTML"
    )

@router.message(IsAdmin(), AddAccState.password)
async def add_password(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    pw = "" if msg.text.strip().lower() == "skip" else msg.text.strip()
    await state.update_data(password=pw)
    await state.set_state(AddAccState.twofa)
    await msg.answer(
        "✅ Password saved!\n\n"
        "<b>Step 5/7 — 2FA Password</b> (ya <code>skip</code>):",
        parse_mode="HTML"
    )

@router.message(IsAdmin(), AddAccState.twofa)
async def add_twofa(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    twofa = "" if msg.text.strip().lower() == "skip" else msg.text.strip()
    await state.update_data(twofa=twofa)
    await state.set_state(AddAccState.session_str)
    await msg.answer(
        "✅ 2FA saved!\n\n"
        "<b>Step 6/7 — Session String</b>\n"
        "(Auto OTP ke liye — <code>python session_gen.py</code> se banao)\n\n"
        "Ya <code>skip</code> karo:",
        parse_mode="HTML"
    )

@router.message(IsAdmin(), AddAccState.session_str)
async def add_session(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    sess = "" if msg.text.strip().lower() == "skip" else msg.text.strip()
    await state.update_data(session_str=sess)
    await state.set_state(AddAccState.description)
    await msg.answer(
        "<b>Step 7/7 — Description</b> (ya <code>skip</code>):\n"
        "Example: <i>Fresh 2024, India verified</i>",
        parse_mode="HTML"
    )

@router.message(IsAdmin(), AddAccState.description)
async def add_done(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    desc = "" if msg.text.strip().lower() == "skip" else msg.text.strip()
    d = await state.get_data()
    await state.clear()

    await db.add_account(
        number=d["number"], price=d["price"],
        country=d["country"], country_flag=d["country_flag"],
        password=d.get("password",""), twofa=d.get("twofa",""),
        session_str=d.get("session_str",""), description=desc
    )

    sess_status = "✅ Auto OTP Ready" if d.get("session_str") else "⚠️ No Session (Manual OTP)"
    await msg.answer(
        f"✅ <b>Account Added!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 <code>{d['number']}</code>\n"
        f"{d['country_flag']} {d['country']} · ₹{d['price']:.2f}\n"
        f"🔑 {d.get('password') or 'N/A'} · 🔐 {d.get('twofa') or 'N/A'}\n"
        f"📡 {sess_status}\n"
        f"📝 {desc or 'No description'}",
        parse_mode="HTML", reply_markup=admin_main_kb()
    )


# ── View Accounts ──────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "📋 View Accounts")
async def view_accounts(msg: Message):
    accounts = await db.get_all_accounts()
    if not accounts:
        return await msg.answer("📋 Koi account nahi hai abhi.")

    avail = [a for a in accounts if a["status"] == "available"]
    sold  = [a for a in accounts if a["status"] == "sold"]
    await msg.answer(
        f"📋 <b>All Accounts</b>\n"
        f"🟢 Available: {len(avail)}  ·  🔴 Sold: {len(sold)}",
        parse_mode="HTML"
    )
    for acc in accounts[:20]:
        emoji = "🟢" if acc["status"] == "available" else "🔴"
        sess  = "📡 ✅" if acc.get("session_str") else "📡 ❌"
        await msg.answer(
            f"{emoji} <b>#{acc['id']}</b> · {acc['country_flag']} {acc['country']}\n"
            f"📱 <code>{acc['number']}</code>\n"
            f"💰 ₹{acc['price']:.2f} · {acc['status'].upper()}\n"
            f"🔑 {acc['password'] or 'N/A'} · 🔐 {acc['twofa'] or 'N/A'} · {sess}\n"
            f"📝 {acc['description'] or 'No desc'}",
            parse_mode="HTML", reply_markup=admin_account_kb(acc["id"])
        )


# ── Account Actions ────────────────────────────────────────────────────────────

@router.callback_query(IsAdmin(), F.data.startswith("del_acc:"))
async def del_acc(cq: CallbackQuery):
    acc_id = int(cq.data.split(":")[1])
    await db.delete_account(acc_id)
    await cq.message.edit_text(f"🗑 Account #{acc_id} deleted.")
    await cq.answer("Deleted!")

@router.callback_query(IsAdmin(), F.data.startswith("edit_price:"))
async def edit_price_start(cq: CallbackQuery, state: FSMContext):
    acc_id = int(cq.data.split(":")[1])
    await state.set_state(EditPriceState.price)
    await state.update_data(acc_id=acc_id)
    await cq.message.answer(f"✏️ Account #{acc_id} ka naya price:", reply_markup=cancel_kb())
    await cq.answer()

@router.message(IsAdmin(), EditPriceState.price)
async def edit_price_done(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    try:
        price = float(msg.text.strip())
    except ValueError:
        return await msg.answer("❌ Valid number daalo.")
    d = await state.get_data()
    await state.clear()
    await db.update_account(d["acc_id"], price=price)
    await msg.answer(f"✅ Price updated: ₹{price:.2f}", reply_markup=admin_main_kb())

@router.callback_query(IsAdmin(), F.data.startswith("edit_session:"))
async def edit_session_start(cq: CallbackQuery, state: FSMContext):
    acc_id = int(cq.data.split(":")[1])
    await state.set_state(EditSessionState.session)
    await state.update_data(acc_id=acc_id)
    await cq.message.answer(
        f"🔑 Account #{acc_id} ka naya session string:\n"
        f"(<code>clear</code> type karo remove karne ke liye)",
        parse_mode="HTML", reply_markup=cancel_kb()
    )
    await cq.answer()

@router.message(IsAdmin(), EditSessionState.session)
async def edit_session_done(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    sess = "" if msg.text.strip().lower() == "clear" else msg.text.strip()
    d = await state.get_data()
    await state.clear()
    await db.update_account(d["acc_id"], session_str=sess)
    await msg.answer("✅ Session updated!" if sess else "✅ Session removed!", reply_markup=admin_main_kb())


# ── Approve / Reject Orders ────────────────────────────────────────────────────

@router.callback_query(IsAdmin(), F.data.startswith("admin_approve:"))
async def approve(cq: CallbackQuery, bot: Bot):
    order_id = int(cq.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order or order["status"] != "pending":
        return await cq.answer("⚠️ Already processed.", show_alert=True)

    acc = await db.get_account(order["account_id"])
    await db.approve_order(order_id)
    await db.mark_account_sold(order["account_id"], order["user_id"])
    await db.update_user_stats(order["user_id"], order["amount"])
    session_id = await db.create_otp_session(order_id, order["user_id"], order["account_id"])

    from keyboards import reveal_number_kb
    try:
        await bot.send_message(
            order["user_id"],
            f"🎉 <b>Payment Approved!</b>\n\n"
            f"Order #{order_id} · ₹{order['amount']:.2f}\n"
            f"{acc['country_flag']} {acc['country']}\n\n"
            f"👇 Account details ke liye:",
            parse_mode="HTML",
            reply_markup=reveal_number_kb(order_id, session_id)
        )
    except Exception:
        pass

    await log_sale(bot, acc["number"], order["amount"], acc["country"], acc["country_flag"], order["user_id"], order["username"], order_id)

    try:
        await cq.message.edit_caption(
            caption=f"✅ <b>Order #{order_id} Approved!</b>\n📱 {acc['number']} delivered.",
            parse_mode="HTML"
        )
    except Exception:
        await cq.message.edit_text(f"✅ <b>Order #{order_id} Approved!</b>", parse_mode="HTML")
    await cq.answer("✅ Approved!")


@router.callback_query(IsAdmin(), F.data.startswith("admin_reject:"))
async def reject(cq: CallbackQuery, bot: Bot):
    order_id = int(cq.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order or order["status"] != "pending":
        return await cq.answer("⚠️ Already processed.", show_alert=True)

    await db.reject_order(order_id)
    try:
        await bot.send_message(
            order["user_id"],
            f"❌ <b>Order #{order_id} Rejected</b>\n\n"
            f"Payment verify nahi ho payi.\nSupport se contact karo.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        await cq.message.edit_caption(caption=f"❌ Order #{order_id} rejected.", parse_mode="HTML")
    except Exception:
        await cq.message.edit_text(f"❌ Order #{order_id} rejected.")
    await cq.answer("❌ Rejected!")


@router.callback_query(IsAdmin(), F.data.startswith("admin_view_ss:"))
async def view_screenshot(cq: CallbackQuery, bot: Bot):
    order_id = int(cq.data.split(":")[1])
    order = await db.get_order(order_id)
    if not order or not order.get("screenshot"):
        return await cq.answer("📸 Screenshot nahi mila!", show_alert=True)
    await bot.send_photo(
        cq.from_user.id,
        order["screenshot"],
        caption=f"📸 Order #{order_id} · @{order['username'] or 'N/A'}"
    )
    await cq.answer()


# ── Pending Orders ─────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "⏳ Pending Orders")
async def pending(msg: Message):
    orders = await db.get_pending_orders()
    if not orders:
        return await msg.answer("✅ Koi pending order nahi hai!")
    for o in orders:
        acc = await db.get_account(o["account_id"])
        await msg.answer(
            f"⏳ <b>Order #{o['id']}</b>\n"
            f"👤 @{o['username'] or 'N/A'} (<code>{o['user_id']}</code>)\n"
            f"📱 <code>{acc['number'] if acc else 'N/A'}</code>\n"
            f"{acc['country_flag'] if acc else ''} {acc['country'] if acc else ''}\n"
            f"💸 ₹{o['amount']:.2f}\n"
            f"📸 {'✅ Screenshot uploaded' if o.get('screenshot') else '❌ No screenshot'}\n"
            f"🗓 {o['created_at'][:19]}",
            parse_mode="HTML",
            reply_markup=admin_approve_kb(o["id"])
        )


# ── Statistics ─────────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "📊 Statistics")
async def stats(msg: Message):
    s = await db.get_stats()
    stock = await db.get_country_stock()
    country_lines = "\n".join(
        f"  {cs['flag']} {cs['country']}: {cs['count']} acc · ₹{cs['price']:.0f}"
        for cs in stock
    ) or "  No stock"

    maintenance = await db.is_maintenance()
    m_status = "🔴 ON" if maintenance else "🟢 OFF"

    await msg.answer(
        f"📊 <b>Bot Statistics</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Total Accounts  : {s['total_accounts']}\n"
        f"🟢 Available       : {s['available']}\n"
        f"🔴 Sold            : {s['sold']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users     : {s['users']}\n"
        f"🚫 Banned          : {s['banned']}\n"
        f"💰 Total Revenue   : ₹{s['revenue']:.2f}\n"
        f"⏳ Pending Orders  : {s['pending']}\n"
        f"✅ Approved Orders : {s['approved_orders']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔧 Maintenance     : {m_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 <b>Stock by Country:</b>\n{country_lines}",
        parse_mode="HTML"
    )


# ── User Management ────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "👥 User Management")
async def user_management(msg: Message):
    users = await db.get_all_users()
    if not users:
        return await msg.answer("👥 Koi user nahi hai.")

    await msg.answer(
        f"👥 <b>User Management ({len(users)} users)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Kisi user ka ID ya @username bhejo details ke liye.\n"
        f"Ya neeche list dekho:",
        parse_mode="HTML"
    )

    # Show paginated list with ban buttons
    for u in users[:15]:
        banned = u.get("is_banned", 0)
        status = "🚫 BANNED" if banned else "✅ Active"
        await msg.answer(
            f"{status}\n"
            f"👤 @{u['username'] or 'N/A'} · <code>{u['user_id']}</code>\n"
            f"💰 ₹{u['total_spent']:.0f} · {u['total_orders']} orders\n"
            f"📅 Joined: {u['joined_at'][:10]}"
            + (f"\n🚫 Reason: {u.get('ban_reason','')}" if banned and u.get('ban_reason') else ""),
            parse_mode="HTML",
            reply_markup=admin_user_kb(u["user_id"], bool(banned))
        )


@router.callback_query(IsAdmin(), F.data.startswith("ban:"))
async def ban_start(cq: CallbackQuery, state: FSMContext):
    user_id = int(cq.data.split(":")[1])
    await state.set_state(BanReasonState.reason)
    await state.update_data(target_user_id=user_id, ban_msg_id=cq.message.message_id)
    await cq.message.answer(
        f"🚫 Ban reason likho for <code>{user_id}</code>\n"
        f"(ya <code>skip</code> karo default reason ke liye):",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await cq.answer()


@router.message(IsAdmin(), BanReasonState.reason)
async def ban_done(msg: Message, state: FSMContext, bot: Bot):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    d = await state.get_data()
    await state.clear()
    reason = "No reason provided" if msg.text.strip().lower() == "skip" else msg.text.strip()
    user_id = d["target_user_id"]

    await db.ban_user(user_id, reason)

    # Notify banned user
    try:
        await bot.send_message(
            user_id,
            f"🚫 <b>You have been banned!</b>\n\n"
            f"Reason: {reason}\n\n"
            f"Contact support if you think this is a mistake.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await msg.answer(
        f"🚫 User <code>{user_id}</code> banned!\nReason: {reason}",
        parse_mode="HTML",
        reply_markup=admin_main_kb()
    )


@router.callback_query(IsAdmin(), F.data.startswith("unban:"))
async def unban(cq: CallbackQuery, bot: Bot):
    user_id = int(cq.data.split(":")[1])
    await db.unban_user(user_id)

    try:
        await bot.send_message(
            user_id,
            "✅ <b>You have been unbanned!</b>\n\nYou can use the bot again.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Update button
    try:
        await cq.message.edit_reply_markup(reply_markup=admin_user_kb(user_id, False))
    except Exception:
        pass

    await cq.answer(f"✅ User {user_id} unbanned!", show_alert=True)


@router.callback_query(IsAdmin(), F.data.startswith("user_orders:"))
async def user_orders(cq: CallbackQuery):
    user_id = int(cq.data.split(":")[1])
    orders = await db.get_user_orders(user_id)
    if not orders:
        return await cq.answer("No orders found!", show_alert=True)
    text = f"📜 <b>Orders for {user_id}</b>\n\n"
    for o in orders[:10]:
        e = {"pending":"⏳","approved":"✅","rejected":"❌"}.get(o["status"],"❔")
        text += f"{e} #{o['id']} · ₹{o['amount']:.2f} · {o['created_at'][:10]}\n"
    await cq.message.answer(text, parse_mode="HTML")
    await cq.answer()


@router.callback_query(IsAdmin(), F.data.startswith("msg_user:"))
async def msg_user_start(cq: CallbackQuery, state: FSMContext):
    user_id = int(cq.data.split(":")[1])
    await state.set_state(MsgUserState.message)
    await state.update_data(target_user_id=user_id)
    await cq.message.answer(
        f"📨 <code>{user_id}</code> ko message bhejo:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await cq.answer()


@router.message(IsAdmin(), MsgUserState.message)
async def msg_user_done(msg: Message, state: FSMContext, bot: Bot):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    d = await state.get_data()
    await state.clear()
    try:
        await bot.send_message(
            d["target_user_id"],
            f"📨 <b>Message from Admin:</b>\n\n{msg.text}",
            parse_mode="HTML"
        )
        await msg.answer("✅ Message sent!", reply_markup=admin_main_kb())
    except Exception:
        await msg.answer("❌ Message send nahi hua — user ne bot block kiya hoga.", reply_markup=admin_main_kb())


# ── Order History ──────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "📜 Order History")
async def order_history(msg: Message):
    orders = await db.get_all_orders(50)
    if not orders:
        return await msg.answer("📜 Koi order nahi hai.")
    text = "📜 <b>Last 50 Orders</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for o in orders:
        e = {"pending":"⏳","approved":"✅","rejected":"❌"}.get(o["status"],"❔")
        text += f"{e} #{o['id']} · @{o['username'] or 'N/A'} · ₹{o['amount']:.2f} · {o['created_at'][:10]}\n"
    await msg.answer(text, parse_mode="HTML")


# ── OTP Sessions ───────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "🔐 OTP Sessions")
async def otp_sessions(msg: Message):
    sessions = await db.get_waiting_otp_sessions()
    if not sessions:
        return await msg.answer("🔐 Koi active OTP session nahi hai.")
    for s in sessions:
        acc = await db.get_account(s["account_id"])
        await msg.answer(
            f"🔐 <b>OTP Session #{s['id']}</b>\n"
            f"📱 <code>{acc['number'] if acc else 'N/A'}</code>\n"
            f"👤 <code>{s['user_id']}</code>\n"
            f"📡 {'✅ Auto OTP' if acc and acc.get('session_str') else '❌ No Session'}\n"
            f"🗓 {s['created_at'][:19]}",
            parse_mode="HTML",
            reply_markup=admin_otp_kb(s["id"])
        )


# ── Broadcast ──────────────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "📢 Broadcast")
async def broadcast_start(msg: Message, state: FSMContext):
    await state.set_state(BroadcastState.message)
    await msg.answer(
        "📢 <b>Broadcast</b>\n\nSab users ko bhejne ke liye message type karo:",
        parse_mode="HTML", reply_markup=cancel_kb()
    )

@router.message(IsAdmin(), BroadcastState.message)
async def broadcast_send(msg: Message, state: FSMContext, bot: Bot):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    await state.clear()
    users = await db.get_all_users()
    sent = failed = 0
    status_msg = await msg.answer(f"📢 Sending to {len(users)} users...")
    for u in users:
        try:
            await bot.send_message(u["user_id"], f"📢 <b>Admin Message:</b>\n\n{msg.text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    try:
        await status_msg.edit_text(
            f"✅ <b>Broadcast Done!</b>\n\n"
            f"✅ Sent: {sent}\n❌ Failed: {failed}\n👥 Total: {len(users)}",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await msg.answer("✅ Broadcast complete!", reply_markup=admin_main_kb())


# ── Maintenance Mode ───────────────────────────────────────────────────────────

@router.message(IsAdmin(), F.text == "🔧 Maintenance")
async def maintenance_panel(msg: Message):
    is_on = await db.is_maintenance()
    m_msg = await db.get_maintenance_msg()
    status = "🔴 ON" if is_on else "🟢 OFF"
    await msg.answer(
        f"🔧 <b>Maintenance Mode</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Status: <b>{status}</b>\n\n"
        f"📝 Current Message:\n<i>{m_msg}</i>",
        parse_mode="HTML",
        reply_markup=maintenance_kb(is_on)
    )

@router.callback_query(IsAdmin(), F.data == "maintenance_on")
async def maintenance_on(cq: CallbackQuery):
    await db.set_setting("maintenance", "1")
    await cq.message.edit_text(
        "🔧 <b>Maintenance Mode</b>\n━━━━━━━━━━━━━━━━━━━━\nStatus: <b>🔴 ON</b>\n\nBot is now in maintenance mode.",
        parse_mode="HTML",
        reply_markup=maintenance_kb(True)
    )
    await cq.answer("🔴 Maintenance ON!", show_alert=True)

@router.callback_query(IsAdmin(), F.data == "maintenance_off")
async def maintenance_off(cq: CallbackQuery):
    await db.set_setting("maintenance", "0")
    await cq.message.edit_text(
        "🔧 <b>Maintenance Mode</b>\n━━━━━━━━━━━━━━━━━━━━\nStatus: <b>🟢 OFF</b>\n\nBot is now live!",
        parse_mode="HTML",
        reply_markup=maintenance_kb(False)
    )
    await cq.answer("🟢 Maintenance OFF!", show_alert=True)

@router.callback_query(IsAdmin(), F.data == "maintenance_edit_msg")
async def maintenance_edit_msg(cq: CallbackQuery, state: FSMContext):
    await state.set_state(MaintenanceMsgState.message)
    await cq.message.answer(
        "✏️ Naya maintenance message type karo:",
        reply_markup=cancel_kb()
    )
    await cq.answer()

@router.message(IsAdmin(), MaintenanceMsgState.message)
async def maintenance_msg_done(msg: Message, state: FSMContext):
    if msg.text == "❌ Cancel":
        await state.clear()
        return await msg.answer("Cancelled.", reply_markup=admin_main_kb())
    await state.clear()
    await db.set_setting("maintenance_msg", msg.text.strip())
    await msg.answer("✅ Maintenance message updated!", reply_markup=admin_main_kb())
