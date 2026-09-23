# -*- coding: utf-8 -*-
"""
اختبار: شاشة المدير يجب أن تطابق شاشة العميل تماماً.
يحاكي السحابة ويقارن الفترات والحسابات والحركات رقماً برقم.
"""
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloud_sync import CloudSync, install_sync_schema
from sync_down import sync_down


class Cloud:
    """سحابة تحاكي دوال المزامنة بعد إصلاح 13"""
    def __init__(self):
        self.rows = {}       # seq -> row (مع period)
        self.accounts = {}   # (name, category) -> active

    def rpc(self, name, p=None):
        p = p or {}
        if name == "sync_push_transactions":
            for r in p["p_rows"]:
                self.rows[r["seq_no"]] = dict(r)
            return len(p["p_rows"])
        if name == "sync_delete_transactions":
            for s in p["p_seq_nos"]:
                self.rows.pop(s, None)
            return 0
        if name == "sync_push_accounts":
            for r in p["p_rows"]:
                self.accounts[(r["name"], r["category"])] = True
            return 0
        if name == "sync_delete_accounts":
            for r in p["p_rows"]:
                self.accounts[(r["name"], r["category"])] = False
            return 0
        if name == "sync_cloud_summary":
            return [{"total_rows": len(self.rows), "max_seq": max(self.rows or [0]),
                     "accounts_count": len(self.accounts), "last_sync": None}]
        if name == "sync_pull_accounts":
            return [{"name": n, "category": c} for (n, c), a in self.accounts.items() if a]
        if name == "sync_pull_transactions":
            after, lim = p.get("p_after_seq") or 0, p.get("p_limit") or 1000
            keys = sorted(k for k in self.rows if k > after)[:lim]
            return [self.rows[k] for k in keys]
        if name == "sync_pull_changes":
            return {"server_time": "2026-09-02T10:00:00Z", "full_resync": False,
                    "has_more": False, "changed": [], "deleted": []}
        return None


TENANT = "T-1"
tmp = tempfile.mkdtemp()
client_db = os.path.join(tmp, "client.db")

# ═══ جهاز العميل: حركات بفترات صريحة تختلف عن شهر التاريخ ═══
install_sync_schema(client_db)
con = sqlite3.connect(client_db)
cols = [c[1] for c in con.execute("PRAGMA table_info(invoices)")]
if "period" not in cols:
    con.execute("ALTER TABLE invoices ADD COLUMN period TEXT DEFAULT ''")

# حركة سُجّلت يوم ٧/٣٠ لكنها مثبّتة في فترة ٨ — هذه هي الحالة التي أظهرت
# فترة ٧ زائدة عند المدير
DATA = [
    (1, "2026-07-30 09:00:00", "أحمد", "صرف ذهب", 100.0, "2026-08"),
    (2, "2026-08-05 10:00:00", "أحمد", "قبض ذهب",  96.0, "2026-08"),
    (3, "2026-09-01 11:00:00", "سالم", "صرف ذهب",  50.0, "2026-09"),
]
for i, dt, nm, op, w, per in DATA:
    con.execute("""INSERT INTO invoices(invoice_id,date_time,name,op_type,weight,period)
                   VALUES(?,?,?,?,?,?)""", (i, dt, nm, op, w, per))

# حسابات بأقسام ديناميكية (صندوق خياس مضاف + عمال)
for n, c in [("أحمد", "المصنعين"), ("سالم", "المركبين"),
             ("ورشة التركيب", "أقسام_خياس_إضافية"), ("عامل التركيب", "ورشة التركيب")]:
    con.execute("INSERT OR IGNORE INTO names VALUES(?,?)", (n, c))
con.commit()

client_periods = sorted({r[0] for r in con.execute("SELECT period FROM invoices")})
client_accounts = sorted(con.execute("SELECT name, category FROM names").fetchall())
client_count = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
con.close()
print(f"العميل: فترات {client_periods} | {client_count} حركة | {len(client_accounts)} حساب")

