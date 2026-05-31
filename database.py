"""
database.py — MongoDB version using Motor (async)
All data persists across Railway restarts.
"""

import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

_client = None
_db     = None


def get_db():
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(MONGO_URI)
        _db     = _client["accountbot"]
    return _db


async def init_db():
    db = get_db()
    # Create indexes for fast lookups
    await db.accounts.create_index("status")
    await db.accounts.create_index("country")
    await db.orders.create_index("user_id")
    await db.orders.create_index("status")
    await db.users.create_index("user_id", unique=True)
    await db.otp_sessions.create_index("status")
    await db.otp_sessions.create_index("order_id")

    # Default settings
    await db.settings.update_one(
        {"key": "maintenance"},
        {"$setOnInsert": {"key": "maintenance", "value": "0"}},
        upsert=True
    )
    await db.settings.update_one(
        {"key": "maintenance_msg"},
        {"$setOnInsert": {"key": "maintenance_msg", "value": "🔧 Bot is under maintenance. Please check back later!"}},
        upsert=True
    )
    print("✅ MongoDB connected!")


# ── Settings ──────────────────────────────────────────────────────────────────

async def get_setting(key: str) -> str:
    db = get_db()
    r = await db.settings.find_one({"key": key})
    return r["value"] if r else ""

async def set_setting(key: str, value: str):
    db = get_db()
    await db.settings.update_one(
        {"key": key},
        {"$set": {"value": value}},
        upsert=True
    )

async def is_maintenance() -> bool:
    return (await get_setting("maintenance")) == "1"

async def get_maintenance_msg() -> str:
    return await get_setting("maintenance_msg")


# ── Accounts ──────────────────────────────────────────────────────────────────

async def add_account(number, price, country, country_flag,
                      password="", twofa="", session_str="", description=""):
    db  = get_db()
    now = datetime.datetime.now().isoformat()
    await db.accounts.insert_one({
        "number":       number,
        "password":     password,
        "twofa":        twofa,
        "session_str":  session_str,
        "country":      country,
        "country_flag": country_flag,
        "price":        price,
        "description":  description,
        "status":       "available",
        "added_at":     now,
        "sold_at":      None,
        "sold_to":      None,
    })

async def _doc_to_account(doc) -> dict | None:
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    return doc

async def get_available_accounts():
    db = get_db()
    cursor = db.accounts.find({"status": "available"}).sort([("country", 1), ("_id", 1)])
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        results.append(doc)
    return results

async def get_available_by_country(country):
    db = get_db()
    cursor = db.accounts.find({"status": "available", "country": country}).sort("_id", 1)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        results.append(doc)
    return results

