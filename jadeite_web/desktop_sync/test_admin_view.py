# -*- coding: utf-8 -*-
"""
المسار الكامل: العميل يثبّت النسخة ← بياناته تصعد للسحابة ← أنت تدخل حسابه
من جهازك فترى كل شيء. مع تحقق أن كل عميل يرى بياناته وحدها.
"""
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloud_sync import CloudSync, install_sync_schema
from sync_down import sync_down


class Cloud:
    """سحابة تحاكي العزل بـ tenant_id ورمز المزامنة"""
    def __init__(self):
        self.rows = {}       # (tenant, seq) -> row
        self.accounts = {}   # tenant -> [names]
        self.tokens = {}     # tenant -> token

    def api_for(self, tenant, token):
        cloud = self
        class API:
            def rpc(self, name, p=None):
                p = dict(p or {})
                t = p.get("p_tenant", tenant)
                # التحقق الأمني: رمز خاطئ يُرفض تماماً
                if cloud.tokens.get(t) != token:
                    raise PermissionError("رمز المزامنة غير صالح")
                if name == "sync_push_transactions":
                    for r in p["p_rows"]: cloud.rows[(t, r["seq_no"])] = r
                    return len(p["p_rows"])
                if name == "sync_push_accounts":
                    cloud.accounts.setdefault(t, []).extend(p["p_rows"]); return 0
                if name == "sync_delete_transactions":
                    for s in p["p_seq_nos"]: cloud.rows.pop((t, s), None)
                    return 0
                if name == "sync_cloud_summary":
                    mine = [k[1] for k in cloud.rows if k[0] == t]
                    return [{"total_rows": len(mine), "max_seq": max(mine or [0]),
                             "accounts_count": len(cloud.accounts.get(t, [])), "last_sync": None}]
                if name == "sync_pull_accounts":
                    return list(cloud.accounts.get(t, []))
                if name == "sync_pull_transactions":
                    after, lim = p.get("p_after_seq") or 0, p.get("p_limit") or 1000
                    keys = sorted(k[1] for k in cloud.rows if k[0] == t and k[1] > after)[:lim]
                    return [cloud.rows[(t, k)] for k in keys]
                if name == "sync_pull_changes":
                    return {"server_time": "2026-08-13T12:00:00Z", "full_resync": False,
                            "has_more": False, "changed": [], "deleted": []}
                return None
        return API()


cloud = Cloud()
tmp = tempfile.mkdtemp()


def make_client(tenant, token, count, base_weight):
    """جهاز عميل عليه بيانات قديمة، غير مربوط بالسحابة بعد"""
    cloud.tokens[tenant] = token
    db = os.path.join(tmp, f"client_data_{tenant}.db")
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE names (name TEXT, category TEXT, UNIQUE(name, category));
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
            weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
            trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '', manual_no TEXT DEFAULT '');
    """)
    con.execute("INSERT INTO names VALUES(?,?)", (f"عامل {tenant}", "المصنعين"))
    for i in range(1, count + 1):
        con.execute("""INSERT INTO invoices(invoice_id,date_time,name,op_type,weight,set_number)
                       VALUES(?,?,?,?,?,?)""",
                    (i, f"2026-08-{(i % 27) + 1:02d} 09:00:00", f"عامل {tenant}",
                     "صرف ذهب", base_weight + i, f"T{tenant}-{i}"))
    con.commit(); con.close()
    return db


# ============ الخطوة ١: عميلان يثبّتان النسخة ويسجّلان الدخول ============
db_a = make_client("A", "TOKEN-A", 500, 100)
db_b = make_client("B", "TOKEN-B", 300, 900)

for tenant, token, db in [("A", "TOKEN-A", db_a), ("B", "TOKEN-B", db_b)]:
    api = cloud.api_for(tenant, token)
    install_sync_schema(db)
    up = CloudSync(db_path=db, api=api, tenant_id=tenant, app_version="1.37.0")
    up.flush(max_batches=500)
    # العميل لا يسحب بعد الآن (اتجاه أحادي)
    # sync_down(db, api, tenant)

a_cloud = len([k for k in cloud.rows if k[0] == "A"])
b_cloud = len([k for k in cloud.rows if k[0] == "B"])
assert (a_cloud, b_cloud) == (500, 300), (a_cloud, b_cloud)
print(f"✔ الخطوة ١: بيانات العميلين صعدت للسحابة (أ={a_cloud} | ب={b_cloud})")

# ============ الخطوة ٢: أنت تدخل حساب العميل (أ) من جهازك ============
admin_db = os.path.join(tmp, "admin_view_A.db")
install_sync_schema(admin_db)
sync_down(admin_db, cloud.api_for("A", "TOKEN-A"), "A")

con = sqlite3.connect(admin_db)
seen = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
total = con.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0]
names = con.execute("SELECT COUNT(*) FROM names").fetchone()[0]
con.close()

orig = sqlite3.connect(db_a)
orig_total = orig.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0]
orig.close()

assert seen == 500 and total == orig_total
print(f"✔ الخطوة ٢: على جهازك ترى كل بيانات العميل (أ): {seen} حركة | {total:,} جم — مطابقة تماماً")
assert names >= 1
print(f"✔ حتى شجرة حساباته وصلتك ({names} اسم)")

# ============ الخطوة ٣: العزل — لا ترى بيانات عميل داخل حساب آخر ============
assert not any(r["set_number"].startswith("TB-")
               for r in [cloud.rows[k] for k in cloud.rows if k[0] == "A"])
print("✔ الخطوة ٣: بيانات العميل (ب) لا تظهر إطلاقاً داخل حساب العميل (أ)")

try:
    cloud.api_for("A", "TOKEN-B").rpc("sync_cloud_summary", {"p_tenant": "A"})
    raise AssertionError("قُبل رمز خاطئ!")
except PermissionError:
    print("✔ رمز عميل لا يفتح حساب عميل آخر — العزل مفروض في الخادم")

# ============ الخطوة ٤: حركة جديدة عند العميل تصلك ============
con = sqlite3.connect(db_a)
con.execute("""INSERT INTO invoices(invoice_id,date_time,name,op_type,weight,set_number)
               VALUES(9001,'2026-08-13 15:00:00','عامل A','قبض ذهب',77.5,'TA-NEW')""")
con.commit(); con.close()

CloudSync(db_path=db_a, api=cloud.api_for("A", "TOKEN-A"), tenant_id="A").flush()
sync_down(admin_db, cloud.api_for("A", "TOKEN-A"), "A")

con = sqlite3.connect(admin_db)
row = con.execute("SELECT weight, set_number FROM invoices WHERE invoice_id=9001").fetchone()
after = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
con.close()
assert row == (77.5, "TA-NEW") and after == 501
print(f"✔ الخطوة ٤: حركة سجّلها العميل الآن ظهرت عندك خلال ثوانٍ ({row[1]} — {row[0]} جم)")

print("\n✅ المسار كامل يعمل: العميل ← السحابة ← شاشتك")
