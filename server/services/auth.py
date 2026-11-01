"""المستخدمون وتسجيل الدخول والجلسات.

كلمات المرور تُخزَّن بخوارزمية scrypt مع ملح عشوائي لكل مستخدم (لا نص واضح إطلاقاً).
رمز الجلسة يُرسل للمتصفح في كوكي HttpOnly، ويُخزَّن في القاعدة بصيغة SHA-256 فقط.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from ..db import utcnow
from ..errors import Conflict, Forbidden, NotFound, Unauthorized, ValidationError
from .common import ACCOUNTANT_DEFAULTS, PERMISSIONS, Actor, audit, clean_line

SESSION_HOURS = 12
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


# ------------------------------------------------------------------ كلمات المرور
_PBKDF2_ITER = 260000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    if not hasattr(hashlib, "scrypt"):
        # بديل آمن إن كانت نسخة OpenSSL على الجهاز لا تدعم scrypt
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
        return "pbkdf2$%d$%s$%s" % (_PBKDF2_ITER, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return "scrypt$%d$%d$%d$%s$%s" % (
        _SCRYPT["n"], _SCRYPT["r"], _SCRYPT["p"],
        base64.b64encode(salt).decode(), base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith("pbkdf2$"):
            _, iters, salt_b64, dk_b64 = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iters))
            return hmac.compare_digest(dk, base64.b64decode(dk_b64))
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(dk_b64)),
        )
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def _validate_password(password) -> str:
    if not isinstance(password, str) or len(password) < 6:
        raise ValidationError("كلمة المرور يجب ألا تقل عن 6 أحرف")
    if len(password) > 200:
        raise ValidationError("كلمة المرور طويلة جداً")
    return password


def _validate_username(username) -> str:
    u = clean_line(username, 40)
    if len(u) < 3:
        raise ValidationError("اسم المستخدم يجب ألا يقل عن 3 أحرف")
    return u


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_actor(row) -> Actor:
    return Actor(
        id=row["id"],
        username=row["username"],
        full_name=row["full_name"],
        is_admin=bool(row["is_admin"]),
        permissions=set(json.loads(row["permissions"] or "[]")),
    )


def _clean_permissions(perms) -> list:
    if not isinstance(perms, list):
        raise ValidationError("قائمة الصلاحيات غير صالحة")
    bad = [p for p in perms if p not in PERMISSIONS]
    if bad:
        raise ValidationError("صلاحيات غير معروفة: " + "، ".join(map(str, bad)))
    return sorted(set(perms))


# ------------------------------------------------------------------ الحماية من التخمين
class _Throttle:
    def __init__(self, limit=5, window=300):
        self.limit, self.window = limit, window
        self._fails = {}
        self._lock = threading.Lock()

    def check(self, key):
        with self._lock:
            now = time.time()
            fails = [t for t in self._fails.get(key, []) if now - t < self.window]
            self._fails[key] = fails
            if len(fails) >= self.limit:
                raise Forbidden("محاولات دخول كثيرة خاطئة. انتظر خمس دقائق ثم حاول مجدداً")

    def fail(self, key):
        with self._lock:
            self._fails.setdefault(key, []).append(time.time())

    def reset(self, key):
        with self._lock:
            self._fails.pop(key, None)


throttle = _Throttle()


# ------------------------------------------------------------------ الإعداد الأول
def needs_setup(db) -> bool:
    with db.read() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def setup_first_admin(db, data: dict):
    """إنشاء مدير النظام الأول وضبط عيار العمل — مرة واحدة فقط."""
    if not needs_setup(db):
        raise Conflict("تم إعداد النظام مسبقاً")
    username = _validate_username(data.get("username"))
    full_name = clean_line(data.get("full_name"), 80) or username
    password = _validate_password(data.get("password"))
    karat = data.get("working_karat")
    try:
        karat = int(karat)
    except (TypeError, ValueError):
        raise ValidationError("اختر عيار العمل المعتمد")
    if karat not in (18, 21, 22, 24):
        raise ValidationError("عيار العمل يجب أن يكون 18 أو 21 أو 22 أو 24")
    system_name = clean_line(data.get("system_name"), 80)
    wage_unit = clean_line(data.get("wage_unit"), 20)
    with db.write() as c:
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            raise Conflict("تم إعداد النظام مسبقاً")
        now = utcnow()
        cur = c.execute(
            """INSERT INTO users(username, full_name, password_hash, is_admin, permissions, created_at, updated_at)
               VALUES (?, ?, ?, 1, '[]', ?, ?)""",
            (username, full_name, hash_password(password), now, now),
        )
        uid = cur.lastrowid
        c.execute("UPDATE settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = 'working_karat'",
                  (str(karat), now, uid))
        if system_name:
            c.execute("UPDATE settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = 'system_name'",
                      (system_name, now, uid))
        if wage_unit:
            c.execute("UPDATE settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = 'wage_unit'",
                      (wage_unit, now, uid))
        c.execute(
            "INSERT INTO karat_history(karat, previous_karat, reason, changed_at, changed_by) VALUES (?, NULL, ?, ?, ?)",
            (karat, "الإعداد الأول للنظام", now, uid),
        )
        actor = Actor(uid, username, full_name, True)
        audit(c, actor, "setup", "system", uid, username, "الإعداد الأول للنظام",
              after={"working_karat": karat, "system_name": system_name})
    return actor


# ------------------------------------------------------------------ الدخول والجلسات
def login(db, username, password, client_key: str = ""):
    username = clean_line(username, 40)
    key = f"{client_key}|{username.casefold()}"
    throttle.check(key)
    with db.read() as c:
        row = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not verify_password(str(password or ""), row["password_hash"]):
        throttle.fail(key)
        raise Unauthorized("اسم المستخدم أو كلمة المرور غير صحيحة")
    if not row["is_active"]:
        raise Forbidden("هذا المستخدم موقوف. راجع مدير النظام")
    throttle.reset(key)
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with db.write() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (utcnow(),))
        c.execute(
            "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), row["id"], utcnow(),
             (now + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        audit(c, _row_to_actor(row), "login", "user", row["id"], row["username"])
    return token, _row_to_actor(row)


def actor_from_token(db, token: str | None):
    if not token:
        return None
    with db.read() as c:
        row = c.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1""",
            (_token_hash(token), utcnow()),
        ).fetchone()
    return _row_to_actor(row) if row else None