async def get_country_stock():
    db = get_db()
    pipeline = [
        {"$match": {"status": "available"}},
        {"$group": {
            "_id":          "$country",
            "flag":         {"$first": "$country_flag"},
            "price":        {"$first": "$price"},
            "count":        {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    results = []
    async for doc in db.accounts.aggregate(pipeline):
        results.append({
            "country": doc["_id"],
            "flag":    doc["flag"],
            "price":   doc["price"],
            "count":   doc["count"]
        })
    return results

async def get_account(account_id: str):
    db = get_db()
    from bson import ObjectId
    try:
        doc = await db.accounts.find_one({"_id": ObjectId(account_id)})
    except Exception:
        doc = await db.accounts.find_one({"_id": account_id})
    if doc:
        doc["id"] = str(doc["_id"])
    return doc

async def get_all_accounts():
    db = get_db()
    cursor = db.accounts.find().sort([("status", 1), ("_id", -1)])
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        results.append(doc)
    return results

async def mark_account_sold(account_id: str, user_id: int):
    db  = get_db()
    now = datetime.datetime.now().isoformat()
    from bson import ObjectId
    try:
        await db.accounts.update_one(
            {"_id": ObjectId(account_id)},
            {"$set": {"status": "sold", "sold_at": now, "sold_to": user_id}}
        )
    except Exception:
        pass

async def delete_account(account_id: str):
    db = get_db()
    from bson import ObjectId
    try:
        await db.accounts.delete_one({"_id": ObjectId(account_id)})
    except Exception:
        pass

async def update_account(account_id: str, **kwargs):
    allowed = ["price","password","twofa","session_str","description","country","country_flag"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    db = get_db()
    from bson import ObjectId
    try:
        await db.accounts.update_one({"_id": ObjectId(account_id)}, {"$set": updates})
    except Exception:
        pass


# ── Orders ────────────────────────────────────────────────────────────────────

async def create_order(user_id, username, full_name, account_id, amount) -> str:
    db  = get_db()
    now = datetime.datetime.now().isoformat()
    result = await db.orders.insert_one({
        "user_id":     user_id,
        "username":    username,
        "full_name":   full_name,
        "account_id":  account_id,
        "amount":      amount,
        "screenshot":  "",
        "status":      "pending",
        "created_at":  now,
        "approved_at": None,
    })
    return str(result.inserted_id)

async def get_order(order_id: str):
    db = get_db()
    from bson import ObjectId
    try:
        doc = await db.orders.find_one({"_id": ObjectId(order_id)})
    except Exception:
        return None
    if doc:
        doc["id"] = str(doc["_id"])
    return doc

async def get_pending_orders():
    db = get_db()
    cursor = db.orders.find({"status": "pending"}).sort("created_at", -1)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        results.append(doc)
    return results

async def get_all_orders(limit=50):
    db = get_db()
    cursor = db.orders.find().sort("created_at", -1).limit(limit)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        results.append(doc)
    return results

async def get_user_orders(user_id: int):
    db = get_db()
    cursor = db.orders.find({"user_id": user_id}).sort("created_at", -1)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        results.append(doc)
    return results

async def approve_order(order_id: str):
    db  = get_db()
    now = datetime.datetime.now().isoformat()
    from bson import ObjectId
    await db.orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": "approved", "approved_at": now}}
    )

async def reject_order(order_id: str):
    db = get_db()
    from bson import ObjectId
    await db.orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "rejected"}})

async def set_order_screenshot(order_id: str, file_id: str):
    db = get_db()
    from bson import ObjectId
    await db.orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"screenshot": file_id}})


# ── Users ─────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str, full_name: str):
    db  = get_db()
    now = datetime.datetime.now().isoformat()
    await db.users.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"joined_at": now, "total_spent": 0, "total_orders": 0, "is_banned": False, "ban_reason": "", "balance": 0.0},
         "$set": {"username": username, "full_name": full_name}},
        upsert=True
    )

async def get_user(user_id: int):
    db  = get_db()
    doc = await db.users.find_one({"user_id": user_id})
    return doc

async def get_all_users():
    db = get_db()
    cursor = db.users.find().sort("joined_at", -1)
    results = []
    async for doc in cursor:
        results.append(doc)
    return results

async def update_user_stats(user_id: int, amount: float):
    db = get_db()
    await db.users.update_one(
        {"user_id": user_id},
        {"$inc": {"total_spent": amount, "total_orders": 1}}
    )

async def ban_user(user_id: int, reason: str = "No reason provided"):
    db = get_db()
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"is_banned": True, "ban_reason": reason}}
    )

async def unban_user(user_id: int):
    db = get_db()
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"is_banned": False, "ban_reason": ""}}
    )

async def is_banned(user_id: int) -> bool:
    db  = get_db()
    doc = await db.users.find_one({"user_id": user_id}, {"is_banned": 1})
    return bool(doc and doc.get("is_banned"))

# ── Wallet / Deposit ──────────────────────────────────────────────────────────

async def get_balance(user_id: int) -> float:
    db  = get_db()
    doc = await db.users.find_one({"user_id": user_id}, {"balance": 1})
    return float(doc.get("balance", 0)) if doc else 0.0

async def add_balance(user_id: int, amount: float):
    db = get_db()
    await db.users.update_one({"user_id": user_id}, {"$inc": {"balance": amount}})

