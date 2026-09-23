# -*- coding: utf-8 -*-
"""محاكاة كاملة: عميل قائم عنده بيانات محلية يفتح النسخة الجديدة لأول مرة"""
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloud_sync import CloudSync, install_sync_schema
from sync_down import sync_down

tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "client_data_TENANT-A.db")

# ---------- قاعدة العميل كما هي اليوم (قبل الربط بالسحابة) ----------
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE names (name TEXT, category TEXT, UNIQUE(name, category));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
    weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
    trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '', manual_no TEXT DEFAULT '');
CREATE TABLE monthly_archive (archive_date TEXT);
""")
con.execute("INSERT INTO names VALUES('أحمد','المصنعين')")
con.execute("INSERT INTO names VALUES('مورد الذهب','الموردين')")
N = 1200
for i in range(1, N + 1):
    con.execute("INSERT INTO invoices(invoice_id,date_time,name,op_type,weight,set_number,row_number)"
                " VALUES(?,?,?,?,?,?,?)",
                (i, f"2026-0{(i%6)+1}-15 09:00:00", "أحمد", "صرف ذهب", i * 1.5, f"T-{i}", str(i)))
con.commit()
before_count = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
before_sum = con.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0]
con.close()
print(f"قاعدة العميل قبل التحديث: {before_count} حركة | إجمالي {before_sum} جم")


class FakeCloud:
    """سحابة فارغة تماماً (العميل لم يُربط من قبل)"""
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
        if name == "sync_pull_accounts":
            return list(self.accounts)
        if name == "sync_pull_transactions":
            after, lim = p.get("p_after_seq") or 0, p.get("p_limit") or 1000
            sel = sorted(k for k in self.rows if k > after)[:lim]
            return [self.rows[k] for k in sel]
        if name == "sync_pull_changes":
            return {"server_time": "2026-08-12T10:00:00Z", "full_resync": False,
                    "has_more": False, "changed": [], "deleted": []}
        return None


cloud = FakeCloud()

# ---------- تسلسل أول تشغيل للنسخة الجديدة ----------
install_sync_schema(db)
up = CloudSync(db_path=db, api=cloud, tenant_id="TENANT-A", app_version="1.35.1")
pending = up.pending_count()
assert pending >= before_count, f"لم تُدرج كل الحركات القديمة للرفع ({pending})"
print(f"في انتظار الرفع بعد التهيئة: {pending}")

up.flush(max_batches=500)
assert len(cloud.rows) == before_count, f"فُقدت حركات! رُفع {len(cloud.rows)} من {before_count}"
print(f"✔ رُفعت كل الحركات القديمة للسحابة: {len(cloud.rows)}")
assert up.pending_count() == 0
print("✔ صندوق الصادر فارغ — لا حركة عالقة")
assert len(cloud.accounts) == 2
print(f"✔ رُفعت شجرة الحسابات: {len(cloud.accounts)} حساب")

sync_down(db, cloud, "TENANT-A")
con = sqlite3.connect(db)
after_count = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
after_sum = con.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0]
assert (after_count, after_sum) == (before_count, before_sum), (after_count, after_sum)
print(f"✔ بعد السحب: {after_count} حركة | إجمالي {after_sum} جم — مطابق تماماً، لا فقد ولا تكرار")

counter = con.execute("SELECT value FROM settings WHERE key='invoice_counter'").fetchone()[0]
assert int(counter) == before_count
print(f"✔ عدّاد الفواتير مضبوط على {counter} فلا تصطدم حركة جديدة بقديمة")
con.close()

# ---------- جهاز جديد فارغ لنفس العميل ----------
db2 = os.path.join(tmp, "new_device.db")
install_sync_schema(db2)
sync_down(db2, cloud, "TENANT-A")
con2 = sqlite3.connect(db2)
n2 = con2.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
s2 = con2.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0]
assert (n2, s2) == (before_count, before_sum)
print(f"✔ جهاز جديد فارغ: استعاد {n2} حركة كاملة من السحابة")
con2.close()

# ---------- إعادة تشغيل البرنامج مرة أخرى: لا تكرار ولا رفع بلا داعٍ ----------
install_sync_schema(db)
up2 = CloudSync(db_path=db, api=cloud, tenant_id="TENANT-A")
assert up2.pending_count() == 0, "أعاد إدراج كل شيء للرفع من جديد!"
sync_down(db, cloud, "TENANT-A")
con = sqlite3.connect(db)
assert con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == before_count
con.close()
print("✔ إعادة التشغيل لا تُكرّر البيانات ولا تعيد رفعها بلا داعٍ")

print("\nكل شيء سليم ✅")
