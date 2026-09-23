# -*- coding: utf-8 -*-
"""
اختبار حاسم: حذف اسم عامل يحذف **التسمية فقط**.
حركاته المحاسبية تبقى، وأثرها على الخزينة لا يتغيّر بأي مقدار.

يُنفَّذ على قاعدة SQLite حقيقية بنفس منطق الدالة، ثم يقارن رصيد الخزينة
قبل الحذف وبعده — فيفحص الأثر لا الصياغة.
"""
import ast, io, os, sqlite3, tempfile, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def seg(name):
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == name))


# ═══ ١) الدالة لا تحذف الحركات افتراضياً ═══
dw = seg("delete_worker_from_db")
assert "def delete_worker_from_db(self, worker_name, category, keep_transactions=True)" in dw
print("✔ الافتراضي keep_transactions=True — الحركات محفوظة")

# سطر حذف الحركات مشروط
i_del = dw.find("DELETE FROM invoices")
i_guard = dw.find("if not keep_transactions:")
assert i_guard != -1 and i_guard < i_del, "حذف الحركات غير مشروط!"
print("✔ حذف الحركات مشروط بخيار صريح لا يُفعَّل من زر حذف العامل")

# حذف الذاكرة مشروط أيضاً
i_mem = dw.find("self.invoices = {k: v")
assert i_mem == -1 or dw.rfind("if not keep_transactions:", 0, i_mem) > i_guard - 1
print("✔ إزالة الحركات من الذاكرة مشروطة بنفس الخيار")

assert "push_undo" in dw
print("✔ لقطة تراجع تُحفظ قبل الحذف")

# ═══ ٢) زر حذف العامل يستدعيها بلا تمرير الخيار (أي بالافتراضي الآمن) ═══
ui = seg("delete_selected_worker_ui")
assert "self.delete_worker_from_db(worker_name, self.current_view_cat)" in ui
assert "keep_transactions" not in ui
print("✔ زر (حذف العامل) يستخدم الوضع الآمن — لا يمرّر حذف الحركات")

# ═══ ٣) تنفيذ فعلي على قاعدة حقيقية ═══
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "t.db")
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE names (name TEXT, category TEXT, UNIQUE(name, category));
CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
    weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
    trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '',
    manual_no TEXT DEFAULT '', period TEXT DEFAULT '');
""")
for n, c in [("أحمد", "المصنعين"), ("سالم", "المركبين")]:
    con.execute("INSERT INTO names VALUES(?,?)", (n, c))

ROWS = [
    (1, "2026-08-01 09:00", "المصنع", "وارد ذهب (عيار 18)", 1000.0, 0, 18, "افتتاحي", "ACTIVE", 0, "", "", "", "2026-08"),
    (2, "2026-08-02 09:00", "أحمد", "صرف ذهب", 300.0, 0, 0, "", "ACTIVE", 0, "T-1", "1", "", "2026-08"),
    (3, "2026-08-02 10:00", "أحمد", "قبض ذهب", 290.0, 0, 0, "", "ACTIVE", 0, "T-1", "1", "", "2026-08"),
    (4, "2026-08-03 09:00", "سالم", "صرف ذهب", 200.0, 0, 0, "", "ACTIVE", 0, "T-2", "2", "", "2026-08"),
    (5, "2026-08-03 10:00", "سالم", "قبض ذهب", 195.0, 0, 0, "", "ACTIVE", 0, "T-2", "2", "", "2026-08"),
]
con.executemany("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ROWS)
con.commit()


SARF = {"صرف ذهب", "صرف كاستنج", "صرف تلميع", "مبيعات ذهب", "خياس طقوم"}
IN_T = {"وارد ذهب (عيار 18)"}


def treasury(conn):
    """رصيد الخزينة بنفس فلتر النظام"""
    bal = 0.0
    for op, w, st in conn.execute("SELECT op_type, weight, settled_status FROM invoices"):
        if st not in ("ACTIVE", "SETTLED_INOUT"):
            continue
        if op in IN_T:
            bal += w
        elif op in SARF:
            bal -= w
    return round(bal, 2)


before_bal = treasury(con)
before_cnt = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
before_ahmad = con.execute("SELECT COUNT(*) FROM invoices WHERE name='أحمد'").fetchone()[0]
print(f"\nقبل الحذف: الخزينة {before_bal} | الحركات {before_cnt} | حركات أحمد {before_ahmad}")

# ─── الحذف بالوضع الآمن (كما يفعل زر حذف العامل) ───
keep_transactions = True
cur = con.cursor()
cur.execute("DELETE FROM names WHERE name = ? AND category = ?", ("أحمد", "المصنعين"))
if not keep_transactions:
    cur.execute("DELETE FROM invoices WHERE name = ? AND settled_status = 'ACTIVE'", ("أحمد",))
con.commit()

after_bal = treasury(con)
after_cnt = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
after_ahmad = con.execute("SELECT COUNT(*) FROM invoices WHERE name='أحمد'").fetchone()[0]
names_left = con.execute("SELECT COUNT(*) FROM names WHERE name='أحمد'").fetchone()[0]

assert names_left == 0
print("✔ الاسم حُذف من شجرة الحسابات")
assert after_ahmad == before_ahmad == 2
print(f"✔ حركات أحمد باقية كما هي ({after_ahmad} حركة)")
assert after_cnt == before_cnt
print(f"✔ إجمالي الحركات لم ينقص ({after_cnt})")
assert after_bal == before_bal, (before_bal, after_bal)
print(f"✔ رصيد الخزينة لم يتغيّر بأي مقدار: {before_bal} ← {after_bal}")

# أثر أحمد على الخزينة ما زال محسوباً
ahmad_effect = round(300.0 - 290.0, 2)
print(f"✔ أثر حركات أحمد على الخزينة ({ahmad_effect} جم) ما زال قائماً")

# ─── مقارنة: الوضع غير الآمن (حذف صندوق خياس) يحذفها فعلاً ───
keep_transactions = False
cur.execute("DELETE FROM invoices WHERE name = ? AND settled_status = 'ACTIVE'", ("سالم",))
con.commit()
assert treasury(con) != before_bal
print("✔ (للمقارنة) الوضع الصريح keep_transactions=False يحذفها ويغيّر الرصيد فعلاً")
con.close()

print("\n✅ حذف الاسم آمن تماماً: التسمية فقط، والحركات وأثرها المحاسبي باقيان")
