from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from utils.qr import make_upi_qr
from keyboards import deposit_payment_kb, deposit_confirm_kb, admin_deposit_kb
from config import ADMIN_IDS, UPI_ID

router = Router()


class DepositState(StatesGroup):
    custom_amount = State()
    screenshot    = State()


# ── My Wallet ──────────────────────────────────────────────────────────────────

@router.message(F.text == "💰 My Wallet")
async def my_wallet(msg: Message):
    bal    = await db.get_balance(msg.from_user.id)
    orders = await db.get_user_orders(msg.from_user.id)
    done   = [o for o in orders if o["status"] == "approved"]
    await msg.answer(
        f"💼 <b>My Wallet</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Balance   : <b>₹{bal:.2f}</b>\n"
        f"📦 Orders    : {len(done)} completed\n"
        f"💸 Spent     : ₹{sum(o['amount'] for o in done):.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Tap <b>➕ Deposit</b> to add money!",
        parse_mode="HTML"
    )


# ── Deposit Menu ───────────────────────────────────────────────────────────────

@router.message(F.text == "➕ Deposit")
async def deposit_menu(msg: Message):
    from keyboards import deposit_amount_kb
    bal = await db.get_balance(msg.from_user.id)
    await msg.answer(
        f"💳 <b>Deposit Money</b>\n\n"
        f"💼 Current Balance: <b>₹{bal:.2f}</b>\n\n"
        f"Select amount to deposit:",
        parse_mode="HTML",
        reply_markup=deposit_amount_kb()
    )


# ── Amount Button Tapped ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dep:"))
async def dep_amount_selected(cq: CallbackQuery, state: FSMContext):
    val = cq.data.split(":", 1)[1]

    if val == "custom":
        await state.set_state(DepositState.custom_amount)
        await cq.message.answer(
            "✏️ <b>Custom Amount</b>\n\nKitna deposit karna hai? (₹ mein):\nMinimum: ₹10",
            parse_mode="HTML"
        )
        await cq.answer()
        return

    await _send_deposit_qr(cq.message, cq.from_user.id, cq.from_user.username or "", float(val))
    await cq.answer()


# ── Custom Amount ──────────────────────────────────────────────────────────────

@router.message(DepositState.custom_amount)
async def dep_custom_amount(msg: Message, state: FSMContext):
    try:
        amount = float(msg.text.strip().replace("₹", "").replace(",", ""))
        if amount < 10:
            return await msg.answer("❌ Minimum ₹10 deposit karo!")
        if amount > 50000:
            return await msg.answer("❌ Maximum ₹50,000 ek baar mein!")
    except ValueError:
        return await msg.answer("❌ Valid amount daalo! Example: <code>500</code>", parse_mode="HTML")

    await state.clear()
    await _send_deposit_qr(msg, msg.from_user.id, msg.from_user.username or "", amount)


# ── Generate & Send QR ────────────────────────────────────────────────────────

async def _send_deposit_qr(target, user_id: int, username: str, amount: float):
    """Create deposit record and send QR to user."""

    # Create deposit with exact=0 first to get ID
    deposit_id = await db.create_deposit(user_id, username, amount, 0)

    # Generate QR with unique paise
    qr_bytes, exact = make_upi_qr(amount, deposit_id[:6])

    # Update exact amount in DB
    await db.update_deposit_exact(deposit_id, exact)

    caption = (
        f"💳 <b>Deposit QR</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Deposit Amount : ₹{amount:.2f}\n"
        f"💸 Pay EXACTLY    : <b>₹{exact:.2f}</b>\n"
        f"🏦 UPI ID         : <code>{UPI_ID}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>Important:</b>\n"
        f"• Exact amount pay karo (₹{exact:.2f})\n"
        f"• Screenshot lo payment ka\n"
        f"• Neeche Upload button dabao\n\n"
        f"🔖 Ref: <code>{deposit_id[:8]}</code>"
    )

    qr_file = BufferedInputFile(qr_bytes, filename="deposit_qr.png")

    if isinstance(target, Message):
        await target.answer_photo(
            photo=qr_file,
            caption=caption,
            parse_mode="HTML",
            reply_markup=deposit_payment_kb(deposit_id)
        )
    else:
        await target.answer_photo(
            photo=qr_file,
            caption=caption,
            parse_mode="HTML",
            reply_markup=deposit_payment_kb(deposit_id)
        )


