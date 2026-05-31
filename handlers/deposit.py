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


# ── Deposit Menu ───────────────────────────────────────────────────────────────

@router.message(F.text == "➕ Deposit")
async def deposit_menu(msg: Message):
    from keyboards import deposit_amount_kb
    bal = await db.get_balance(msg.from_user.id)
    await msg.answer(
        f"💰 <b>Add Money to Wallet</b>\n\n"
        f"💼 Current Balance: <b>₹{bal:.2f}</b>\n\n"
        f"Select amount to deposit:",
        parse_mode="HTML",
        reply_markup=deposit_amount_kb()
    )


@router.message(F.text == "💰 My Wallet")
async def my_wallet(msg: Message):
    bal    = await db.get_balance(msg.from_user.id)
    orders = await db.get_user_orders(msg.from_user.id)
    spent  = sum(o["amount"] for o in orders if o["status"] == "approved")
    await msg.answer(
        f"💼 <b>My Wallet</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Balance: <b>₹{bal:.2f}</b>\n"
        f"💸 Total Spent: ₹{spent:.2f}\n"
        f"📦 Total Orders: {len([o for o in orders if o['status']=='approved'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Tap <b>➕ Deposit</b> to add money!",
        parse_mode="HTML"
    )


# ── Amount Selection ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dep:"))
async def deposit_amount(cq: CallbackQuery, state: FSMContext, bot: Bot):
    val = cq.data.split(":", 1)[1]

    if val == "custom":
        await state.set_state(DepositState.custom_amount)
        await cq.message.answer("✏️ Custom amount enter karo (₹):\nMinimum: ₹10")
        await cq.answer()
        return

    amount = float(val)
    await _generate_deposit_qr(cq.message, cq.from_user.id, cq.from_user.username or "", amount, bot)
    await cq.answer()


@router.message(DepositState.custom_amount)
async def deposit_custom(msg: Message, state: FSMContext, bot: Bot):
    try:
        amount = float(msg.text.strip())
        if amount < 10:
            return await msg.answer("❌ Minimum ₹10 deposit karo.")
    except ValueError:
        return await msg.answer("❌ Valid amount daalo.")
    await state.clear()
    await _generate_deposit_qr(msg, msg.from_user.id, msg.from_user.username or "", amount, bot)


async def _generate_deposit_qr(msg_or_obj, user_id: int, username: str, amount: float, bot: Bot):
    # Create deposit record first
    deposit_id = await db.create_deposit(user_id, username, amount, 0)
    qr_bytes, exact = make_upi_qr(amount, deposit_id[:8])

    # Update exact amount
    from bson import ObjectId
    db2 = db.get_db()
    await db2.deposits.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"exact_amount": exact}})

    caption = (
        f"💳 <b>Deposit QR — #{deposit_id[:8]}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Pay EXACTLY: <b>₹{exact:.2f}</b>\n"
        f"🏦 UPI: <code>{UPI_ID}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Exact amount zaroori hai (unique paise)\n\n"
        f"📸 Screenshot upload karo neeche:"
    )
    qr_file = BufferedInputFile(qr_bytes, filename="deposit.png")

    if hasattr(msg_or_obj, 'answer_photo'):
        await msg_or_obj.answer_photo(photo=qr_file, caption=caption, parse_mode="HTML", reply_markup=deposit_payment_kb(deposit_id))
    else:
        await msg_or_obj.answer_photo(photo=qr_file, caption=caption, parse_mode="HTML", reply_markup=deposit_payment_kb(deposit_id))


# ── Screenshot Upload ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("dep_ss:"))
async def dep_screenshot_prompt(cq: CallbackQuery, state: FSMContext):
    deposit_id = cq.data.split(":", 1)[1]
    await state.set_state(DepositState.screenshot)
    await state.update_data(deposit_id=deposit_id)
    await cq.message.answer("📸 Payment screenshot bhejo (photo as image):")
    await cq.answer()


