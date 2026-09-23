# -*- coding: utf-8 -*-
"""
محاكاة الحالة الفعلية: عميل يعمل منذ شهور على النسخة القديمة بلا ربط سحابي،
ويستلم التحديث الجديد. هل تعود بياناته كلها؟
"""
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloud_sync import CloudSync, install_sync_schema
from sync_down import sync_down

CLIENT_ID = "TENANT-XYZ"
tmp = tempfile.mkdtemp()
DATA_DIR = os.path.join(tmp, "JadeiteERP", "Data")
os.makedirs(DATA_DIR)
db = os.path.join(DATA_DIR, f"client_data_{CLIENT_ID}.db")

# ---------- قاعدة العميل الحالية (٦ شهور عمل، بلا سحابة) ----------
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE names (name TEXT, category TEXT, UNIQUE(name, category));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
    weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
    trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '', manual_no TEXT DEFAULT '');
""")
for n, c in [("أحمد","المصنعين"), ("سالم","المركبين"), ("مورد الذهب","الموردين"), ("عميل الرياض","الموردين")]:
    con.execute("INSERT INTO names VALUES(?,?)", (n, c))

TYPES = ["صرف ذهب","قبض ذهب","المفنش ٨ بالالف","وارد ذهب (عيار 18)","مبيعات ذهب","صرف كاستنج","قبض كاستنج"]
N = 3000
for i in range(1, N + 1):
    con.execute("""INSERT INTO invoices(invoice_id,date_time,name,op_type,weight,before_w,after_w,
                   note,trees_count,set_number,row_number,manual_no) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (i, f"2026-0{(i % 6) + 1}-{(i % 27) + 1:02d} 09:30:00",
                 ["أحمد","سالم","مورد الذهب","عميل الرياض"][i % 4], TYPES[i % len(TYPES)],
                 round(i * 0.37, 2), 0, 18 if i % 4 == 2 else 0, "ملاحظة" if i % 5 == 0 else "",
                 0, f"T-{i}", str(i % 50), str(5000 + i) if i % 7 == 0 else ""))
con.execute("INSERT INTO settings VALUES('invoice_counter', ?)", (str(N),))
con.commit()

before = {
    "count": con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0],
    "sum": con.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0],
    "names": con.execute("SELECT COUNT(*) FROM names").fetchone()[0],
    "by_type": dict(con.execute("SELECT op_type, COUNT(*) FROM invoices GROUP BY op_type").fetchall()),
    "notes": con.execute("SELECT COUNT(*) FROM invoices WHERE note <> ''").fetchone()[0],
    "manual": con.execute("SELECT COUNT(*) FROM invoices WHERE manual_no <> ''").fetchone()[0],
    "max_id": con.execute("SELECT MAX(invoice_id) FROM invoices").fetchone()[0],
}
con.close()
print(f"العميل قبل التحديث: {before['count']:,} حركة | {before['sum']:,} جم | "
      f"{before['names']} اسم | {len(before['by_type'])} نوع عملية")


class Cloud:
    """سحابة فارغة — العميل لم يُربط من قبل إطلاقاً"""
    def __init__(self): self.rows, self.accounts = {}, []
    def rpc(self, name, p=None):
        p = p or {}
        if name == "sync_push_transactions":
            for r in p["p_rows"]: self.rows[r["seq_no"]] = r
            return len(p["p_rows"])
        if name == "sync_push_accounts":
            self.accounts += p["p_rows"]; return len(p["p_rows"])
        if name == "sync_delete_transactions":
            for s in p["p_seq_nos"]: self.rows.pop(s, None)
            return 0
        if name == "sync_cloud_summary":
            return [{"total_rows": len(self.rows), "max_seq": max(self.rows or [0]),
                     "accounts_count": len(self.accounts), "last_sync": None}]
        if name == "sync_pull_accounts": return list(self.accounts)
        if name == "sync_pull_transactions":
            after, lim = p.get("p_after_seq") or 0, p.get("p_limit") or 1000
            return [self.rows[k] for k in sorted(k for k in self.rows if k > after)[:lim]]
        if name == "sync_pull_changes":
            return {"server_time": "2026-08-13T10:00:00Z", "full_resync": False,
                    "has_more": False, "changed": [], "deleted": []}
        return None


cloud = Cloud()

# ================= أول تشغيل للنسخة الجديدة =================
install_sync_schema(db)
up = CloudSync(db_path=db, api=cloud, tenant_id=CLIENT_ID, app_version="1.36.0")
assert up.pending_count() >= before["count"]
up.flush(max_batches=1000)
assert len(cloud.rows) == before["count"], f"رُفع {len(cloud.rows)} من {before['count']}"
print(f"✔ رُفعت كل الحركات للسحابة: {len(cloud.rows):,}")

sync_down(db, cloud, CLIENT_ID)

con = sqlite3.connect(db)
after = {
    "count": con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0],
    "sum": con.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0],
    "names": con.execute("SELECT COUNT(*) FROM names").fetchone()[0],
    "by_type": dict(con.execute("SELECT op_type, COUNT(*) FROM invoices GROUP BY op_type").fetchall()),
    "notes": con.execute("SELECT COUNT(*) FROM invoices WHERE note <> ''").fetchone()[0],
    "manual": con.execute("SELECT COUNT(*) FROM invoices WHERE manual_no <> ''").fetchone()[0],
    "max_id": con.execute("SELECT MAX(invoice_id) FROM invoices").fetchone()[0],
}
for k in before:
    assert before[k] == after[k], f"اختلاف في {k}: {before[k]} ← {after[k]}"
print("✔ بعد التحديث: العدد والمجموع والأسماء وأنواع العمليات والبيانات وأرقام الفواتير — مطابقة ١٠٠٪")

row = con.execute("SELECT date_time,name,op_type,weight,after_w,note,set_number,row_number,manual_no "
                  "FROM invoices WHERE invoice_id=?", (7,)).fetchone()
assert row[0] == "2026-02-08 09:30:00" and row[8] == "5007", row
print(f"✔ تفاصيل الحركة رقم ٧ محفوظة حرفياً: {row[0]} | {row[2]} | فاتورة {row[8]}")

assert int(con.execute("SELECT value FROM settings WHERE key='invoice_counter'").fetchone()[0]) == before["max_id"]
print(f"✔ عدّاد الفواتير = {before['max_id']} (الحركة التالية تأخذ الرقم التالي بلا تصادم)")
con.close()

# ================= لو استخدم جهازاً آخر لاحقاً =================
db2 = os.path.join(DATA_DIR, "another_device.db")
install_sync_schema(db2)
sync_down(db2, cloud, CLIENT_ID)
con2 = sqlite3.connect(db2)
assert con2.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == before["count"]
assert con2.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0] == before["sum"]
print("✔ على أي جهاز آخر يسجّل فيه دخوله: تعود بياناته كاملة من السحابة")

# ================= لو انقطع الإنترنت أثناء التحديث =================
db3 = os.path.join(DATA_DIR, f"client_data_OFFLINE.db")
import shutil
shutil.copy2(db, db3)
class DeadCloud:
    def rpc(self, *a, **k): raise RuntimeError("urlopen error: لا يوجد اتصال")
install_sync_schema(db3)
off = CloudSync(db_path=db3, api=DeadCloud(), tenant_id="X")
try:
    off.flush(max_batches=2)
except Exception:
    pass
con3 = sqlite3.connect(db3)
assert con3.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == before["count"]
print("✔ لو انقطع الإنترنت وقت التحديث: بيانات العميل المحلية سليمة ولا تُمس")
con3.close()

print("\n✅ استعادة بيانات العميل مضمونة بالكامل")