# ── Upload Screenshot Button ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dep_ss:"))
async def dep_ss_prompt(cq: CallbackQuery, state: FSMContext):
    deposit_id = cq.data.split(":", 1)[1]

    dep = await db.get_deposit(deposit_id)
    if not dep:
        return await cq.answer("❌ Deposit not found!", show_alert=True)
    if dep["user_id"] != cq.from_user.id:
        return await cq.answer("❌ Not your deposit!", show_alert=True)
    if dep["status"] != "pending":
        return await cq.answer("⚠️ Already processed.", show_alert=True)

    await state.set_state(DepositState.screenshot)
    await state.update_data(deposit_id=deposit_id)
    await cq.message.answer(
        "📸 <b>Payment Screenshot Bhejo</b>\n\n"
        "• Gallery se photo select karo\n"
        "• Direct photo send karo (file nahi)\n"
        "• Sirf ek photo bhejo",
        parse_mode="HTML"
    )
    await cq.answer()


# ── Receive Screenshot ─────────────────────────────────────────────────────────

@router.message(DepositState.screenshot, F.photo)
async def dep_ss_received(msg: Message, state: FSMContext):
    data       = await state.get_data()
    deposit_id = data.get("deposit_id")
    await state.clear()

    if not deposit_id:
        return await msg.answer("❌ Session expire ho gayi. Dobara try karo.")

    file_id = msg.photo[-1].file_id
    await db.set_deposit_screenshot(deposit_id, file_id)

    dep = await db.get_deposit(deposit_id)

    await msg.answer(
        f"✅ <b>Screenshot Received!</b>\n\n"
        f"💰 Amount  : ₹{dep['amount']:.2f}\n"
        f"💸 Paid    : ₹{dep['exact_amount']:.2f}\n"
        f"🔖 Ref     : <code>{deposit_id[:8]}</code>\n\n"
        f"Ab admin ko notify karo 👇",
        parse_mode="HTML",
        reply_markup=deposit_confirm_kb(deposit_id)
    )


@router.message(DepositState.screenshot, F.document)
async def dep_ss_doc(msg: Message):
    await msg.answer("❌ <b>File mat bhejo!</b>\n\nGallery se photo as image bhejo.", parse_mode="HTML")


@router.message(DepositState.screenshot, ~F.photo)
async def dep_ss_wrong(msg: Message):
    await msg.answer("❌ Sirf photo bhejo!")


