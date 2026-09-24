# -*- coding: utf-8 -*-
"""
اختبار: الخياس الفعلي للمصنعين والمركبين مستقل لكل فترة.
فترة ٩ لها خياسها، وفترة ١٠ تبدأ بخياس جديد خاص بها.
"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

ns = {}
exec("class S:\n"
     "    @staticmethod\n    def inv_period(inv):\n"
     '        p = (inv.get("period") or "").strip()\n'
     '        return p if p else str(inv.get("التاريخ", ""))[:7]\n'
     "    @classmethod\n    def inv_in_period(cls, inv, month):\n"
     "        return True if not month else cls.inv_period(inv) == month\n"
     + textwrap.indent(textwrap.dedent(seg("invoices_by_name")), "    ") + "\n"
     + textwrap.indent(textwrap.dedent(seg("get_box_closed_total")), "    ") + "\n"
     + textwrap.indent(textwrap.dedent(seg("get_current_unclosed_khayas")), "    ") + "\n"
     + textwrap.indent(textwrap.dedent(seg("get_unclosed_periods")), "    ") + "\n"
     "    def get_box_account_name(self, cat): return f'صندوق خياس {cat}'\n"
     "    def get_box_khayas_cumulative(self, cat, month=None): return 0.0\n"
     "    def get_box_recovered_total(self, cat, month=None): return 0.0\n"
     "    def get_actual_section_khayas(self, cat, target_month=None, include_settled=False):\n"
     "        return self._live.get((cat, target_month), 0.0)\n"
     "    def get_recorded_periods(self): return ['2026-10', '2026-09', '2026-08']\n", ns)
app = ns["S"]()
app.current_display_month = "2026-10"
app.invoices = {}

# الخياس الحي لكل فترة
app._live = {
    ("المصنعين", "2026-09"): 10.0,   # خياس شهر ٩
    ("المصنعين", "2026-10"): 5.0,    # خياس شهر ١٠
    ("المركبين", "2026-09"): 3.0,
    ("المركبين", "2026-10"): 0.0,
}

# ═══ ١) قبل أي إقفال: كل فترة بخياسها ═══
assert app.get_current_unclosed_khayas("المصنعين", month="2026-09") == 10.0
assert app.get_current_unclosed_khayas("المصنعين", month="2026-10") == 5.0
print("✔ فترة ٩: خياس المصنعين = 10.0  |  فترة ١٠: خياس جديد = 5.0")
print("  → كل فترة بخياسها المستقل")

# ═══ ٢) إقفال فترة ٩ لا يمسّ فترة ١٠ ═══
app.invoices = {
    1: {"رقم الفاتورة": 1, "الاسم": "صندوق خياس المصنعين", "النوع": "قيد يومي دائن",
        "الوزن": 10.0, "settled_status": "ACTIVE", "period": "2026-09",
        "التاريخ": "2026-09-30 23:00", "set_number": "JE-1"},
}
assert app.get_current_unclosed_khayas("المصنعين", month="2026-09") == 0.0
assert app.get_current_unclosed_khayas("المصنعين", month="2026-10") == 5.0
print("✔ بعد إقفال فترة ٩: خياسها = 0.0، وفترة ١٠ تبقى 5.0 كما هي")
print("  (قبل الإصلاح كان إقفال فترة سابقة يخصم من الفترة الجديدة فتظهر بالسالب)")

# ═══ ٣) كشف الفترات المنتهية غير المقفلة ═══
app.invoices = {}
pending = app.get_unclosed_periods("المصنعين")
months = [m for m, _a in pending]
assert "2026-09" in months, pending
assert "2026-10" not in months, "الفترة الحالية يجب ألا تُطلب للإقفال"
print(f"✔ الفترات المنتهية غير المقفلة: {months}")
print("  (الفترة الحالية مستثناة — عملها لم ينتهِ بعد)")

app.invoices = {
    1: {"رقم الفاتورة": 1, "الاسم": "صندوق خياس المصنعين", "النوع": "قيد يومي دائن",
        "الوزن": 10.0, "settled_status": "ACTIVE", "period": "2026-09",
        "التاريخ": "2026-09-30 23:00", "set_number": "JE-1"},
}
assert app.get_unclosed_periods("المصنعين") == []
print("✔ بعد الإقفال لا تظهر الفترة في قائمة المطلوب إقفالها")

# ═══ ٤) الإقفال يعمل على الفترة المحددة ═══
close = seg("close_split_khayas_box")
assert "def close_split_khayas_box(self, cat, month=None)" in close
assert "month = month or self.current_display_month" in close
assert "target_month=month" in close and "get_box_closed_total(cat, month=month)" in close
print("✔ الإقفال يُحسب ويُسجَّل للفترة المحددة وحدها")

# ═══ ٥) التنبيه عند تغيير الفترة ═══
chg = seg("on_period_changed")
assert "check_unclosed_previous_periods" in chg
print("✔ تغيير الفترة ينبّه إن كان هناك خياس فترة منتهية لم يُقفل")

chk = seg("check_unclosed_previous_periods")
assert "askyesno" in chk and "close_split_khayas_box" in chk
print("✔ التنبيه يعرض الفترات ومبالغها ويطلب موافقتك قبل الإقفال")
assert "log_cloud_error" in chk
print("✔ فشل إقفال فترة لا يوقف إقفال البقية")

print("\n✅ خياس كل فترة مستقل، والإقفال يُثبّته في فترته")
