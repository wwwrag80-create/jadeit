# -*- coding: utf-8 -*-
"""
اختبار شامل: برنامج المدير يعرض بيانات العميل كما هي على جهازه حرفياً.

يشغّل المسار الحقيقي كاملاً: قاعدة عميل ← محرك الرفع (cloud_sync) ← سحابة
وهمية تحاكي دوال SQL ← السحب في برنامج المدير (sync_down) ← مقارنة كل شيء:

  • الأسماء بأقسامها **وترتيبها** (كانت تصل للمدير مرتّبة أبجدياً)
  • الإعدادات: نسب الاسترجاع، أسماء الأعمدة، ترتيب الشاشات (لم تكن تُرفع)
  • كل عمود في كل حركة — والتاريخ حرفياً ولو اختلف توقيت جهاز المدير
  • بعد تعديل/حذف/إضافة عند العميل تبقى نسخة المدير مطابقة
  • الاتجاه واحد: لا شيء يُكتب في قاعدة العميل
"""
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def set_tz(tz):
    os.environ["TZ"] = tz
    if hasattr(time, "tzset"):
        time.tzset()


set_tz("Asia/Riyadh")
from cloud_sync import CloudSync, install_sync_schema  # noqa: E402
from sync_down import sync_down  # noqa: E402


class FakeCloud:
    """يحاكي دوال المزامنة في SQL (13 + 16) بما يكفي للمقارنة."""

    def __init__(self, settings_supported=True):
        self.accounts = {}          # (name, category) -> {active, order}
        self.txns = {}              # seq_no -> row
        self.settings = {}
        self.settings_supported = settings_supported

    def rpc(self, name, p=None):
        p = p or {}
        if name == "sync_push_accounts":
            for r in p["p_rows"]:
                key = (r["name"], r["category"])
                old = self.accounts.get(key, {})
                order = r.get("sort_order")
                self.accounts[key] = {"active": True,
                                      "order": order if isinstance(order, int) else old.get("order")}
            return len(p["p_rows"])
        if name == "sync_delete_accounts":
            for r in p["p_rows"]:
                if (r["name"], r["category"]) in self.accounts:
                    self.accounts[(r["name"], r["category"])]["active"] = False
            return 0
        if name == "sync_pull_accounts":
            active = [(k, v) for k, v in self.accounts.items() if v["active"]]
            active.sort(key=lambda kv: (kv[1]["order"] is None, kv[1]["order"] or 0, kv[0][1], kv[0][0]))
            return [{"name": k[0], "category": k[1]} for k, _ in active]
        if name == "sync_push_transactions":
            for r in p["p_rows"]:
                self.txns[r["seq_no"]] = dict(r)
            return len(p["p_rows"])
        if name == "sync_delete_transactions":
            for s in p["p_seq_nos"]:
                self.txns.pop(s, None)
            return 0
        if name == "sync_push_settings":
            if not self.settings_supported:
                raise RuntimeError("Could not find the function public.sync_push_settings")
            self.settings = {r["key"]: r["value"] for r in p["p_rows"]}
            return len(self.settings)
        if name == "sync_pull_settings":
            if not self.settings_supported:
                raise RuntimeError("Could not find the function public.sync_pull_settings")
            return [{"key": k, "value": v} for k, v in sorted(self.settings.items())]
        if name == "sync_cloud_summary":
            return [{"total_rows": len(self.txns), "max_seq": max(self.txns or [0]),
                     "accounts_count": len(self.accounts), "last_sync": None}]
        if name == "sync_pull_transactions":
            after, lim = p.get("p_after_seq") or 0, p.get("p_limit") or 1000
            out = []
            for seq in sorted(k for k in self.txns if k > after)[:lim]:
                r = dict(self.txns[seq])
                # السحابة تخزّن لحظة زمنية وترجعها بتوقيت UTC (مثل timestamptz)
                r["txn_date"] = datetime.fromisoformat(r["txn_date"]).astimezone(timezone.utc).isoformat()
                out.append(r)
            return out
        return None


def client_db():
    """قاعدة عميل بنفس بنية البرنامج (init_database)"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
            weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
            trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', period TEXT DEFAULT '',
            row_number TEXT DEFAULT '', manual_no TEXT DEFAULT '');
    """)
    con.commit()
    con.close()
    install_sync_schema(path)
    return path


def run(db, sql, params=()):
    con = sqlite3.connect(db)
    con.execute(sql, params)
    con.commit()
    con.close()


def screen(db):
    """ما يقرؤه البرنامج عند الفتح: الأقسام بأسمائها بترتيبها، الإعدادات، الحركات"""
    con = sqlite3.connect(db)
    try:
        cats = {}
        for name, cat in con.execute("SELECT name, category FROM names"):   # كما في load_data_from_db
            cats.setdefault(cat, []).append(name)
        settings = {k: v for k, v in con.execute("SELECT key, value FROM settings")
                    if k != "invoice_counter"}
        invoices = con.execute("""SELECT invoice_id, date_time, name, op_type, weight, before_w, after_w,
                                         note, settled_status, trees_count, set_number, row_number,
                                         manual_no, period FROM invoices ORDER BY invoice_id""").fetchall()
        return cats, settings, invoices
    finally:
        con.close()


