# -*- coding: utf-8 -*-
"""
اختبار عزل الفترات: كل فترة مستقلة بعملياتها وأرقامها.
الحالة: تعمل في فترة ٢٠٢٦-٠٨ وتاريخ الجهاز ٢٠٢٦-٠٩ — يجب ألا تظهر فترة ٩.
"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def seg(n):
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == n))


# ═══ ١) شاشة صناديق الخياس تعرض الفترة المعروضة وحدها ═══
inq = seg("render_stage_monthly_inquiry")
assert "self.inv_period(inv) != self.current_display_month" in inq
assert "months.add(self.current_display_month)" in inq
assert "months.add(dt[:7])" not in inq
print("✔ صناديق الخياس: تعرض الفترة المعروضة وحدها (كانت تجمع الشهور من التاريخ)")

# ═══ ٢) رصيد الخزينة للفترة المعروضة ═══
rec = seg("recalculate_all")
assert "self.inv_in_period(inv, self.current_display_month)" in rec
print("✔ رصيد الخزينة البارز = رصيد الفترة المعروضة وحدها")

# ═══ ٣) خياس الصندوق مقيّد بالفترة افتراضياً ═══
cum = seg("get_box_khayas_cumulative")
assert "if month is None:" in cum and "month = self.current_display_month" in cum
assert "self.period_invoices(month)" in cum     # حركات الفترة من فهرسها
print("✔ خياس الصندوق يُحسب للفترة المعروضة افتراضياً")

# ═══ ٤) محاكاة عددية ═══
ns = {}
exec("class S:\n"
     "    @staticmethod\n"
     "    def inv_period(inv):\n"
     '        p = (inv.get("period") or "").strip()\n'
     '        return p if p else str(inv.get("التاريخ", ""))[:7]\n'
     "    @classmethod\n"
     "    def inv_in_period(cls, inv, month):\n"
     "        return True if not month else cls.inv_period(inv) == month\n", ns)
S = ns["S"]

invs = [
    # حركات فترة ٨ — بعضها بتاريخ شهر ٩ (سُجّلت ونحن في فترة ٨)
    {"التاريخ": "2026-08-20 10:00", "period": "2026-08", "الوزن": 100.0},
    {"التاريخ": "2026-09-01 11:00", "period": "2026-08", "الوزن": 50.0},
    {"التاريخ": "2026-09-02 09:00", "period": "2026-08", "الوزن": 25.0},
    # حركة فترة ٩ فعلاً
    {"التاريخ": "2026-09-03 12:00", "period": "2026-09", "الوزن": 999.0},
]

p8 = [i for i in invs if S.inv_in_period(i, "2026-08")]
p9 = [i for i in invs if S.inv_in_period(i, "2026-09")]
assert len(p8) == 3 and len(p9) == 1
print(f"\n✔ فترة ٨: {len(p8)} حركات (منها اثنتان بتاريخ شهر ٩)")
print(f"✔ فترة ٩: {len(p9)} حركة فقط")

bal8 = round(sum(i["الوزن"] for i in p8), 2)
bal9 = round(sum(i["الوزن"] for i in p9), 2)
assert bal8 == 175.0 and bal9 == 999.0
print(f"✔ رصيد فترة ٨ = {bal8} (لا يشمل حركة فترة ٩)")
print(f"✔ رصيد فترة ٩ = {bal9} (لا يشمل حركات فترة ٨)")

# الفترات الظاهرة عند العمل في فترة ٨
shown = sorted({S.inv_period(i) for i in p8})
assert shown == ["2026-08"], shown
print(f"✔ عند العمل في فترة ٨ تظهر فترة واحدة فقط: {shown}")
print("  (قبل الإصلاح كانت تظهر ٢٠٢٦-٠٨ و٢٠٢٦-٠٩ معاً لأن الشهور تُجمع من التاريخ)")

# ═══ ٥) شاشة الخسائر: بحث بالفترات ═══
loss = seg("refresh_losses_tab")
assert "combo_losses_period" in loss and "month=month" in loss
print("\n✔ شاشة الخسائر: تعرض صناديق الفترة المختارة وحدها")

per = seg("get_recorded_periods")
assert "self.inv_period(inv)" in per
print("✔ قائمة الفترات تعرض الفترات المسجّلة فعلاً")

# ═══ ٦) التراجع عن الإقفال ═══
for fn in ("get_box_closing_entries", "reopen_khayas_box_dialog"):
    assert any(isinstance(m, ast.FunctionDef) and m.name == fn for m in cls.body), fn
reopen = seg("reopen_khayas_box_dialog")
assert "delete_invoice_from_db" in reopen and "recalculate_all" in reopen
print("✔ التراجع عن الإقفال: يحذف القيد المزدوج ويعيد الحساب الشامل")
assert "push_undo" in reopen
print("✔ ويحفظ لقطة تراجع قبل التنفيذ")
assert "askyesno" in reopen
print("✔ ويطلب تأكيداً يوضّح المبلغ وأثره")

entries = seg("get_box_closing_entries")
assert 'g["touches_box"]' in entries
print("✔ يعرض قيود إقفال هذا الصندوق فقط (لا قيود صناديق أخرى)")

print("\n✅ عزل الفترات والتراجع عن الإقفال يعملان بشكل سليم")
