"""النسخ الاحتياطي والاستعادة وسجل التدقيق العام."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime

from ..db import SCHEMA_VERSION
from ..errors import ValidationError
from .common import Actor, audit

REQUIRED_TABLES = {"users", "accounts", "documents", "trade_lines", "voucher_details", "opening_lines",
                   "ledger_entries", "audit_log", "settings", "account_balances"}
KEEP_AUTO = 30


def backups_dir(db) -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(db.path)), "backups")
    os.makedirs(d, exist_ok=True)
    return d


def _copy_to(db, dest: str):
    src = sqlite3.connect(db.path)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def auto_backup(db, label: str = "auto") -> str | None:
    """نسخة تلقائية عند تشغيل الخادم (يُحتفظ بآخر 30 نسخة)."""
    if not os.path.exists(db.path) or os.path.getsize(db.path) == 0:
        return None
    d = backups_dir(db)
    name = f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    path = os.path.join(d, name)
    _copy_to(db, path)
    autos = sorted(f for f in os.listdir(d) if f.startswith(label + "-") and f.endswith(".db"))
    for old in autos[:-KEEP_AUTO]:
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    return path


def list_backups(db, actor: Actor):
    actor.require("system.backup")
    d = backups_dir(db)
    out = []
    for f in sorted(os.listdir(d), reverse=True):
        if f.endswith(".db"):
            p = os.path.join(d, f)
            out.append({"name": f, "size": os.path.getsize(p),
                        "modified": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")})
    return {"directory": d, "files": out}


def make_download(db, actor: Actor):
    actor.require("system.backup")
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _copy_to(db, tmp)
        with open(tmp, "rb") as f:
            data = f.read()
    finally:
        os.remove(tmp)
    with db.write() as c:
        audit(c, actor, "backup_download", "system", None, "backup")
    name = f"jadeit-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    return name, data


def _validate_backup_file(path: str):
    try:
        c = sqlite3.connect(path)
        try:
            ok = c.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise ValidationError("ملف النسخة الاحتياطية تالف")
            version = c.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise ValidationError("إصدار ملف النسخة الاحتياطية غير متوافق مع هذا البرنامج")
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not REQUIRED_TABLES.issubset(tables):
                raise ValidationError("الملف ليس نسخة احتياطية لهذا النظام")
            admins = c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1 AND is_active = 1").fetchone()[0]
            if admins == 0:
                raise ValidationError("النسخة لا تحتوي على مدير نظام نشط")
        finally:
            c.close()
    except sqlite3.DatabaseError:
        raise ValidationError("الملف ليس قاعدة بيانات صالحة")


def restore(db, actor: Actor, data: bytes) -> dict:
    actor.require("system.backup")
    if not data or len(data) < 1024:
        raise ValidationError("اختر ملف نسخة احتياطية صالحاً")
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        _validate_backup_file(tmp)
        safety = auto_backup(db, label="before-restore")
        with db._write_lock:
            src = sqlite3.connect(tmp)
            try:
                dst = db.conn()
                src.backup(dst)
            finally:
                src.close()
            db.reset_connections()
        with db.write() as c:
            audit(c, None, "restore", "system", None, actor.username,
                  reason=f"استعادة نسخة احتياطية بواسطة {actor.full_name}",
                  after={"safety_backup": os.path.basename(safety) if safety else None})
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return {"restored": True, "safety_backup": os.path.basename(safety) if safety else None}


ACTION_LABELS = {
    "setup": "إعداد النظام", "login": "تسجيل دخول", "post": "ترحيل", "edit": "تعديل", "cancel": "إلغاء",
    "account_create": "إنشاء حساب", "account_update": "تعديل حساب", "karat_change": "تغيير عيار العمل",
    "settings_update": "تعديل الإعدادات", "user_create": "إنشاء مستخدم", "user_update": "تعديل مستخدم",
    "password_change": "تغيير كلمة المرور", "backup_download": "تنزيل نسخة احتياطية", "restore": "استعادة نسخة",
}


def list_audit(db, actor: Actor, params: dict) -> dict:
    actor.require("system.backup")
    where, args = [], []
    if params.get("entity"):
        where.append("a.entity = ?")
        args.append(params["entity"])
    if params.get("action"):
        where.append("a.action = ?")
        args.append(params["action"])
    if params.get("exclude_login") == "1":
        where.append("a.action <> 'login'")
    if params.get("q"):
        where.append("a.ref LIKE ?")
        args.append(f"%{str(params['q'])[:40]}%")
    page = max(1, int(params.get("page") or 1))
    size = 50
    sql = "SELECT a.*, u.full_name FROM audit_log a LEFT JOIN users u ON u.id = a.user_id"
    if where:
        sql += " WHERE " + " AND ".join(where)
    with db.read() as c:
        total = c.execute(f"SELECT COUNT(*) FROM ({sql})", args).fetchone()[0]
        rows = c.execute(sql + " ORDER BY a.id DESC LIMIT ? OFFSET ?", args + [size, (page - 1) * size]).fetchall()
    return {
        "items": [{
            "id": r["id"], "at": r["at"], "user": r["full_name"] or "", "action": r["action"],
            "action_label": ACTION_LABELS.get(r["action"], r["action"]), "entity": r["entity"],
            "entity_id": r["entity_id"], "ref": r["ref"], "reason": r["reason"],
            "before": json.loads(r["before_json"]) if r["before_json"] else None,
            "after": json.loads(r["after_json"]) if r["after_json"] else None,
        } for r in rows],
        "total": total, "page": page, "pages": max(1, -(-total // size)),
    }