def admin_mirror(cloud):
    """برنامج المدير: قاعدة نظيفة ثم سحب (مثل SyncDownWindow في نسخة المدير)"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    install_sync_schema(path)
    sync_down(path, cloud, "T")
    return path


# ═══ بيانات العميل ═══
db = client_db()
for name, cat in [("الكاستينج", "الآلة/المكائن"), ("يوسف", "المصنعين"), ("أحمد", "المصنعين"),
                  ("سالم", "المركبين"), ("محمد", "المصنعين"), ("بدر", "المركبين"),
                  ("مورد ب", "الموردين"), ("مورد أ", "الموردين"), ("الصب", "أقسام_خياس_إضافية")]:
    run(db, "INSERT INTO names(name, category) VALUES(?, ?)", (name, cat))
for k, v in [("recovery_pct_تلميع", "40"), ("recovery_pct_مركب", "12.5"),
             ("col_labels_workers", '{"قبض": "استلام"}'), ("sidebar_order", '["sales","boxes"]'),
             ("neg_color_المصنعين", "1"), ("invoice_counter", "999")]:
    run(db, "INSERT INTO settings(key, value) VALUES(?, ?)", (k, v))
rows = [
    (1001, "2026-08-31 23:30:00", "يوسف", "صرف ذهب", 12.5, 0, 0, "", "ACTIVE", 0, "", "1", "", "2026-08"),
    (1002, "2026-09-01 00:15:00", "يوسف", "قبض ذهب", 10.0, 0, 0, "ملاحظة", "ACTIVE", 0, "", "1", "", "2026-08"),
    (1003, "2026-09-02 10:00:00", "عميل", "مبيعات ذهب", 20.0, 0, 0, "", "ACTIVE", 0, "T-5", "", "77", "2026-09"),
    (1004, "2026-09-02 10:00:00", "عميل", "خياس طقوم", 0.4, 0, 0, "", "MEMO", 7, "T-5", "", "77", "2026-09"),
    (1005, "2026-09-03 09:00:00", "مورد أ", "وارد ذهب (عيار 18)", 100.0, 110.0, 750.0, "", "SETTLED_INOUT", 1, "", "", "", "2026-09"),
    (1006, "2026-09-03 09:05", "الصب", "صرف الصب", 3.0, 0, 0, "", "SETTLED", 0, "", "2", "", "2026-09"),
]
con = sqlite3.connect(db)
con.executemany("INSERT INTO invoices(invoice_id, date_time, name, op_type, weight, before_w, after_w, note,"
                " settled_status, trees_count, set_number, row_number, manual_no, period)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
con.commit()
con.close()

client_before = screen(db)
cloud = FakeCloud()
CloudSync(db_path=db, api=cloud, tenant_id="T").flush()
assert screen(db) == client_before, "الرفع غيّر شيئاً في قاعدة العميل!"
print("✔ الرفع لا يغيّر شيئاً في قاعدة العميل (اتجاه واحد)")

# المدير على جهاز بتوقيت مختلف تماماً
set_tz("America/New_York")
admin = admin_mirror(cloud)
c_cats, c_set, c_inv = client_before
a_cats, a_set, a_inv = screen(admin)

assert a_cats == c_cats, (a_cats, c_cats)
print("✔ الأسماء في كل قسم بترتيب العميل نفسه (المصنعين: يوسف، أحمد، محمد — لا أبجدياً)")
assert a_set == c_set, (a_set, c_set)
print("✔ الإعدادات مطابقة: نسب الاسترجاع وأسماء الأعمدة والترتيب وتلوين السالب")
assert a_inv == c_inv, [(a, c) for a, c in zip(a_inv, c_inv) if a != c]
print("✔ كل الحركات بكل أعمدتها مطابقة — الحالة (MEMO/SETTLED)، الفترة، الأوزان")
print("✔ والتاريخ حرفياً رغم أن جهاز المدير بتوقيت آخر (لا تنزاح الساعة ولا اليوم)")
set_tz("Asia/Riyadh")

# ═══ العميل يعدّل ويحذف ويضيف ═══
run(db, "DELETE FROM names WHERE name = 'أحمد'")
run(db, "INSERT INTO names(name, category) VALUES('خالد', 'المصنعين')")
run(db, "UPDATE settings SET value = '55' WHERE key = 'recovery_pct_تلميع'")
run(db, "DELETE FROM settings WHERE key = 'neg_color_المصنعين'")
run(db, "UPDATE invoices SET weight = 11.25, note = 'معدّلة' WHERE invoice_id = 1002")
run(db, "DELETE FROM invoices WHERE invoice_id = 1003")
run(db, "INSERT INTO invoices(invoice_id, date_time, name, op_type, weight, before_w, after_w, note,"
        " settled_status, trees_count, set_number, row_number, manual_no, period)"
        " VALUES (1007, '2026-09-04 08:00:00', 'خالد', 'صرف ذهب', 5, 0, 0, '', 'ACTIVE', 0, '', '3', '', '2026-09')")
CloudSync(db_path=db, api=cloud, tenant_id="T").flush()
assert screen(admin_mirror(cloud)) == screen(db)
print("✔ بعد تعديل وحذف وإضافة عند العميل: نسخة المدير مطابقة تماماً من جديد")

# ═══ سحابة لم يُشغَّل عليها 16_admin_mirror_parity.sql بعد ═══
old_cloud = FakeCloud(settings_supported=False)
db2 = client_db()
run(db2, "INSERT INTO settings(key, value) VALUES('recovery_pct_تلميع', '40')")
run(db2, "INSERT INTO invoices(invoice_id, date_time, name, op_type, weight, period)"
         " VALUES (1, '2026-09-01 10:00:00', 'عميل', 'مبيعات ذهب', 3, '2026-09')")
CloudSync(db_path=db2, api=old_cloud, tenant_id="T").flush()
assert 1 in old_cloud.txns
print("✔ سحابة قديمة بلا دالة الإعدادات: رفع الحركات يستمر بلا توقف")
admin_mirror(old_cloud)
print("✔ وسحب المدير منها يعمل (الإعدادات تُتخطّى فقط)")

print("\n✅ برنامج المدير يعرض بيانات العميل كما هي على جهازه — أسماءً وترتيباً وإعدادات وحركات")
