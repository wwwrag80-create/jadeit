"""حسابات العملاء: الإنشاء والتعديل والبحث.

• رقم الحساب تلقائي وفريد (يبدأ من 1001).
• الاسم فريد بعد التوحيد (راجع common.name_key).
• تعديل الأجر الافتراضي لا يغيّر أجور المستندات المرحّلة، لأن كل سطر يحفظ أجره.
"""
from __future__ import annotations

import re

from .. import fixed as F
from ..db import next_seq, peek_seq, utcnow
from ..errors import Conflict, NotFound, ValidationError
from .common import Actor, audit, clean_line, clean_text, client_token, name_key

ACCOUNT_SEQ = "account"
ACCOUNT_START = 1001


def _public(row) -> dict:
    return {
        "id": row["id"],
        "account_no": row["account_no"],
        "name": row["name"],
        "phone": row["phone"],
        "notes": row["notes"],
        "wage_rate": F.fmt_rate(row["wage_rate_e4"]),
        "is_active": bool(row["is_active"]),
        "version": row["version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _validate_name(value) -> str:
    name = clean_line(value, 100)
    if len(name) < 2:
        raise ValidationError("اسم الحساب مطلوب (حرفان على الأقل)", {"field": "name"})
    return name


def _validate_phone(value) -> str:
    phone = F.normalize_digits(clean_line(value, 30))
    if not phone:
        return ""
    if not re.fullmatch(r"\+?[0-9][0-9 \-]{4,24}", phone):
        raise ValidationError("رقم الجوال غير صالح (أرقام فقط مع + أو - اختيارياً)", {"field": "phone"})
    return phone


def _validate_rate(value) -> int:
    try:
        return F.parse(value, F.DP_RATE, "الأجر المعتمد", allow_zero=True)
    except F.FixedError as e:
        raise ValidationError(str(e), {"field": "wage_rate"})


def _name_conflict(c, key: str, exclude_id=None):
    row = c.execute("SELECT id, account_no, name FROM accounts WHERE name_key = ?", (key,)).fetchone()
    if row and row["id"] != exclude_id:
        return row
    return None


def list_accounts(db, q: str = "", include_inactive: bool = True, limit: int = 5000):
    q = clean_line(q, 100)
    sql = "SELECT * FROM accounts"
    args = []
    where = []
    if not include_inactive:
        where.append("is_active = 1")
    if q:
        where.append("(name_key LIKE ? OR account_no LIKE ? OR phone LIKE ?)")
        like = f"%{name_key(q)}%"
        args += [like, f"%{q}%", f"%{F.normalize_digits(q)}%"]
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CAST(account_no AS INTEGER) LIMIT ?"
    args.append(int(limit))
    with db.read() as c:
        rows = c.execute(sql, args).fetchall()
    return [_public(r) for r in rows]


def get_account(db, account_id: int) -> dict:
    with db.read() as c:
        row = c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise NotFound("الحساب غير موجود")
    return _public(row)


def next_account_no(db) -> str:
    with db.read() as c:
        return str(peek_seq(c, ACCOUNT_SEQ, ACCOUNT_START))


def check_name(db, name: str, exclude_id=None):
    key = name_key(name or "")
    if not key:
        return {"available": True}
    with db.read() as c:
        row = _name_conflict(c, key, exclude_id)
    if row:
        return {"available": False, "account_no": row["account_no"], "name": row["name"], "id": row["id"]}
    return {"available": True}


def create_account(db, actor: Actor, data: dict) -> dict:
    actor.require("accounts.manage")
    token = client_token(data.get("client_token"))
    name = _validate_name(data.get("name"))
    phone = _validate_phone(data.get("phone"))
    notes = clean_text(data.get("notes"), 1000)
    if data.get("wage_rate") in (None, ""):
        raise ValidationError("الأجر المعتمد للحساب مطلوب (اكتب 0 إن لم يكن هناك أجر)", {"field": "wage_rate"})
    rate = _validate_rate(data.get("wage_rate"))
    key = name_key(name)
    with db.write() as c:
        existing = c.execute("SELECT * FROM accounts WHERE client_token = ?", (token,)).fetchone()
        if existing:
            # الطلب نفسه وصل مرة أخرى (ضغط مكرر أو إعادة إرسال) — لا ننشئ حساباً ثانياً
            out = _public(existing)
            out["duplicate_request"] = True
            return out
        conflict = _name_conflict(c, key)
        if conflict:
            raise Conflict(
                f"يوجد حساب بالاسم نفسه: {conflict['name']} (رقم {conflict['account_no']})",
                {"field": "name", "account_id": conflict["id"]},
                code="duplicate_name",
            )
        while True:
            number = str(next_seq(c, ACCOUNT_SEQ, ACCOUNT_START))
            if not c.execute("SELECT 1 FROM accounts WHERE account_no = ?", (number,)).fetchone():
                break
        now = utcnow()
        cur = c.execute(
            """INSERT INTO accounts(account_no, name, name_key, phone, notes, wage_rate_e4, client_token,
                                    created_at, created_by, updated_at, updated_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (number, name, key, phone, notes, rate, token, now, actor.id, now, actor.id),
        )
        row = c.execute("SELECT * FROM accounts WHERE id = ?", (cur.lastrowid,)).fetchone()
        out = _public(row)
        audit(c, actor, "account_create", "account", row["id"], number, after=out)
    return out


def update_account(db, actor: Actor, account_id: int, data: dict) -> dict:
    actor.require("accounts.manage")
    with db.write() as c:
        row = c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            raise NotFound("الحساب غير موجود")
        if int(data.get("version", 0)) != row["version"]:
            raise Conflict("تم تعديل هذا الحساب من مستخدم آخر. أعد فتحه ثم عدّل", code="stale")
        before = _public(row)
        name = _validate_name(data.get("name", row["name"]))
        phone = _validate_phone(data.get("phone", row["phone"]))
        notes = clean_text(data.get("notes", row["notes"]), 1000)
        rate = _validate_rate(data["wage_rate"]) if "wage_rate" in data else row["wage_rate_e4"]
        is_active = bool(data.get("is_active", row["is_active"]))
        if rate != row["wage_rate_e4"]:
            actor.require("accounts.wage", "لا تملك صلاحية تعديل الأجر الافتراضي للحساب")
        key = name_key(name)
        conflict = _name_conflict(c, key, exclude_id=account_id)
        if conflict:
            raise Conflict(
                f"يوجد حساب بالاسم نفسه: {conflict['name']} (رقم {conflict['account_no']})",
                {"field": "name", "account_id": conflict["id"]},
                code="duplicate_name",
            )
        c.execute(
            """UPDATE accounts SET name = ?, name_key = ?, phone = ?, notes = ?, wage_rate_e4 = ?,
                      is_active = ?, version = version + 1, updated_at = ?, updated_by = ?
               WHERE id = ?""",
            (name, key, phone, notes, rate, int(is_active), utcnow(), actor.id, account_id),
        )
        after = _public(c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone())
        changed = {k: after[k] for k in ("name", "phone", "notes", "wage_rate", "is_active") if before[k] != after[k]}
        if changed:
            audit(c, actor, "account_update", "account", account_id, row["account_no"],
                  reason=clean_line(data.get("reason"), 300),
                  before={k: before[k] for k in changed}, after=changed)
    return after
