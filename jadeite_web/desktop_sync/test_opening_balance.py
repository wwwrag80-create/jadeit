# -*- coding: utf-8 -*-
"""اختبار: ترحيل رصيد الفترة السابقة + مصدر خياس التلميع النهائي + التراجع عن الإقفال"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) ترحيل الرصيد ═══
ns = {}
exec("class S:\n"
     "    @staticmethod\n    def inv_period(inv):\n"
     '        p = (inv.get("period") or "").strip()\n'
     '        return p if p else str(inv.get("التاريخ", ""))[:7]\n'
     + textwrap.indent(textwrap.dedent(seg("get_opening_treasury_balance")), "    ")
     + "\n"
     + textwrap.indent(textwrap.dedent(seg("treasury_effect")), "    ")
     + "\n"
     "    def get_all_stage_categories(self): return []\n"
     "    def get_stage_config(self, c): return ('', '', '')\n"
     "    def get_recorded_periods(self): return ['2026-09', '2026-08', '2026-07']\n"
     "    def get_current_unclosed_khayas(self, cat, month=None): return 0.0\n", ns)
app = ns["S"]()


def inv(i, t, w, period, st="ACTIVE"):
    return {"رقم الفاتورة": i, "النوع": t, "الوزن": w, "period": period,
            "settled_status": st, "التاريخ": f"{period}-05 10:00"}


app.invoices = {
    1: inv(1, "رصيد افتتاحي", 1000.0, "2026-07"),
    2: inv(2, "مبيعات ذهب", 300.0, "2026-07"),      # فترة ٧: 1000 − 300 = 700
    3: inv(3, "وارد ذهب (عيار 18)", 200.0, "2026-08"),
    4: inv(4, "مبيعات ذهب", 50.0, "2026-08"),        # فترة ٨: +150
    5: inv(5, "مبيعات ذهب", 999.0, "2026-09"),
    6: inv(6, "مبيعات ذهب", 500.0, "2026-08", st="SETTLED"),   # ملغاة
}

o7 = app.get_opening_treasury_balance("2026-07")
o8 = app.get_opening_treasury_balance("2026-08")
o9 = app.get_opening_treasury_balance("2026-09")
assert o7 == 0.0, o7
print(f"✔ أول فترة (٢٠٢٦-٠٧): رصيد أول المدة = {o7} (لا فترة قبلها)")
assert o8 == 700.0, o8
print(f"✔ فترة ٢٠٢٦-٠٨: رصيد أول المدة = {o8} (مُرحَّل من فترة ٧)")
assert o9 == 850.0, o9
print(f"✔ فترة ٢٠٢٦-٠٩: رصيد أول المدة = {o9} (700 + 150 من فترة ٨)")
print("  → لم يعد أي رصيد يبدأ من الصفر")

# الحركات الملغاة لا تُرحَّل
assert app.treasury_effect(app.invoices[6]) == 0.0
print("✔ الحركات الملغاة لا تدخل رصيد أول المدة")

# ═══ ٢) الحلقة الحية تبدأ من رصيد أول المدة ═══
rec = seg("recalculate_all")
assert "running_balance = self.get_opening_treasury_balance(self.current_display_month)" in rec
print("✔ رصيد الخزينة الحي يبدأ من رصيد أول المدة لا من الصفر")

# ═══ ٣) عمود الخياس من شاشة المبيعات ═══
inq = seg("render_stage_monthly_inquiry")
assert 'if cat == "خياس الطقوم":' in inq and "get_sales_ops_khayas_total(m)" in inq
print("✔ عمود الخياس في صندوق التلميع النهائي = إجمالي عمود خياس بشاشة المبيعات")

cum = seg("get_box_khayas_cumulative")
assert "get_sales_ops_khayas_total" in cum
print("✔ ونفس المصدر في حساب الصندوق (لا مصدران مختلفان)")

tot = seg("get_sales_ops_khayas_total")
assert "get_sale_invoice_groups" in tot and "if month is None" in tot
print("✔ ويُقرأ لفترة واحدة فقط (لا يجمع فترتين)")

# ═══ ٤) التراجع عن الإقفال ═══
ro = seg("reopen_khayas_box_dialog")
i_btn = ro.find('btns.pack(side="bottom"')
i_tree = ro.find('frame.pack(fill="both", expand=True')
assert i_btn != -1 and i_btn < i_tree, "الأزرار قد تُدفع خارج النافذة"
print("✔ أزرار التراجع تُرصف من الأسفل أولاً — لا يمكن أن تُدفع خارج النافذة")
assert 'tree.bind("<Double-1>", lambda e: do_reopen())' in ro
print("✔ النقر المزدوج على الإقفال يتراجع عنه مباشرة")
assert 'if deleted == 0:' in ro
print("✔ لو لم يُحذف أي قيد تظهر رسالة واضحة بالسبب")
assert "delete_invoice_from_db" in ro and "recalculate_all" in ro
print("✔ التراجع يحذف القيد فعلياً ويعيد الحساب الشامل")

print("\n✅ ترحيل الرصيد وخياس التلميع والتراجع عن الإقفال — كلها سليمة")
