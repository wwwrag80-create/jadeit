# -*- coding: utf-8 -*-
"""
اختبار منطقي لإصلاح خطأ 28000: يحاكي منطق ensure_tenant_link/client_login_full/
assert_sync_token في SQLite للتحقق من صحة التسلسل المنطقي (لا يمكن تشغيل
PL/pgSQL الحقيقي هنا، لكن هذا يثبت أن التسلسل والقرارات المنطقية صحيحة).
"""
import sqlite3
import uuid


def make_db():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE clients (
            client_id TEXT PRIMARY KEY, username TEXT, password_hash TEXT,
            business_name TEXT, can_edit INTEGER DEFAULT 1, is_active INTEGER DEFAULT 1
        );
        CREATE TABLE tenants (
            id TEXT PRIMARY KEY, business_name TEXT, is_active INTEGER DEFAULT 1,
            can_edit INTEGER DEFAULT 1, sync_token TEXT, sync_enabled INTEGER DEFAULT 1
        );
    """)
    return db


def ensure_tenant_link(db, client_id):
    """محاكاة SQL: ensure_tenant_link"""
    row = db.execute("SELECT sync_token, sync_enabled FROM tenants WHERE id=?", (client_id,)).fetchone()
    if row is not None:
        token, enabled = row
        if token is None or enabled is None:
            new_token = token or str(uuid.uuid4())
            db.execute("UPDATE tenants SET sync_token=?, sync_enabled=1 WHERE id=?", (new_token, client_id))
            db.commit()
    else:
        c = db.execute("SELECT business_name, can_edit, is_active FROM clients WHERE client_id=?",
                       (client_id,)).fetchone()
        if c is not None:
            business, can_edit, active = c
            db.execute("INSERT INTO tenants(id,business_name,is_active,can_edit,sync_token,sync_enabled) "
                      "VALUES(?,?,?,?,?,1)", (client_id, business, active, can_edit, str(uuid.uuid4())))
            db.commit()
    return db.execute("SELECT business_name, can_edit, sync_token, sync_enabled FROM tenants WHERE id=?",
                      (client_id,)).fetchone()


def client_login_full(db, username, password_hash):
    """محاكاة SQL: client_login_full"""
    row = db.execute("SELECT client_id, business_name, can_edit, is_active FROM clients "
                     "WHERE lower(username)=lower(?) AND password_hash=?", (username, password_hash)).fetchone()
    if row is None or not row[3]:
        return None
    client_id, business, can_edit, _ = row
    _, _, token, enabled = ensure_tenant_link(db, client_id)
    return {"client_id": client_id, "business_name": business, "can_edit": bool(can_edit),
            "sync_token": token, "sync_enabled": bool(enabled)}


def assert_sync_token(db, tenant_id, token, is_service_role=False):
    if is_service_role:
        return True
    row = db.execute("SELECT sync_token, is_active, sync_enabled FROM tenants WHERE id=?", (tenant_id,)).fetchone()
    if row and token is not None and row[0] == token and row[1] and row[2]:
        return True
    raise PermissionError("28000: غير مصرّح بالمزامنة لهذا الحساب")


# ============================================================================
#  السيناريو ١: عميل أُنشئ في clients لكن بلا صف tenants مطابق (سبب العطل الأصلي)
# ============================================================================
db = make_db()
CID = "client-A"
db.execute("INSERT INTO clients VALUES(?,?,?,?,1,1)", (CID, "ahmad", "hash123", "مصنع أحمد"))
db.commit()

# قبل الإصلاح: لا يوجد صف tenants إطلاقاً — هذا بالضبط سبب رسالة 28000 الأصلية
before = db.execute("SELECT COUNT(*) FROM tenants WHERE id=?", (CID,)).fetchone()[0]
assert before == 0
print("✔ إعادة إنتاج العطل الأصلي: لا يوجد صف tenants للعميل قبل أول دخول")

# الدخول يستدعي client_login_full الذي يستدعي ensure_tenant_link تلقائياً
session = client_login_full(db, "ahmad", "hash123")
assert session is not None and session["sync_token"], "الدخول لم يرجع رمز مزامنة!"
print(f"✔ الإصلاح الذاتي: أول دخول أنشأ صف tenants ورمز مزامنة تلقائياً ({session['sync_token'][:8]}…)")

# الآن رفع البيانات من جهاز العميل بهذا الرمز ينجح
assert assert_sync_token(db, CID, session["sync_token"]) is True
print("✔ رفع بيانات العميل بالرمز الجديد ينجح فوراً — لا مزيد من 28000")

# رمز خاطئ ما زال يُرفض (الأمان محفوظ)
try:
    assert_sync_token(db, CID, "رمز-خاطئ")
    raise AssertionError("قُبل رمز خاطئ!")
except PermissionError:
    print("✔ رمز خاطئ ما زال يُرفض — الإصلاح لم يفتح أي ثغرة أمنية")

# ============================================================================
#  السيناريو ٢: إعادة الدخول لا تُنشئ رمزاً جديداً (لا تُبطل الجهاز القديم)
# ============================================================================
session2 = client_login_full(db, "ahmad", "hash123")
assert session2["sync_token"] == session["sync_token"]
print("✔ إعادة الدخول لا تُغيّر الرمز — أجهزة العميل القديمة تبقى تعمل")

# ============================================================================
#  السيناريو ٣: انتحال شخصية المدير — يعمل بمفتاح الخدمة حتى بلا رمز إطلاقاً
# ============================================================================
CID2 = "client-B"
# عميل ثانٍ بلا أي صف tenants وبلا استدعاء ensure_tenant_link من قبل
db.execute("INSERT INTO clients VALUES(?,?,?,?,1,1)", (CID2, "salem", "hash456", "مصنع سالم"))
db.commit()
assert db.execute("SELECT COUNT(*) FROM tenants WHERE id=?", (CID2,)).fetchone()[0] == 0

# المدير يدخل بمفتاح الخدمة — ينجح فوراً بفضل تجاوز is_service_role،
# حتى لو لم يُستدعَ ensure_tenant_link بعد لهذا العميل تحديداً
assert assert_sync_token(db, CID2, None, is_service_role=True) is True
print("✔ انتحال الشخصية بمفتاح الخدمة ينجح فوراً — لا يحتاج رمزاً مزامنة أصلاً")

# ثم عند استدعاء ensure_tenant_link من شاشة المدير (كما يفعل open_as_client) يُصلَح أيضاً
_, _, token_b, _ = ensure_tenant_link(db, CID2)
assert token_b is not None
print(f"✔ ومع ذلك open_as_client يستدعي ensure_tenant_link فيُنشئ رمزاً حتى بلا حاجة إليه فعلياً")

# ============================================================================
#  السيناريو ٤: عميل غير موجود إطلاقاً — لا يُنشئ بيانات وهمية
# ============================================================================
ghost = "لا-يوجد-عميل-بهذا-المعرّف"
row = ensure_tenant_link(db, ghost)
assert row is None or row == (None, None, None, None)
assert db.execute("SELECT COUNT(*) FROM tenants WHERE id=?", (ghost,)).fetchone()[0] == 0
print("✔ حساب غير موجود: لا يُنشئ صفاً وهمياً — يعيد بهدوء بلا شيء")

# ============================================================================
#  السيناريو ٥: عميل موقوف لا يستطيع الدخول رغم صحة كلمة المرور
# ============================================================================
db.execute("INSERT INTO clients VALUES(?,?,?,?,1,0)", ("client-C", "off", "h", "موقوف"))
db.commit()
assert client_login_full(db, "off", "h") is None
print("✔ الحساب الموقوف يُمنع من الدخول رغم صحة كلمة المرور")

print("\n✅ كل سيناريوهات إصلاح خطأ 28000 سليمة منطقياً")
