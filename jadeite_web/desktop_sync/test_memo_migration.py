# -*- coding: utf-8 -*-
"""
اختبار حاسم: السطور المعلوماتية القديمة تُصفّى من كشف الخزينة ورصيدها.
يُنفَّذ على قاعدة SQLite حقيقية بنفس منطق الترحيل.
"""
import ast, io, os, re, sqlite3, tempfile

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)
marks = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and (t.id.startswith("KHAYAS_MARK_") or t.id == "MEMO_STATUS"):
                marks[t.id] = node.value.value

# ═══ ١) الترحيل موجود ويستهدف العلامات الثلاث فقط ═══
assert "UPDATE invoices" in src and "settled_status = ?" in src
i = src.find("SET settled_status = ?")
block = src[i:i + 400]
for k in ("KHAYAS_MARK_POLISH", "KHAYAS_MARK_ASSEMBLER", "KHAYAS_MARK_NET"):
    assert k in block, k
assert "KHAYAS_MARK_FINAL" not in block
print("✔ الترحيل يستهدف: البوليش، المركب، صافي الطقم")
print("✔ ولا يمسّ خياس التلميع النهائي (يبقى مؤثّراً على الخزينة)")
assert "'ACTIVE', 'SETTLED_INOUT'" in block
print("✔ يشمل الحركات المسجّلة بأي من الحالتين المحسوبتين")

# ═══ ٢) تنفيذ فعلي على قاعدة ═══
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "t.db")
con = sqlite3.connect(db)
con.execute("""CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT,
  name TEXT, op_type TEXT, weight REAL, settled_status TEXT, trees_count REAL)""")

ROWS = [
    (1, "وارد ذهب (عيار 18)", 6000.0, "ACTIVE", 0.0),
    (2, "مبيعات ذهب",          23.37, "ACTIVE", 0.0),
    (3, "خياس طقوم",           1.64,  "ACTIVE", marks["KHAYAS_MARK_FINAL"]),      # يبقى
    (4, "خياس طقوم",           1.19,  "SETTLED_INOUT", marks["KHAYAS_MARK_POLISH"]),
    (5, "خياس طقوم",           0.17,  "SETTLED_INOUT", marks["KHAYAS_MARK_ASSEMBLER"]),
    (6, "خياس طقوم",           1.63,  "SETTLED_INOUT", marks["KHAYAS_MARK_NET"]),
]
for i_, op, w, st, tc in ROWS:
    con.execute("INSERT INTO invoices VALUES (?,?,?,?,?,?,?)",
                (i_, "2026-08-29 21:40:06", "المصنع", op, w, st, tc))
con.commit()


def treasury(conn):
    bal = 0.0
    for op, w, st in conn.execute("SELECT op_type, weight, settled_status FROM invoices"):
        if st not in ("ACTIVE", "SETTLED_INOUT"):
            continue
        if op == "وارد ذهب (عيار 18)":
            bal += w
        elif op in ("مبيعات ذهب", "خياس طقوم"):
            bal -= w
    return round(bal, 2)


before = treasury(con)
rows_before = con.execute(
    "SELECT COUNT(*) FROM invoices WHERE settled_status IN ('ACTIVE','SETTLED_INOUT')").fetchone()[0]
print(f"\nقبل الترحيل: الرصيد {before} | {rows_before} حركة في الكشف")

con.execute("""UPDATE invoices SET settled_status = ?
               WHERE op_type = 'خياس طقوم'
                 AND settled_status IN ('ACTIVE','SETTLED_INOUT')
                 AND trees_count IN (?,?,?)""",
            (marks["MEMO_STATUS"], marks["KHAYAS_MARK_POLISH"],
             marks["KHAYAS_MARK_ASSEMBLER"], marks["KHAYAS_MARK_NET"]))
con.commit()

after = treasury(con)
rows_after = con.execute(
    "SELECT COUNT(*) FROM invoices WHERE settled_status IN ('ACTIVE','SETTLED_INOUT')").fetchone()[0]
print(f"بعد الترحيل:  الرصيد {after} | {rows_after} حركة في الكشف")

removed = round(1.19 + 0.17 + 1.63, 2)
assert after == round(before + removed, 2), (before, after)
print(f"✔ عاد للرصيد {removed} جم كانت تُخصم خطأً")
assert rows_after == rows_before - 3
print("✔ اختفت الحركات الثلاث من الكشف")

kept = con.execute("SELECT settled_status FROM invoices WHERE invoice_id=3").fetchone()[0]
assert kept == "ACTIVE"
print("✔ خياس التلميع النهائي ما زال ACTIVE ويؤثّر على الخزينة")

# إعادة التشغيل آمنة
con.execute("""UPDATE invoices SET settled_status = ?
               WHERE op_type='خياس طقوم' AND settled_status IN ('ACTIVE','SETTLED_INOUT')
                 AND trees_count IN (?,?,?)""",
            (marks["MEMO_STATUS"], marks["KHAYAS_MARK_POLISH"],
             marks["KHAYAS_MARK_ASSEMBLER"], marks["KHAYAS_MARK_NET"]))
con.commit()
assert treasury(con) == after
print("✔ إعادة تشغيل الترحيل لا تغيّر شيئاً")
con.close()

# ═══ ٣) التسمية والانتقال لآخر صف ═══
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))
led = seg("refresh_op_ledger_table")
assert "self.op_ledger_tree.see(rows[-1])" in led
print("✔ اختيار الاسم ينتقل لآخر صف وآخر عملياته")

inq = seg("refresh_inquiry_table")
assert "الخياس الفعلي ({self.get_display_label(cat_now)})" in inq
assert "get_actual_section_khayas(cat_now)" in inq
print("✔ المصنعون والمركبون: التسمية «الخياس الفعلي» بالمعادلة المعتمدة")

print("\n✅ الخزينة صارت نظيفة والحسابات تتطابق")