def logout(db, token: str | None):
    if not token:
        return
    with db.write() as c:
        c.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


# ------------------------------------------------------------------ إدارة المستخدمين
def _user_public(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "is_admin": bool(row["is_admin"]),
        "permissions": json.loads(row["permissions"] or "[]"),
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def list_users(db, actor: Actor):
    actor.require("users.manage")
    with db.read() as c:
        rows = c.execute("SELECT * FROM users ORDER BY id").fetchall()
    return {
        "users": [_user_public(r) for r in rows],
        "permissions": PERMISSIONS,
        "accountant_defaults": ACCOUNTANT_DEFAULTS,
    }


def create_user(db, actor: Actor, data: dict):
    actor.require("users.manage")
    username = _validate_username(data.get("username"))
    full_name = clean_line(data.get("full_name"), 80) or username
    password = _validate_password(data.get("password"))
    is_admin = bool(data.get("is_admin"))
    perms = _clean_permissions(data.get("permissions", []))
    with db.write() as c:
        if c.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise Conflict("اسم المستخدم مستخدم مسبقاً")
        now = utcnow()
        cur = c.execute(
            """INSERT INTO users(username, full_name, password_hash, is_admin, permissions, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, full_name, hash_password(password), int(is_admin), json.dumps(perms), now, now),
        )
        audit(c, actor, "user_create", "user", cur.lastrowid, username,
              after={"full_name": full_name, "is_admin": is_admin, "permissions": perms})
        row = c.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _user_public(row)


def update_user(db, actor: Actor, user_id: int, data: dict):
    actor.require("users.manage")
    with db.write() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise NotFound("المستخدم غير موجود")
        before = _user_public(row)
        full_name = clean_line(data.get("full_name", row["full_name"]), 80) or row["username"]
        is_admin = bool(data.get("is_admin", row["is_admin"]))
        is_active = bool(data.get("is_active", row["is_active"]))
        perms = _clean_permissions(data.get("permissions", before["permissions"]))
        if user_id == actor.id and (not is_admin or not is_active):
            raise ValidationError("لا يمكنك إلغاء صلاحية المدير أو إيقاف حسابك أنت")
        if row["is_admin"] and (not is_admin or not is_active):
            admins = c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1 AND is_active = 1").fetchone()[0]
            if admins <= 1:
                raise ValidationError("يجب أن يبقى مدير نظام واحد نشط على الأقل")
        pw_hash = row["password_hash"]
        if data.get("password"):
            pw_hash = hash_password(_validate_password(data["password"]))
        c.execute(
            """UPDATE users SET full_name = ?, is_admin = ?, is_active = ?, permissions = ?,
                      password_hash = ?, updated_at = ? WHERE id = ?""",
            (full_name, int(is_admin), int(is_active), json.dumps(perms), pw_hash, utcnow(), user_id),
        )
        if not is_active or data.get("password"):
            c.execute("DELETE FROM sessions WHERE user_id = ? AND user_id <> ?", (user_id, actor.id))
        after = _user_public(c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
        audit(c, actor, "user_update", "user", user_id, row["username"],
              reason="تغيير كلمة المرور" if data.get("password") else "",
              before=before, after=after)
    return after


def change_own_password(db, actor: Actor, current: str, new: str):
    with db.write() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (actor.id,)).fetchone()
        if not verify_password(str(current or ""), row["password_hash"]):
            raise ValidationError("كلمة المرور الحالية غير صحيحة")
        c.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                  (hash_password(_validate_password(new)), utcnow(), actor.id))
        audit(c, actor, "password_change", "user", actor.id, actor.username)
