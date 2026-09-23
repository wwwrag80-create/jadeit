# -*- coding: utf-8 -*-
"""
اختبار سلوكي حقيقي لمحرك المزامنة (cloud_sync.py) — يشغّل المحرك فعلاً على
قاعدة SQLite مؤقتة وخادم وهمي، بدل البحث عن نصوص داخل الكود.

يتحقق من:
  ١) الرفع يعمل، ويزيل التكرار، وينقل حالة MEMO كما هي (لا ACTIVE).
  ٢) السحابة القديمة التي لا تعرف MEMO: إعادة محاولة تلقائية بحالة SETTLED.
  ٣) قاعدة الاتجاه الواحد: المحرك لا يسحب ولا يكتب في قاعدة العميل افتراضياً.
  ٤) لو فُعّل السحب صراحةً يعمل بلا أخطاء (كان يسقط بـ NameError) ويحترم
     الحركات المحلية غير المرفوعة.
  ٥) تواريخ السحابة (UTC) تُحوَّل لتوقيت الجهاز لا تُقصّ.
"""
import os
import sqlite3
import sys
import tempfile
import time

os.environ["TZ"] = "Asia/Riyadh"
if hasattr(time, "tzset"):
    time.tzset()

# ويندوز لا يدعم ضبط التوقيت من داخل الاختبار (لا tzset): الأرقام الثابتة أدناه
# محسوبة لتوقيت الرياض، فتُقارَن بها فقط لو كان الجهاز على +03:00 فعلاً،
# وإلا يُقارَن بالتحويل المحلي — حتى لا يفشل البناء لمجرد ضبط ساعة الجهاز.
RIYADH = time.localtime().tm_gmtoff == 3 * 3600


def local(iso_utc):
    """التاريخ نفسه بتوقيت هذا الجهاز (المرجع حين لا يكون الجهاز على توقيت الرياض)"""
    from datetime import datetime
    return datetime.fromisoformat(iso_utc).astimezone().replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud_sync  # noqa: E402
from cloud_sync import CloudSync, install_sync_schema  # noqa: E402
from sync_down import _sqlite_dt  # noqa: E402


class FakeApi:
    def __init__(self, reject_memo=False, changes=None):
        self.calls = []
        self.reject_memo = reject_memo
        self.changes = changes or {}

    def rpc(self, name, payload=None):
        self.calls.append((name, payload))
        if name == "sync_push_transactions" and self.reject_memo:
            if any(r.get("status") == "MEMO" for r in payload["p_rows"]):
                raise RuntimeError('invalid input value for enum txn_status: "MEMO"')
        if name == "sync_pull_changes":
            return self.changes
        return None

    def names(self):
        return [c[0] for c in self.calls]


def fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    install_sync_schema(path)
    return path


def add_invoice(path, inv_id, op, weight, status="ACTIVE", date="2026-09-01 10:00:00"):
    con = sqlite3.connect(path)
    con.execute("""INSERT OR REPLACE INTO invoices
        (invoice_id, date_time, name, op_type, weight, before_w, after_w, note,
         settled_status, trees_count, set_number, row_number, manual_no)
        VALUES (?,?,?,?,?,0,0,'',?,0,'','','')""", (inv_id, date, "عميل", op, weight, status))
    con.commit()
    con.close()


# ═══ ١) الرفع + إزالة التكرار + حالة MEMO ═══
db = fresh_db()
add_invoice(db, 1, "مبيعات ذهب", 10)
add_invoice(db, 1, "مبيعات ذهب", 12)          # تعديل متتالٍ لنفس الحركة
add_invoice(db, 2, "خياس طقوم", 0.5, status="MEMO")
api = FakeApi()
engine = CloudSync(db_path=db, api=api, tenant_id="t-1")
engine.flush()
pushes = [p for n, p in api.calls if n == "sync_push_transactions"]
assert len(pushes) == 1, api.names()
rows = {r["seq_no"]: r for r in pushes[0]["p_rows"]}
assert len(pushes[0]["p_rows"]) == 2, "التكرار لم يُزل قبل الإرسال"
assert rows[1]["weight"] == 12, "لم تُرفع آخر نسخة من الحركة"
assert rows[2]["status"] == "MEMO", f"السطر المعلوماتي رُفع بحالة {rows[2]['status']}"
assert rows[1]["txn_date"].endswith("+03:00") or not RIYADH, rows[1]["txn_date"]
assert engine.pending_count() == 0, "صندوق الصادر لم يُفرَّغ بعد الرفع"
print("✔ الرفع يعمل ويزيل التكرار ويحفظ حالة MEMO")