async def deduct_balance(user_id: int, amount: float) -> bool:
    db  = get_db()
    doc = await db.users.find_one({"user_id": user_id}, {"balance": 1})
    bal = float(doc.get("balance", 0)) if doc else 0.0
    if bal < amount:
        return False
    await db.users.update_one({"user_id": user_id}, {"$inc": {"balance": -amount}})
    return True

async def create_deposit(user_id: int, username: str, amount: float, exact_amount: float) -> str:
    db  = get_db()
    now = datetime.datetime.now().isoformat()
    result = await db.deposits.insert_one({
        "user_id":      user_id,
        "username":     username,
        "amount":       amount,
        "exact_amount": exact_amount,
        "screenshot":   "",
        "status":       "pending",
        "created_at":   now,
    })
    return str(result.inserted_id)

async def get_deposit(deposit_id: str):
    db = get_db()
    from bson import ObjectId
    try:
        doc = await db.deposits.find_one({"_id": ObjectId(deposit_id)})
        if doc:
            doc["id"] = str(doc["_id"])
        return doc
    except Exception:
        return None

async def set_deposit_screenshot(deposit_id: str, file_id: str):
    db = get_db()
    from bson import ObjectId
    await db.deposits.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"screenshot": file_id}})

async def approve_deposit(deposit_id: str):
    db  = get_db()
    now = datetime.datetime.now().isoformat()
    from bson import ObjectId
    doc = await db.deposits.find_one({"_id": ObjectId(deposit_id)})
    if doc:
        await db.deposits.update_one(
            {"_id": ObjectId(deposit_id)},
            {"$set": {"status": "approved", "approved_at": now}}
        )
        await add_balance(doc["user_id"], doc["amount"])

async def reject_deposit(deposit_id: str):
    db = get_db()
    from bson import ObjectId
    await db.deposits.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"status": "rejected"}})

async def get_pending_deposits():
    db = get_db()
    cursor = db.deposits.find({"status": "pending"}).sort("created_at", -1)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        results.append(doc)
    return results

# ── Stats ─────────────────────────────────────────────────────────────────────

async def get_stats():
    db  = get_db()
    ta  = await db.accounts.count_documents({})
    av  = await db.accounts.count_documents({"status": "available"})
    sol = await db.accounts.count_documents({"status": "sold"})
    tu  = await db.users.count_documents({})
    ban = await db.users.count_documents({"is_banned": True})
    po  = await db.orders.count_documents({"status": "pending"})
    ao  = await db.orders.count_documents({"status": "approved"})
    pd  = await db.deposits.count_documents({"status": "pending"}) if hasattr(db, 'deposits') else 0

    # Total revenue
    pipeline = [{"$match": {"status": "approved"}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    rev_doc  = await db.orders.aggregate(pipeline).to_list(1)
    rev      = rev_doc[0]["total"] if rev_doc else 0

    return {
        "total_accounts": ta, "available": av, "sold": sol,
        "users": tu, "banned": ban, "revenue": rev,
        "pending": po, "approved_orders": ao, "pending_deposits": pd
    }

# ── OTP Sessions ──────────────────────────────────────────────────────────────

async def create_otp_session(order_id: str, user_id: int, account_id: str) -> str:
    db  = get_db()
    now = datetime.datetime.now().isoformat()
    result = await db.otp_sessions.insert_one({
        "order_id":   order_id,
        "user_id":    user_id,
        "account_id": account_id,
        "otp_code":   "",
        "status":     "waiting",
        "created_at": now,
    })
    return str(result.inserted_id)

async def get_otp_session(session_id: str):
    db = get_db()
    from bson import ObjectId
    try:
        doc = await db.otp_sessions.find_one({"_id": ObjectId(session_id)})
        if doc:
            doc["id"] = str(doc["_id"])
        return doc
    except Exception:
        return None

async def deliver_otp(session_id: str, otp_code: str):
    db = get_db()
    from bson import ObjectId
    await db.otp_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"otp_code": otp_code, "status": "delivered"}}
    )

async def get_waiting_otp_sessions():
    db = get_db()
    cursor = db.otp_sessions.find({"status": "waiting"}).sort("created_at", -1)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        results.append(doc)
    return results