@router.message(DepositState.screenshot, F.photo)
async def dep_screenshot_recv(msg: Message, state: FSMContext, bot: Bot):
    data       = await state.get_data()
    deposit_id = data.get("deposit_id")
    await state.clear()

    file_id = msg.photo[-1].file_id
    await db.set_deposit_screenshot(deposit_id, file_id)

    await msg.answer(
        f"✅ <b>Screenshot received!</b>\n\nDeposit #{deposit_id[:8]}\nAb admin ko notify karo 👇",
        parse_mode="HTML",
        reply_markup=deposit_confirm_kb(deposit_id)
    )


@router.message(DepositState.screenshot, ~F.photo)
async def dep_screenshot_wrong(msg: Message):
    await msg.answer("❌ Sirf photo bhejo (file nahi)!")


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
        return await cq.answer("❌ Pehle screenshot upload karo!", show_alert=True)

    try:
        await cq.message.edit_caption(
            caption=f"⏳ <b>Verification Pending</b>\n\nDeposit #{deposit_id[:8]} — Admin review kar raha hai.\nApprove hone pe balance add ho jaayega.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    for aid in ADMIN_IDS:
        try:
            await bot.send_photo(
                aid,
                dep["screenshot"],
                caption=(
                    f"💳 <b>DEPOSIT REQUEST!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔖 #{deposit_id[:8]}\n"
                    f"👤 @{dep['username'] or 'N/A'} · <code>{dep['user_id']}</code>\n"
                    f"💰 Amount: ₹{dep['amount']:.2f}\n"
                    f"💸 Exact: ₹{dep['exact_amount']:.2f}\n"
                    f"🗓 {dep['created_at'][:19]}"
                ),
                parse_mode="HTML",
                reply_markup=admin_deposit_kb(deposit_id)
            )
        except Exception:
            try:
                await bot.send_message(
                    aid,
                    f"💳 <b>DEPOSIT REQUEST!</b>\n#{deposit_id[:8]}\n👤 <code>{dep['user_id']}</code>\n💰 ₹{dep['amount']:.2f}",
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
    await db.reject_deposit(deposit_id)
    try:
        await cq.message.edit_caption(caption="❌ Deposit cancelled.", parse_mode="HTML")
    except Exception:
        await cq.message.answer("❌ Deposit cancelled.")
    await cq.answer("Cancelled.")


# ── Wallet Pay ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wallet_pay:"))
async def wallet_pay(cq: CallbackQuery, bot: Bot):
    account_id = cq.data.split(":", 1)[1]
    acc        = await db.get_account(account_id)
    if not acc or acc["status"] != "available":
        return await cq.answer("❌ Account no longer available!", show_alert=True)

    bal = await db.get_balance(cq.from_user.id)
    if bal < acc["price"]:
        return await cq.answer(
            f"❌ Insufficient balance!\nBalance: ₹{bal:.2f}\nRequired: ₹{acc['price']:.2f}",
            show_alert=True
        )

    u          = cq.from_user
    order_id   = await db.create_order(u.id, u.username or "", u.full_name or "", account_id, acc["price"])
    deducted   = await db.deduct_balance(u.id, acc["price"])

    if not deducted:
        return await cq.answer("❌ Balance deduct nahi hua. Try again.", show_alert=True)

    # Auto approve wallet orders
    await db.approve_order(order_id)
    await db.mark_account_sold(account_id, u.id)
    await db.update_user_stats(u.id, acc["price"])
    session_id = await db.create_otp_session(order_id, u.id, account_id)

    new_bal = await db.get_balance(u.id)

    from keyboards import reveal_number_kb
    await cq.message.answer(
        f"✅ <b>Purchase Successful!</b>\n\n"
        f"💰 ₹{acc['price']:.2f} deducted from wallet\n"
        f"💼 Remaining: ₹{new_bal:.2f}\n"
        f"{acc['country_flag']} {acc['country']}\n\n"
        f"👇 Account details:",
        parse_mode="HTML",
        reply_markup=reveal_number_kb(order_id, session_id)
    )

    from utils.logger import log_sale
    await log_sale(bot, acc["number"], acc["price"], acc["country"], acc["country_flag"], u.id, u.username or "", order_id)
    await cq.answer("✅ Purchase successful!")
