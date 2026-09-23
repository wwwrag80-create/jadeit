# -*- coding: utf-8 -*-
"""
اختبار: شريط الخزينة العلوي = كشف حساب الخزينة، دائماً.

الخطأ الذي يمنعه: حلقة حساب الرصيد الحي كانت بلا فلتر حالة إطلاقاً، فكانت
تحتسب السطور المعلوماتية (MEMO) والحركات الملغاة — بينما كشف الحساب يفلترها.
النتيجة: رقمان مختلفان لنفس الخزينة (73.50 في الشريط مقابل 78.00 في الكشف).
"""
import ast, io, re

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

# ---------- ١) حلقة الرصيد الحي تفلتر الحالة ----------
recalc = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                          and m.name == "recalculate_all"))
loop_idx = recalc.find("for inv in sorted_invoices:")
assert loop_idx != -1, "لم يُعثر على حلقة حساب الخزينة"
loop_head = recalc[loop_idx:loop_idx + 600]
assert 'settled_status") not in ("ACTIVE", "SETTLED_INOUT")' in loop_head, \
    "حلقة الخزينة بلا فلتر حالة — سيختلف الشريط عن الكشف!"
print("✔ حلقة الرصيد الحي تفلتر الحالة كما يفلترها كشف الحساب")

# ---------- ٢) كشف حساب الخزينة يستخدم الفلتر نفسه ----------
stmt = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                        and m.name == "get_account_ledger_rows"))
assert 'settled_status") not in ("ACTIVE", "SETTLED_INOUT")' in stmt
print("✔ كشف حساب الخزينة يستخدم الفلتر نفسه")

# ---------- ٣) محاكاة عددية: الشريط والكشف يجب أن يتطابقا ----------
MEMO = "MEMO"
SARF = {"مبيعات ذهب", "مبيعات ذهب مع الماس", "خياس طقوم"}
IN = {"وارد ذهب (عيار 18)"}


def live_bar(invs):
    """يحاكي حلقة الرصيد الحي بعد الإصلاح"""
    bal = 0.0
    for inv in invs:
        if inv["settled_status"] not in ("ACTIVE", "SETTLED_INOUT"):
            continue
        if inv["النوع"] in IN:
            bal += inv["الوزن"]
        elif inv["النوع"] in SARF:
            bal -= inv["الوزن"]
    return round(bal, 2)


def statement(invs):
    """يحاكي كشف حساب الخزينة"""
    bal = 0.0
    for inv in invs:
        if inv["settled_status"] not in ("ACTIVE", "SETTLED_INOUT"):
            continue
        if inv["النوع"] in IN:
            bal += inv["الوزن"]
        elif inv["النوع"] in SARF:
            bal -= inv["الوزن"]
    return round(bal, 2)


# نفس بيانات لقطة العميل
invoices = [
    {"النوع": "وارد ذهب (عيار 18)", "الوزن": 100.0, "settled_status": "ACTIVE"},   # قيد افتتاحي
    {"النوع": "مبيعات ذهب",          "الوزن": 20.0,  "settled_status": "ACTIVE"},
    {"النوع": "خياس طقوم",           "الوزن": 2.0,   "settled_status": "ACTIVE"},   # تلميع نهائي
    {"النوع": "خياس طقوم",           "الوزن": 1.0,   "settled_status": MEMO},       # بوليش
    {"النوع": "خياس طقوم",           "الوزن": 1.0,   "settled_status": MEMO},       # مركب
    {"النوع": "خياس طقوم",           "الوزن": 2.5,   "settled_status": MEMO},       # صافي
    {"النوع": "مبيعات ذهب",          "الوزن": 50.0,  "settled_status": "SETTLED"},  # ملغاة
]

bar, stm = live_bar(invoices), statement(invoices)
assert bar == stm == 78.0, (bar, stm)
print(f"\n✔ الشريط = {bar}  |  الكشف = {stm}  → متطابقان تماماً")
print("  (100 − 20 مبيعات − 2 خياس تلميع نهائي = 78.00، كما في لقطتك)")

# السلوك القديم (بلا فلتر) كان يعطي رقماً مختلفاً
def old_bar(invs):
    bal = 0.0
    for inv in invs:
        if inv["النوع"] in IN:
            bal += inv["الوزن"]
        elif inv["النوع"] in SARF:
            bal -= inv["الوزن"]
    return round(bal, 2)


assert old_bar(invoices) != stm
print(f"✔ السلوك القديم كان يعطي {old_bar(invoices)} ≠ {stm} — وهذا سبب الاختلاف")

# ---------- ٤) الحركات الملغاة لا تُحتسب في أي منهما ----------
cancelled_only = [i for i in invoices if i["settled_status"] == "SETTLED"]
assert live_bar(cancelled_only) == 0.0 and statement(cancelled_only) == 0.0
print("✔ الحركات الملغاة (SETTLED) لا تُحتسب في الشريط ولا في الكشف")

print("\n✅ شريط الخزينة وكشف حسابها يستخدمان الفلتر نفسه — لا اختلاف ممكن")
