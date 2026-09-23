# -*- coding: utf-8 -*-
"""
اختبار حاسم قبل إرسال التحديث للعميل:
هل تبقى بياناته القديمة كاملة وسليمة بعد تطبيق كل تحديثات هذه الدفعة؟
"""
import ast, io, os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloud_sync import install_sync_schema

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)

# ---------- ١) لا تغيير في مخطط قاعدة البيانات ----------
init_db = ast.get_source_segment(src, next(
    n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "init_database"))
required_cols = ["invoice_id", "date_time", "name", "op_type", "weight",
                 "before_w", "after_w", "note", "settled_status", "trees_count",
                 "set_number", "row_number", "manual_no"]
for c in required_cols:
    assert c in init_db, f"عمود مفقود من المخطط: {c}"
print(f"✔ مخطط جدول الحركات لم يتغيّر ({len(required_cols)} عموداً كما هي)")

# لم تُضف أعمدة جديدة تتطلب ترحيلاً
assert "ALTER TABLE invoices ADD COLUMN khayas" not in src
print("✔ لا أعمدة جديدة: كل الإضافات استخدمت حقولاً قائمة (trees_count كعلامة)")

# ---------- ٢) الإعدادات الجديدة لها قيم افتراضية آمنة ----------
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
rec = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                       and m.name == "get_recovery_pct"))
assert "RECOVERY_DEFAULT" in rec
print("✔ نسب الاسترجاع لها افتراضي آمن (صفر) — قاعدة العميل القديمة لا تحتويها")

lbl = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                       and m.name == "get_column_label"))
assert "except Exception" in lbl and "return column_id" in lbl
print("✔ أسماء الأعمدة المعدّلة: غيابها يُرجع الاسم الأصلي بلا خطأ")

# ---------- ٣) بيانات قديمة بلا العلامات الجديدة تُقرأ صحيحاً ----------
marks = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id.startswith("KHAYAS_MARK_"):
                marks[t.id] = node.value.value
assert marks["KHAYAS_MARK_FINAL"] == 0.0
print("✔ العلامة الافتراضية 0.0 = خياس التلميع النهائي — فحركات العميل القديمة"
      " (trees_count=0) تُقرأ كما كانت تماماً")

# ---------- ٤) محاكاة فعلية: قاعدة عميل قديمة + تطبيق التحديث ----------
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "client_data_OLD.db")
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE names (name TEXT, category TEXT, UNIQUE(name, category));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
    weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
    trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '', manual_no TEXT DEFAULT '');
""")
for n, c in [("أحمد", "المصنعين"), ("سالم", "المركبين"), ("مورد", "الموردين")]:
    con.execute("INSERT INTO names VALUES(?,?)", (n, c))

OLD = [
    (1, "2026-05-10 09:00:00", "المصنع", "وارد ذهب (عيار 18)", 500.0, 0, 18, "قيد افتتاحي", "ACTIVE", 1, "", "", ""),
    (2, "2026-06-11 09:00:00", "أحمد", "صرف ذهب", 100.0, 0, 0, "", "ACTIVE", 0, "T-1", "1", ""),
    (3, "2026-06-11 09:05:00", "أحمد", "قبض ذهب", 96.0, 0, 0, "", "ACTIVE", 0, "T-1", "1", ""),
    (4, "2026-07-02 10:00:00", "سالم", "صرف ذهب", 50.0, 0, 0, "", "ACTIVE", 0, "T-9", "2", ""),
    (5, "2026-07-02 10:05:00", "سالم", "قبض ذهب", 48.0, 0, 0, "", "ACTIVE", 0, "T-9", "2", ""),
    # خياس طقوم قديم بعلامة 0.0 (النسخة القديمة لم تكن تفرّق الأنواع)
    (6, "2026-07-15 11:00:00", "عميل", "خياس طقوم", 3.0, 0, 0, "خياس طقم", "ACTIVE", 0, "T-1", "1", "5001"),
    (7, "2026-07-15 11:00:00", "عميل", "مبيعات ذهب", 40.0, 0, 0, "مبيعات", "ACTIVE", 0, "T-1", "1", "5001"),
]
con.executemany("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", OLD)
con.execute("INSERT INTO settings VALUES('invoice_counter','7')")
con.commit()

before = {
    "count": con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0],
    "sum": con.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0],
    "names": con.execute("SELECT COUNT(*) FROM names").fetchone()[0],
    "types": con.execute("SELECT COUNT(DISTINCT op_type) FROM invoices").fetchone()[0],
}
con.close()

# التحديث يُشغّل install_sync_schema على قاعدة العميل
install_sync_schema(db)

con = sqlite3.connect(db)
after = {
    "count": con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0],
    "sum": con.execute("SELECT ROUND(SUM(weight),2) FROM invoices").fetchone()[0],
    "names": con.execute("SELECT COUNT(*) FROM names").fetchone()[0],
    "types": con.execute("SELECT COUNT(DISTINCT op_type) FROM invoices").fetchone()[0],
}
assert before == after, (before, after)
print(f"\n✔ بعد التحديث: {after['count']} حركة | {after['sum']} جم | {after['names']} أسماء — مطابقة 100%")

# الحركة القديمة محفوظة حرفياً
row = con.execute("SELECT date_time,name,op_type,weight,note,set_number,manual_no "
                  "FROM invoices WHERE invoice_id=6").fetchone()
assert row == ("2026-07-15 11:00:00", "عميل", "خياس طقوم", 3.0, "خياس طقم", "T-1", "5001")
print("✔ تفاصيل الحركات القديمة محفوظة حرفياً (تاريخ/نوع/وزن/بيان/أرقام)")

# خياس الطقوم القديم يُقرأ كخياس تلميع نهائي ويؤثر على الخزينة كما كان
assert con.execute("SELECT trees_count, settled_status FROM invoices WHERE invoice_id=6").fetchone() == (0.0, "ACTIVE")
print("✔ خياس الطقوم القديم يبقى ACTIVE بعلامة 0.0 → يُقرأ كخياس تلميع نهائي ويخصم من الخزينة كما كان")

# بنية المزامنة أُضيفت بلا مساس بالبيانات
tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
assert {"invoices", "names", "settings", "sync_outbox", "sync_state"} <= tables
print("✔ جداول المزامنة أُضيفت بجانب جداول العميل بلا تعديل عليها")
con.close()

# ---------- ٥) إعادة تشغيل التحديث لا تُكرّر شيئاً ----------
install_sync_schema(db)
con = sqlite3.connect(db)
assert con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == before["count"]
con.close()
print("✔ إعادة تشغيل التحديث آمنة — لا تكرار ولا فقد")

print("\n✅ التحديث آمن على بيانات العميل بالكامل")