# ── Notify Admin ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dep_notify:"))
async def dep_notify(cq: CallbackQuery, bot: Bot):
    deposit_id = cq.data.split(":", 1)[1]
    dep        = await db.get_deposit(deposit_id)

    if not dep:
        return await cq.answer("❌ Deposit not found!", show_alert=True)
    if dep["user_id"] != cq.from_user.id:
        return await cq.answer("❌ Not your deposit!", show_alert=True)
    if dep["status"] != "pending":
        return await cq.answer("⚠️ Already processed.", show_alert=True)
    if not dep.get("screenshot"):
        return await cq.answer(
            "❌ Pehle screenshot upload karo!\nUpar 'Upload Screenshot' button dabao.",
            show_alert=True
        )

    # Update message
    try:
        await cq.message.edit_caption(
            caption=(
                f"⏳ <b>Verification Pending</b>\n\n"
                f"💰 ₹{dep['amount']:.2f} deposit request\n"
                f"🔖 Ref: <code>{deposit_id[:8]}</code>\n\n"
                f"Admin review kar raha hai...\n"
                f"Approve hone pe balance add ho jaayega! ✅"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Notify all admins with screenshot
    for aid in ADMIN_IDS:
        try:
            await bot.send_photo(
                aid,
                dep["screenshot"],
                caption=(
                    f"💳 <b>DEPOSIT REQUEST!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 @{dep['username'] or 'N/A'} · <code>{dep['user_id']}</code>\n"
                    f"💰 Amount  : ₹{dep['amount']:.2f}\n"
                    f"💸 Paid    : ₹{dep['exact_amount']:.2f}\n"
                    f"🔖 Ref     : <code>{deposit_id[:8]}</code>\n"
                    f"🗓 Time    : {dep['created_at'][:19]}\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode="HTML",
                reply_markup=admin_deposit_kb(deposit_id)
            )
        except Exception:
            # Fallback text only
            try:
                await bot.send_message(
                    aid,
                    f"💳 <b>DEPOSIT!</b>\n"
                    f"👤 <code>{dep['user_id']}</code>\n"
                    f"💰 ₹{dep['amount']:.2f} · Paid ₹{dep['exact_amount']:.2f}\n"
                    f"🔖 <code>{deposit_id[:8]}</code>",
                    parse_mode="HTML",
                    reply_markup=admin_deposit_kb(deposit_id)
                )
            except Exception:
                pass

    await cq.answer("✅ Admin ko notify kar diya!")


# ── Cancel Deposit ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dep_cancel:"))
async def dep_cancel(cq: CallbackQuery):
    deposit_id = cq.data.split(":", 1)[1]
    dep        = await db.get_deposit(deposit_id)

    if not dep or dep["user_id"] != cq.from_user.id:
        return await cq.answer("❌ Not your deposit!", show_alert=True)
    if dep["status"] != "pending":
        return await cq.answer("⚠️ Cannot cancel processed deposit.", show_alert=True)

    await db.reject_deposit(deposit_id)
    try:
        await cq.message.edit_caption(
            caption=f"❌ <b>Deposit Cancelled.</b>\n\n₹{dep['amount']:.2f} deposit cancel kar diya.",
            parse_mode="HTML"
        )
    except Exception:
        await cq.message.answer("❌ Deposit cancelled.")
    await cq.answer("Cancelled.")


# ── Wallet Pay (Buy with balance) ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("wallet_pay:"))
async def wallet_pay(cq: CallbackQuery, bot: Bot):
    account_id = cq.data.split(":", 1)[1]
    acc        = await db.get_account(account_id)

    if not acc or acc["status"] != "available":
        return await cq.answer("❌ Account no longer available!", show_alert=True)

    bal = await db.get_balance(cq.from_user.id)
    if bal < acc["price"]:
        return await cq.answer(
            f"❌ Insufficient balance!\n"
            f"Balance : ₹{bal:.2f}\n"
            f"Required: ₹{acc['price']:.2f}\n\n"
            f"Pehle deposit karo!",
            show_alert=True
        )

    u        = cq.from_user
    order_id = await db.create_order(u.id, u.username or "", u.full_name or "", account_id, acc["price"])
    deducted = await db.deduct_balance(u.id, acc["price"])

    if not deducted:
        return await cq.answer("❌ Balance deduct nahi hua. Try again.", show_alert=True)

    # Auto approve wallet purchase
    await db.approve_order(order_id)
    await db.mark_account_sold(account_id, u.id)
    await db.update_user_stats(u.id, acc["price"])
    session_id = await db.create_otp_session(order_id, u.id, account_id)
    new_bal    = await db.get_balance(u.id)

    from keyboards import reveal_number_kb
    await cq.message.answer(
        f"✅ <b>Purchase Successful!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💸 ₹{acc['price']:.2f} wallet se deducted\n"
        f"💼 Remaining: ₹{new_bal:.2f}\n"
        f"{acc['country_flag']} {acc['country']}\n\n"
        f"👇 Account details ke liye:",
        parse_mode="HTML",
        reply_markup=reveal_number_kb(order_id, session_id)
    )

    from utils.logger import log_sale
    await log_sale(
        bot, acc["number"], acc["price"],
        acc["country"], acc["country_flag"],
        u.id, u.username or "", order_id
    )
    await cq.answer("✅ Purchase successful!")