# ═══ رفع كل شيء للسحابة ═══
cloud = Cloud()
up = CloudSync(db_path=client_db, api=cloud, tenant_id=TENANT)
up.flush(max_batches=50)
assert len(cloud.rows) == client_count, (len(cloud.rows), client_count)
print(f"✔ رُفعت {len(cloud.rows)} حركة و{len(cloud.accounts)} حساب")

# الفترة رُفعت مع كل حركة
for seq, row in cloud.rows.items():
    assert row.get("period"), f"الحركة {seq} رُفعت بلا فترة!"
print("✔ كل حركة رُفعت ومعها فترتها المحاسبية")

# الأقسام الديناميكية رُفعت بأسمائها الحقيقية
cats = {c for (_n, c) in cloud.accounts}
assert "أقسام_خياس_إضافية" in cats and "ورشة التركيب" in cats, cats
print(f"✔ الأقسام الديناميكية رُفعت كما هي: {sorted(cats)}")

# ═══ جهاز المدير: قاعدة نظيفة ثم سحب ═══
admin_db = os.path.join(tmp, "admin.db")
install_sync_schema(admin_db)
sync_down(admin_db, cloud, TENANT)

con = sqlite3.connect(admin_db)
admin_periods = sorted({r[0] for r in con.execute("SELECT period FROM invoices")})
admin_accounts = sorted(con.execute("SELECT name, category FROM names").fetchall())
admin_count = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]

assert admin_periods == client_periods, (admin_periods, client_periods)
print(f"\n✔ الفترات مطابقة تماماً: {admin_periods}")
print("  (قبل الإصلاح كان المدير يرى فترة ٢٠٢٦-٠٧ زائدة لأن الفترة كانت تُشتق من التاريخ)")

assert admin_count == client_count
print(f"✔ عدد الحركات مطابق: {admin_count}")

assert admin_accounts == client_accounts, (admin_accounts, client_accounts)
print(f"✔ الحسابات وأقسامها مطابقة تماماً ({len(admin_accounts)} حساب)")
print("  (قبل الإصلاح كانت الأقسام الديناميكية تُسحق إلى «حسابات عامة» فتختفي)")

# كل حركة بتاريخها وفترتها الصحيحين
for i, dt, nm, op, w, per in DATA:
    got = con.execute("SELECT date_time, name, op_type, weight, period FROM invoices WHERE invoice_id=?",
                      (i,)).fetchone()
    assert got[0][:10] == dt[:10] and got[1] == nm and got[3] == w and got[4] == per, (i, got)
print("✔ كل حركة وصلت بتاريخها ووزنها وفترتها الصحيحة")
con.close()

# ═══ حذف اسم عند العميل يصل للمدير ═══
con = sqlite3.connect(client_db)
con.execute("DELETE FROM names WHERE name='سالم' AND category='المركبين'")
con.commit(); con.close()

CloudSync(db_path=client_db, api=cloud, tenant_id=TENANT).flush(max_batches=10)
assert cloud.accounts.get(("سالم", "المركبين")) is False
print("✔ حذف اسم عند العميل يُعطّله في السحابة (كان يبقى ظاهراً عند المدير للأبد)")

admin_db2 = os.path.join(tmp, "admin2.db")
install_sync_schema(admin_db2)
sync_down(admin_db2, cloud, TENANT)
con = sqlite3.connect(admin_db2)
left = con.execute("SELECT COUNT(*) FROM names WHERE name='سالم'").fetchone()[0]
assert left == 0
print("✔ ولا يظهر عند المدير بعد السحب")
con.close()

# ═══ حذف حركة عند العميل يصل للمدير ═══
con = sqlite3.connect(client_db)
con.execute("DELETE FROM invoices WHERE invoice_id=3")
con.commit(); con.close()
CloudSync(db_path=client_db, api=cloud, tenant_id=TENANT).flush(max_batches=10)
assert 3 not in cloud.rows
print("✔ حذف حركة عند العميل يحذفها من السحابة أيضاً")

print("\n✅ شاشة المدير مطابقة لشاشة العميل تماماً")
