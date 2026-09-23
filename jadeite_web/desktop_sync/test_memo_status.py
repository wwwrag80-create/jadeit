# -*- coding: utf-8 -*-
"""
اختبار حاسم: السطور المعلوماتية (خياس البوليش / خياس المركب / صافي الطقم)
يجب أن تكون خارج **كل** الحسابات المالية، وداخل العرض وإعادة البناء فقط.
"""
import ast, io, re, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

consts = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in ("MEMO_STATUS", "KHAYAS_MARK_POLISH",
                                                    "KHAYAS_MARK_ASSEMBLER", "KHAYAS_MARK_NET",
                                                    "KHAYAS_MARK_FINAL"):
                consts[t.id] = node.value.value
assert consts["MEMO_STATUS"] == "MEMO"
print(f"✔ الحالة المعلوماتية معرّفة: {consts['MEMO_STATUS']}")

# ---------- ١) الحالة MEMO ليست ضمن الحالات المحسوبة ----------
accounting_filters = re.findall(r'settled_status"\)\s*not in \(([^)]*)\)', src)
assert accounting_filters, "لم يُعثر على فلاتر الحسابات"
memo_leaks = [f for f in accounting_filters if "MEMO" in f and "SALE_READ" not in f]
assert not memo_leaks, f"MEMO مسموح بها في فلتر محاسبي! {memo_leaks}"
print(f"✔ {len(accounting_filters)} فلتراً محاسبياً — لا أحد منها يقبل MEMO")

# ---------- ٢) السطور الثلاثة تُسجَّل بحالة MEMO ----------
post = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                        and m.name == "post_sale_rows"))
for label, mark in [("خياس البوليش", "KHAYAS_MARK_POLISH"),
                    ("خياس المركب", "KHAYAS_MARK_ASSEMBLER"),
                    ("صافي الطقم", "KHAYAS_MARK_NET")]:
    idx = post.find(mark)
    window = post[max(0, idx - 350):idx + 60]
    assert '"settled_status": MEMO_STATUS' in window, f"{label} ليس MEMO!"
    print(f"✔ {label:16} → MEMO (خارج الخزينة وكشفها)")

idx = post.find("KHAYAS_MARK_FINAL")
window = post[max(0, idx - 350):idx + 60]
assert '"settled_status": "ACTIVE"' in window
assert '"البيان": "خياس التلميع النهائي"' in post
print("✔ خياس التلميع النهائي → ACTIVE (يخصم من الخزينة، وبيانه مطابق لاسم صندوقه)")

# ---------- ٣) محاكاة رصيد الخزينة ----------
def treasury(invoices):
    """يحاكي الفلتر المحاسبي المستخدم في كل النظام"""
    bal = 0.0
    for inv in invoices:
        if inv["settled_status"] not in ("ACTIVE", "SETTLED_INOUT"):
            continue
        if inv["النوع"] == "وارد ذهب (عيار 18)":
            bal += inv["الوزن"]
        elif inv["النوع"] in ("مبيعات ذهب", "خياس طقوم"):
            bal -= inv["الوزن"]
    return round(bal, 2)


M = consts["MEMO_STATUS"]
invoices = [
    {"النوع": "وارد ذهب (عيار 18)", "الوزن": 100.0, "settled_status": "ACTIVE"},   # قيد افتتاحي
    {"النوع": "مبيعات ذهب",          "الوزن": 10.0,  "settled_status": "ACTIVE"},
    {"النوع": "خياس طقوم",           "الوزن": 1.0,   "settled_status": M},          # بوليش
    {"النوع": "خياس طقوم",           "الوزن": 1.0,   "settled_status": M},          # مركب
    {"النوع": "خياس طقوم",           "الوزن": 1.6,   "settled_status": M},          # صافي
    {"النوع": "خياس طقوم",           "الوزن": 2.0,   "settled_status": "ACTIVE"},   # تلميع نهائي
]
got = treasury(invoices)
assert got == 88.0, f"الرصيد الخاطئ {got}"
print(f"\n✔ رصيد الخزينة = {got} (100 − 10 مبيعات − 2 خياس تلميع نهائي فقط)")
print("  السلوك القديم كان 84.40 لأنه خصم البوليش والمركب والصافي أيضاً")

# عدد الحركات الظاهرة في كشف الخزينة
visible = [i for i in invoices if i["settled_status"] in ("ACTIVE", "SETTLED_INOUT")]
assert len(visible) == 3
print(f"✔ كشف الخزينة يعرض {len(visible)} حركات فقط (افتتاحي + مبيعات + خياس تلميع نهائي)")

# ---------- ٤) MEMO ما زالت مقروءة لإعادة البناء والحذف ----------
for name in ("get_sale_invoice_records", "get_sale_invoice_groups"):
    body = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == name))
    assert "SALE_READ_STATUSES" in body, name
print("✔ إعادة بناء الفاتورة وحذفها يقرآن السطور المعلوماتية (لا سطور يتيمة)")

for name in ("get_sets_net_rows", "get_set_khayas_breakdown"):
    body = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == name))
    assert "SALE_READ_STATUSES" in body, name
print("✔ كشوف ربح/خسارة الطقم تقرأ السطور المعلوماتية")

print("\n✅ الفصل المحاسبي سليم: الذهب وخياس التلميع النهائي فقط يؤثران على الخزينة")
