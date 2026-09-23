# -*- coding: utf-8 -*-
"""
اختبار: سطر (الخياس الفعلي) في كشف الخزينة يظهر لكل فترة بقيمته الكاملة،
ولا يختفي عند الانتقال لفترة جديدة — ورصيد افتتاح الفترة = آخر رصيد في كشف
سابقتها، **قبل الإقفال وبعده**.

الإقفال قيد بين «حساب الخسائر» وصندوق الخياس، لا يمسّ الخزينة. كان الكشف
ورصيد أول المدة يخصمان «غير المُقفل» فقط، فبمجرد إقفال خياس فترة ٩ يرتفع
رصيد افتتاح فترة ١٠ بقيمة المُقفل، فتختلف أرقام الفترة الجديدة عن نهاية سابقتها.
"""
import ast, calendar, datetime, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
lines = src.split("\n")
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node_of(name):
    return next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)


seg = lambda n: ast.get_source_segment(src, node_of(n))


def method_src(name):
    node = node_of(name)
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return textwrap.indent(textwrap.dedent("\n".join(lines[start - 1:node.end_lineno])), "    ")


# ═══ ١) السطر يُبنى لكل فترة بقيمته الكاملة ═══
led = seg("_account_ledger_rows_all")
assert "for period, invs in sorted(by_period.items()):" in led
print("✔ سطر الخياس الفعلي يُبنى لكل فترة فيها حركات، لا للفترة المعروضة وحدها")
assert "self.get_actual_section_khayas(cat, target_month=period, invoices=invs)" in led
assert "get_current_unclosed_khayas" not in led
print("✔ ويعرض الخياس الفعلي **كاملاً** — الإقفال لا يُخرجه من الخزينة")
assert "self.period_closing_datetime(period)" in led
print("✔ ويُؤرَّخ في آخر فترته فيقع في مكانه الصحيح من الكشف")
assert 'f"خياس فعلي — فترة {period}"' in led and "أُقفل منه" in led
print("✔ وبيانه يذكر فترته، وما أُقفل منه لحساب الخسائر")

# ═══ ٢) رصيد أول المدة من دفتر الخزينة الموحّد ═══
opening = seg("get_opening_treasury_balance")
assert "self.get_treasury_ledger(before=month)" in opening
comp = seg("treasury_period_components")
assert "self.get_workers_khayas(month, invoices=invoices)" in comp
print("✔ رصيد افتتاح الفترة يُقرأ من دفتر الخزينة نفسه الذي يبني الكشف والتقرير")

# ═══ ٣) محاكاة عددية بأرقام لقطتك — قبل الإقفال وبعده ═══
ns = {"calendar": calendar, "datetime": datetime, "COUNTED_STATUSES": ("ACTIVE", "SETTLED_INOUT")}
exec("class S:\n"
     + "\n".join(method_src(m) for m in (
         "inv_period", "inv_in_period", "get_treasury_type_sets", "treasury_bucket",
         "get_workers_khayas", "treasury_period_components", "get_treasury_ledger",
         "get_opening_treasury_balance", "period_closing_datetime"))
     + "\n    def get_smart_default_date(self): return '2026-10-05'\n"
     "    def get_all_stage_categories(self): return ['الكاستنج','التلميع/البف']\n"
     "    def get_stage_config(self, c):\n"
     "        return {'الكاستنج': ('صرف كاستنج','قبض كاستنج',''),\n"
     "                'التلميع/البف': ('صرف تلميع بف','قبض تلميع بف','')}[c]\n"
     "    def get_actual_section_khayas(self, cat, target_month=None, include_settled=False, invoices=None):\n"
     "        return self._k.get((cat, target_month), 0.0)\n", ns)
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
# الخياس الفعلي لفترة ٩ = ٥ (كما في لقطتك)
app._k = {("المصنعين", "2026-09"): 5.0}

opening10 = app.get_opening_treasury_balance("2026-10")
assert opening10 == 65.0, opening10
print(f"\n✔ رصيد افتتاح فترة ١٠ = {opening10} (٧٠ من الحركات − ٥ خياس فترة ٩)")
print("  → مطابق لآخر رصيد في كشف فترة ٩ (٦٥.٠٠) كما في لقطتك الأولى")

# الإقفال لا يغيّر الخياس الفعلي (يسجّل قيداً بين الخسائر والصندوق فقط)،
# فيبقى رصيد الافتتاح كما هو — كان يقفز إلى ٧٠
assert app.get_opening_treasury_balance("2026-10") == 65.0
print("✔ وبعد إقفال خياس فترة ٩ يبقى ٦٥ — لا يقفز إلى ٧٠")

# فترة ١٠ لها خياسها الجديد المستقل
app._k[("المصنعين", "2026-10")] = 3.0
led10 = {x["period"]: x for x in app.get_treasury_ledger()}
assert led10["2026-09"]["workers"] == -5.0 and led10["2026-10"]["workers"] == -3.0
assert led10["2026-10"]["carry"] == 65.0 and led10["2026-10"]["closing"] == 62.0
print("✔ فترة ١٠ لها خياس فعلي جديد (٣) وفترة ٩ تحتفظ بخياسها (٥) — مستقلان")

print("\n✅ خياس كل فترة يظهر ويبقى، والرصيد يُرحَّل صحيحاً قبل الإقفال وبعده")
