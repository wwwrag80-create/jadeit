"""الإعدادات العامة: عيار العمل المعتمد، اسم النظام، وحدات العرض."""
from __future__ import annotations

from ..db import utcnow
from ..errors import ValidationError
from .common import Actor, audit, clean_line, get_setting


def get_settings(db) -> dict:
    with db.read() as c:
        rows = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}
        gold_refs = [r[0] for r in c.execute(
            "SELECT DISTINCT ref_karat FROM ledger_entries WHERE material = 'gold' ORDER BY ref_karat")]
        has_diamond = c.execute(
            "SELECT 1 FROM ledger_entries WHERE material = 'diamond' LIMIT 1").fetchone() is not None
    return {
        "system_name": rows.get("system_name", ""),
        "working_karat": int(rows.get("working_karat", "18")),
        "wage_unit": rows.get("wage_unit", ""),
        "diamond_unit": rows.get("diamond_unit", ""),
        "gold_ref_karats_in_use": gold_refs,
        "diamond_unit_locked": has_diamond,
    }


def karat_history(db):
    with db.read() as c:
        rows = c.execute(
            """SELECT k.*, u.full_name AS user_name FROM karat_history k
               LEFT JOIN users u ON u.id = k.changed_by ORDER BY k.id DESC""").fetchall()
    return [dict(r) for r in rows]


def change_working_karat(db, actor: Actor, karat, reason):
    """تغيير عيار العمل للعمليات الجديدة فقط.

    المستندات المرحّلة تحتفظ بعيارها (لقطة وقت الترحيل) ولا يُعاد حسابها.
    """
    actor.require("settings.manage")
    try:
        karat = int(karat)
    except (TypeError, ValueError):
        raise ValidationError("اختر عياراً صحيحاً")
    if karat not in (18, 21, 22, 24):
        raise ValidationError("عيار العمل يجب أن يكون 18 أو 21 أو 22 أو 24")
    reason = clean_line(reason, 300)
    if len(reason) < 3:
        raise ValidationError("اكتب سبب تغيير عيار العمل")
    with db.write() as c:
        previous = int(get_setting(c, "working_karat") or 18)
        if previous == karat:
            raise ValidationError("هذا هو عيار العمل الحالي بالفعل")
        now = utcnow()
        c.execute("UPDATE settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = 'working_karat'",
                  (str(karat), now, actor.id))
        c.execute(
            "INSERT INTO karat_history(karat, previous_karat, reason, changed_at, changed_by) VALUES (?, ?, ?, ?, ?)",
            (karat, previous, reason, now, actor.id),
        )
        audit(c, actor, "karat_change", "settings", None, "working_karat", reason,
              before={"working_karat": previous}, after={"working_karat": karat})
    return get_settings(db)


def update_general(db, actor: Actor, data: dict):
    actor.require("settings.manage")
    with db.write() as c:
        current = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}
        changes = {}
        for key, max_len in (("system_name", 80), ("wage_unit", 20), ("diamond_unit", 20)):
            if key in data:
                value = clean_line(data[key], max_len)
                if not value:
                    raise ValidationError("لا يجوز ترك الحقل فارغاً")
                if value != current.get(key):
                    changes[key] = value
        if "diamond_unit" in changes:
            used = c.execute("SELECT 1 FROM ledger_entries WHERE material = 'diamond' LIMIT 1").fetchone()
            if used:
                raise ValidationError(
                    "لا يمكن تغيير وحدة وزن الألماس بعد وجود حركات ألماس مرحّلة، لأن ذلك يغيّر معنى الأرقام المسجلة")
        now = utcnow()
        for key, value in changes.items():
            c.execute("UPDATE settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = ?",
                      (value, now, actor.id, key))
        if changes:
            audit(c, actor, "settings_update", "settings", None, "general",
                  before={k: current.get(k) for k in changes}, after=changes)
    return get_settings(db)