# ═══ ٢) سحابة قديمة لا تعرف MEMO ═══
db2 = fresh_db()
add_invoice(db2, 5, "خياس طقوم", 0.3, status="MEMO")
api2 = FakeApi(reject_memo=True)
engine2 = CloudSync(db_path=db2, api=api2, tenant_id="t-1")
engine2.flush()
pushes2 = [p for n, p in api2.calls if n == "sync_push_transactions"]
assert len(pushes2) == 2, "لم تُعد المحاولة بعد رفض MEMO"
assert pushes2[-1]["p_rows"][0]["status"] == "SETTLED", "لم تتحوّل MEMO إلى SETTLED"
assert engine2.pending_count() == 0
print("✔ السحابة القديمة: إعادة محاولة تلقائية بحالة SETTLED (لا تدخل الأرصدة)")

# ═══ ٣) الاتجاه الواحد: لا سحب افتراضياً ═══
db3 = fresh_db()
add_invoice(db3, 7, "وارد ذهب (عيار 18)", 100)
cloud_change = {
    "server_time": "2026-09-01T12:00:00+00:00", "full_resync": True, "has_more": False,
    "changed": [{"seq_no": 7, "txn_date": "2026-09-01T09:00:00+00:00", "account_name": "المدير",
                 "op_type": "وارد ذهب (عيار 18)", "weight": 999, "status": "ACTIVE"}],
    "deleted": [],
}
api3 = FakeApi(changes=cloud_change)
engine3 = CloudSync(db_path=db3, api=api3, tenant_id="t-1")
assert engine3.pull_enabled is False, "السحب يجب أن يكون معطّلاً افتراضياً"
engine3.start()
time.sleep(1.5)
engine3.stop()
assert "sync_pull_changes" not in api3.names(), "نسخة العميل سحبت من السحابة!"
con = sqlite3.connect(db3)
w = con.execute("SELECT weight FROM invoices WHERE invoice_id=7").fetchone()[0]
con.close()
assert w == 100, "بيانات العميل تغيّرت من السحابة!"
assert engine3.last_error is None, engine3.last_error
print("✔ الاتجاه الواحد: المحرك يرفع فقط ولا يكتب في قاعدة العميل")

# ═══ ٤) السحب عند تفعيله صراحةً ═══
db4 = fresh_db()
add_invoice(db4, 8, "وارد الماس", 1)   # في صندوق الصادر (لم يُرفع بعد)
changes4 = {
    "server_time": "2026-09-01T12:00:00+00:00", "full_resync": False, "has_more": False,
    "changed": [
        {"seq_no": 8, "txn_date": "2026-09-01T09:00:00+00:00", "account_name": "x",
         "op_type": "وارد الماس", "weight": 50, "status": "ACTIVE"},
        {"seq_no": 9, "txn_date": "2026-09-01T21:30:00+00:00", "account_name": "المدير",
         "op_type": "وارد ذهب (عيار 18)", "weight": 3, "status": "ACTIVE", "period": "2026-09"},
    ],
    "deleted": [],
}
engine4 = CloudSync(db_path=db4, api=FakeApi(changes=changes4), tenant_id="t-1", pull_enabled=True)
assert engine4._pull_changes() is True
con = sqlite3.connect(db4)
got = dict(con.execute("SELECT invoice_id, weight FROM invoices").fetchall())
dt9 = con.execute("SELECT date_time FROM invoices WHERE invoice_id=9").fetchone()[0]
con.close()
assert got[8] == 1, "تعديل محلي غير مرفوع طُمس بنسخة السحابة"
assert got[9] == 3
assert dt9 == ("2026-09-02 00:30:00" if RIYADH else local("2026-09-01T21:30:00+00:00")), \
    f"التاريخ لم يُحوَّل لتوقيت الجهاز: {dt9}"
print("✔ السحب المفعّل صراحةً يعمل ويحترم التعديلات المحلية غير المرفوعة")

# ═══ ٥) تحويل التواريخ ═══
assert _sqlite_dt("2026-09-01T20:00:00+00:00") == ("2026-09-01 23:00:00" if RIYADH else local("2026-09-01T20:00:00+00:00"))
assert _sqlite_dt("2026-09-01T22:30:00.5+00:00") == ("2026-09-02 01:30:00" if RIYADH else local("2026-09-01T22:30:00+00:00"))
assert _sqlite_dt("2026-09-01 10:00:00") == "2026-09-01 10:00:00"
assert _sqlite_dt(None) == ""
assert cloud_sync._map_status("memo") == "MEMO"
assert cloud_sync._map_status("غريب") == "ACTIVE"
print("✔ تواريخ السحابة تُحوَّل لتوقيت الجهاز بدل قصّ الإزاحة")

for p in (db, db2, db3, db4):
    os.remove(p)
print("\n✅ محرك المزامنة: كل الاختبارات السلوكية نجحت")
