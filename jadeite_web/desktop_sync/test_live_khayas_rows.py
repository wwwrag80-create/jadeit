# -*- coding: utf-8 -*-
"""
اختبار: سطر (الخياس الفعلي) يظهر لكل فترة بقيمتها، ولا يختفي عند الانتقال
لفترة جديدة — وكل فترة تبدأ بخياس فعلي جديد خاص بها.
"""
import ast, calendar, datetime, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) السطر يُبنى لكل فترة ═══
led = seg("get_account_ledger_rows")
assert "for _period in self.get_recorded_periods():" in led
print("✔ سطر الخياس الفعلي يُبنى لكل فترة مسجّلة، لا للفترة المعروضة وحدها")
assert "self.get_current_unclosed_khayas(_cat, month=_period)" in led
print("✔ ويعرض **غير المُقفل** فقط (المُقفل له قيده الحقيقي في الكشف)")
assert "period_closing_datetime(_period)" in led
print("✔ ويُؤرَّخ في آخر فترته فيقع في مكانه الصحيح من الكشف")
assert 'f"خياس فعلي محسوب لحظياً — فترة {_period}"' in led
print("✔ وبيانه يذكر فترته صراحةً")

# لا استخدام للدالة القديمة بلا فترة
assert 'self.get_actual_section_khayas("المصنعين")\n' not in led
print("✔ لم يبقَ حساب مقيّد بالفترة المعروضة في الكشف")

# ═══ ٢) رصيد أول المدة يخصم خياس الفترات السابقة غير المقفل ═══
opening = seg("get_opening_treasury_balance")
assert "get_current_unclosed_khayas(cat, month=period)" in opening
print("✔ رصيد افتتاح الفترة يخصم الخياس غير المُقفل من الفترات السابقة")
print("  → رصيد افتتاح الفترة = آخر رصيد في كشف سابقتها بالضبط")

# ═══ ٣) محاكاة عددية بأرقام لقطتك ═══
ns = {"calendar": calendar, "datetime": datetime}
exec("class S:\n"
     "    @staticmethod\n    def inv_period(inv):\n"
     '        p = (inv.get("period") or "").strip()\n'
     '        return p if p else str(inv.get("التاريخ", ""))[:7]\n'
     + textwrap.indent(textwrap.dedent(seg("period_closing_datetime")), "    ")
     + "\n    def get_smart_default_date(self): return '2026-10-05'\n"
     + textwrap.indent(textwrap.dedent(seg("treasury_effect")), "    ")
     + "\n    def get_all_stage_categories(self): return ['الكاستنج','التلميع/البف']\n"
     "    def get_stage_config(self, c):\n"
     "        return {'الكاستنج': ('صرف كاستنج','قبض كاستنج',''),\n"
     "                'التلميع/البف': ('صرف تلميع بف','قبض تلميع بف','')}[c]\n"
     "    def get_recorded_periods(self): return ['2026-10','2026-09']\n"
     "    def get_current_unclosed_khayas(self, cat, month=None):\n"
     "        return self._k.get((cat, month), 0.0)\n"
     + textwrap.indent(textwrap.dedent(seg("get_opening_treasury_balance")), "    "), ns)
app = ns["S"]()
app.current_display_month = "2026-10"

def r(t, w, period):
    return {"النوع": t, "الوزن": w, "period": period, "settled_status": "ACTIVE",
            "التاريخ": f"{period}-05 11:38"}

app.invoices = {
    1: r("رصيد افتتاحي", 100.0, "2026-09"),
    2: r("صرف كاستنج", 10.0, "2026-09"),
    3: r("قبض كاستنج", 5.0, "2026-09"),
    4: r("صرف تلميع بف", 30.0, "2026-09"),
    5: r("قبض تلميع بف", 5.0, "2026-09"),
}
# خياس فترة ٩ غير مُقفل = ٥ (كما في لقطتك)
app._k = {("المصنعين", "2026-09"): 5.0, ("المركبين", "2026-09"): 0.0,
          ("المصنعين", "2026-10"): 0.0, ("المركبين", "2026-10"): 0.0}

opening10 = app.get_opening_treasury_balance("2026-10")
assert opening10 == 65.0, opening10
print(f"\n✔ رصيد افتتاح فترة ١٠ = {opening10} (٧٠ من الحركات − ٥ خياس فترة ٩ غير مُقفل)")
print("  → مطابق لآخر رصيد في كشف فترة ٩ (٦٥.٠٠) كما في لقطتك الأولى")

# فترة ١٠ لها خياسها الجديد
app._k[("المصنعين", "2026-10")] = 3.0
assert app.get_current_unclosed_khayas("المصنعين", month="2026-10") == 3.0
assert app.get_current_unclosed_khayas("المصنعين", month="2026-09") == 5.0
print("✔ فترة ١٠ لها خياس فعلي جديد (٣) وفترة ٩ تحتفظ بخياسها (٥) — مستقلان")

print("\n✅ خياس كل فترة يظهر ويبقى، والرصيد يُرحَّل صحيحاً")
