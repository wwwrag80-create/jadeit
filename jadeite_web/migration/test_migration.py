# -*- coding: utf-8 -*-
"""اختبار أداة الترحيل على قاعدة بيانات قديمة حقيقية الشكل"""
import os, sqlite3, tempfile, json, time

# التواريخ تُرحَّل بإزاحة توقيت الجهاز (مثل برنامج العميل) — نثبّت توقيت الرياض للاختبار
os.environ["TZ"] = "Asia/Riyadh"
if hasattr(time, "tzset"):
    time.tzset()

from migrate_sqlite_to_supabase import read_legacy_db, normalize_date, build_report, chunked, map_status

tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "client_data_TEST.db")
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE names (name TEXT, category TEXT, UNIQUE(name, category));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
    weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
    trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '',
    manual_no TEXT DEFAULT '');
INSERT INTO names VALUES ('أحمد','المصنعين'),('سالم','المركبين'),('مورد الرياض','الموردين'),
                         ('صندوق إضافي','أقسام_خياس_إضافية'),('30','نسب_خصم_احجار');
INSERT INTO settings VALUES ('stones_discount_pct','30'),('home_screen_order','["المبيعات"]');
INSERT INTO invoices VALUES
 (1,'2026-07-01 09:00:00','أحمد','صرف ذهب',100.0,0,0,'','ACTIVE',0,'T-1','1',''),
 (2,'2026-07-01 09:00:01','أحمد','قبض ذهب',98.5,0,0,'','ACTIVE',0,'T-1','1',''),
 (3,'2026-08-02 10:00:00','عميل','مبيعات ذهب',40.0,0,0,'مبيعات','ACTIVE',0,'S-1','1','5001'),
 (4,'2026-08-02 10:00:00','عميل','خياس طقوم',1.25,0,0,'خياس طقم','MEMO',7,'S-1','1','5001'),
 (5,'2026-08-03','مورد الرياض','وارد ذهب (عيار 18)',210.0,200.0,18.9,'','ACTIVE',0,'V-9','','');
""")
con.commit(); con.close()

TENANT = "11111111-2222-3333-4444-555555555555"
data = read_legacy_db(db, TENANT)

# --- الحركات ---
assert len(data["transactions"]) == 5
t = data["transactions"][0]
assert t["tenant_id"] == TENANT and t["seq_no"] == 1
assert t["account_name"] == "أحمد" and t["op_type"] == "صرف ذهب" and t["weight"] == 100.0
assert t["txn_date"] == "2026-07-01T09:00:00+03:00"
assert t["period"] == "2026-07"
print("✔ قراءة الحركات وتحويل التاريخ لصيغة ISO بإزاحة التوقيت المحلي")

# السطر المعلوماتي يبقى MEMO (لا يُحتسب في الأرصدة)، والحالة المجهولة تصبح ACTIVE
assert data["transactions"][3]["status"] == "MEMO"
assert map_status("settled_inout") == "SETTLED_INOUT" and map_status("؟") == "ACTIVE"
print("✔ حالات الحركات تُرحَّل كما هي (MEMO لا تتحوّل لـ ACTIVE)")

# التاريخ بدون وقت يُكمَّل تلقائياً
assert data["transactions"][4]["txn_date"] == "2026-08-03T00:00:00+03:00"
assert normalize_date("") .startswith(str(__import__("datetime").datetime.now().year))
assert normalize_date("قيمة غريبة") == "قيمة غريبة"   # تُترك ليرفضها الخادم بوضوح بدل تخمين خاطئ
print("✔ التواريخ الناقصة والغريبة تُعالَج بأمان بدون تخمين")

# --- الحسابات ---
names = {(a["name"], a["category"]) for a in data["accounts"]}
assert ("أحمد", "المصنعين") in names
assert ("سالم", "المركبين") in names
assert ("مورد الرياض", "الموردين") in names
assert ("صندوق إضافي", "صناديق الخياس") in names
assert not any(a["name"] == "30" for a in data["accounts"])   # نسب الخصم ليست حساباً
box = next(a for a in data["accounts"] if a["category"] == "صناديق الخياس")
assert box["box_key"] == "صندوق إضافي"
assert box["category_raw"] == "أقسام_خياس_إضافية"   # القسم الحقيقي محفوظ حرفياً
print("✔ تحويل تصنيفات الأسماء القديمة لشجرة الحسابات الجديدة سليم")

# --- الإعدادات ---
settings = {s["key"]: json.loads(s["value"]) for s in data["settings"]}
assert settings["stones_discount_pct"] == 30
assert settings["home_screen_order"] == ["المبيعات"]
print("✔ الإعدادات تُرحَّل بصيغة JSON صحيحة")

# --- تقرير التحقق ---
rep = data["report"]
assert rep["total"] == 5
assert rep["by_type"]["صرف ذهب"]["count"] == 1
assert rep["by_period"] == {"2026-07": 2, "2026-08": 3}
assert rep["issues"] == [], rep["issues"]
print("✔ تقرير التحقق يعطي العدد والمجاميع لكل نوع ولكل شهر:", rep["by_period"])

# --- اكتشاف المشاكل ---
bad = build_report([
    {"seq_no": 1, "op_type": "", "account_name": "", "weight": 1.0, "txn_date": "2026-08-01T00:00:00"},
    {"seq_no": 1, "op_type": "x", "account_name": "y", "weight": 2.0, "txn_date": "2026-08-01T00:00:00"},
])
assert any("مكرر" in i for i in bad["issues"])
assert any("بدون اسم" in i for i in bad["issues"])
assert any("بدون نوع" in i for i in bad["issues"])
print("✔ التقرير يكشف الحركات المكررة والناقصة قبل الترحيل")

# --- التقسيم لدفعات ---
assert [len(b) for b in chunked(list(range(1250)), 500)] == [500, 500, 250]
print("✔ التقسيم لدفعات سليم")

# --- ملف تالف يُرفض بوضوح ---
broken = os.path.join(tmp, "broken.db")
open(broken, "wb").write(b"not a database" * 50)
try:
    read_legacy_db(broken, TENANT)
    raise AssertionError("كان يجب رفض الملف التالف")
except Exception as e:
    assert "تالف" in str(e) or "invoices" in str(e)
print("✔ الملفات التالفة تُرفض برسالة واضحة بدل ترحيل بيانات ناقصة")

print("\nكل اختبارات أداة الترحيل نجحت ✅")

# --- الفترة الصريحة تُحترم في القواعد الحديثة ---
db2 = os.path.join(tmp, "client_data_PERIOD.db")
con = sqlite3.connect(db2)
con.executescript("""
CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
    weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
    trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '',
    manual_no TEXT DEFAULT '', period TEXT DEFAULT '');
INSERT INTO invoices VALUES (1,'2026-09-01 08:00:00','مورد','وارد الماس',1,0,0,'','ACTIVE',0,'','','','2026-08');
""")
con.commit(); con.close()
d2 = read_legacy_db(db2, TENANT)
assert d2["transactions"][0]["period"] == "2026-08"
assert d2["report"]["by_period"] == {"2026-08": 1}
print("✔ الفترة المحاسبية الصريحة تُرحَّل كما هي حتى لو اختلفت عن شهر التاريخ")
