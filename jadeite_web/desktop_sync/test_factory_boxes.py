# -*- coding: utf-8 -*-
"""
صناديق المصنع: اختيار شهر يعرض أرقامه وحده (الدفعة ٢٥)، و«من شهر/إلى شهر» بقائمتين — بلا كتابة
يدوية — يعرض أرقام الأشهر المختارة، و«الكل» كل الأشهر (الدفعة ٢٨) — بالمعادلات نفسها التي كانت
(تُقارن هنا بنسخة حرفية من الحساب القديم «من شهر/إلى شهر»).
"""
import ast, io, random, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(node, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, node))


def body(name):
    return member(name)


ns = {}
exec("class App:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in (
    "LOSSES_ALL", "inv_period", "invoices_by_period", "get_recorded_periods", "factory_period_options", "selected_factory_range",
    "factory_range_label", "factory_boxes_totals", "combo_range", "set_combo_range", "periods_in_range",
    "range_covers_all", "range_scope_label", "set_factory_range", "factory_show_all",
    "reset_factory_boxes_period", "statement_month_options", "statement_range", "set_statement_range")), ns)
App = ns["App"]


def old_totals(invoices, from_m, to_m):
    """الحساب القديم حرفياً (refresh_factory_boxes_table قبل الدفعة ٢٥) بنطاق «من شهر/إلى شهر»"""
    inv_period = App.inv_period
    in_type_map = {"ذهب": "وارد ذهب (عيار 18)", "فصوص وأحجار": "وارد فصوص وأحجار"}
    sale_type_map = {"ذهب": "مبيعات ذهب", "فصوص وأحجار": "مبيعات فصوص وأحجار"}
    sales_totals, incoming = {}, {}
    for box in ["ذهب", "فصوص وأحجار"]:
        tot_in = tot_sale = 0.0
        for inv in invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
            dt_m = inv_period(inv)
            if not (from_m <= dt_m <= to_m): continue
            t = inv.get("النوع")
            if t == in_type_map[box]: tot_in += inv["الوزن"]
            elif t == sale_type_map[box]: tot_sale += inv["الوزن"]
        sales_totals[box] = round(tot_sale, 2)
        incoming[box] = round(tot_in, 2)
    tot_gold_linked = tot_diamond = 0.0
    for inv in invoices.values():
        if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
        dt_m = inv_period(inv)
        if not (from_m <= dt_m <= to_m): continue
        t = inv.get("النوع")
        if t == "مبيعات ذهب مع الماس": tot_gold_linked += inv["الوزن"]
        elif t == "مبيعات الماس": tot_diamond += inv["الوزن"]
    tot_gold_linked, tot_diamond = round(tot_gold_linked, 2), round(tot_diamond, 2)
    pgs = round(sales_totals["ذهب"] + sales_totals["فصوص وأحجار"], 2)
    pgd = round(tot_gold_linked + tot_diamond, 2)
    gs = sales_totals["ذهب"]
    return {"sales": sales_totals, "incoming": incoming, "gold_linked": tot_gold_linked, "diamond": tot_diamond,
            "prod_gold_stones": pgs, "prod_gold_diamond": pgd, "prod_total": round(pgs + pgd, 2),
            "ratio_stones": round((sales_totals["فصوص وأحجار"] / gs) * 100, 2) if gs else 0.0,
            "ratio_diamond": round((tot_diamond / gs) * 100, 2) if gs else 0.0}


random.seed(7)
TYPES = ["وارد ذهب (عيار 18)", "مبيعات ذهب", "وارد فصوص وأحجار", "مبيعات فصوص وأحجار", "مبيعات ذهب مع الماس",
         "مبيعات الماس", "صرف كاستنج", "قبض ذهب"]
MONTHS = ["2026-07", "2026-08", "2026-09"]
app = App()
app.current_display_month = "2026-09"
app.invoices = {}
for i in range(600):
    m = random.choice(MONTHS)
    inv = {"النوع": random.choice(TYPES), "الوزن": round(random.uniform(0.1, 90), 2),
           "settled_status": random.choice(["ACTIVE", "ACTIVE", "ACTIVE", "SETTLED_INOUT", "MEMO", "SETTLED"]),
           "التاريخ": f"{m}-1{i % 9} 10:00:00"}
    if i % 3:
        inv["period"] = m              # بعضها بلا عمود فترة: تُشتق من التاريخ
    app.invoices[i] = inv

# ═══ ١) شهر بعينه = الحساب القديم بـ«من الشهر إلى الشهر» ═══
for m in MONTHS:
    assert app.factory_boxes_totals(m) == old_totals(app.invoices, m, m), m
print("✔ اختيار شهر: المبيعات والوارد والألماس والإنتاج ونسبه = الحساب السابق للشهر نفسه (" + "، ".join(MONTHS) + ")")

# ═══ ٢) «الكل» = كل الأشهر ═══
everything = app.factory_boxes_totals(app.LOSSES_ALL)
assert everything == old_totals(app.invoices, "0000-00", "9999-99")
for key in ("gold_linked", "diamond"):
    assert round(sum(app.factory_boxes_totals(m)[key] for m in MONTHS), 2) == everything[key]
for box in ("ذهب", "فصوص وأحجار"):
    assert round(sum(app.factory_boxes_totals(m)["sales"][box] for m in MONTHS), 2) == everything["sales"][box]
print(f"✔ «الكل»: كل الأشهر (مبيعات الذهب {everything['sales']['ذهب']:.2f}، إجمالي الإنتاج {everything['prod_total']:.2f}) "
      "= مجموع الأشهر")
assert app.factory_boxes_totals() == app.factory_boxes_totals("2026-09")
print("✔ بلا اختيار: الفترة المعروضة كما كان")

# ═══ ٣) «من شهر/إلى شهر» = الحساب القديم بالنطاق نفسه ═══
for lo, hi in (("2026-07", "2026-08"), ("2026-08", "2026-09")):
    assert app.factory_boxes_totals(lo, hi) == old_totals(app.invoices, lo, hi), (lo, hi)
    assert app.factory_boxes_totals(hi, lo) == app.factory_boxes_totals(lo, hi)     # «من» بعد «إلى»
assert app.factory_boxes_totals("2026-07", "2026-09") == everything                # النطاق كله = «الكل»
assert app.factory_boxes_totals("2026-08", "2026-08") == app.factory_boxes_totals("2026-08")
print("✔ من شهر إلى شهر: أرقام الأشهر المختارة = الحساب السابق بالنطاق نفسه، والمقلوب يُصحَّح، "
      "والنطاق الكامل = «الكل»")

# ═══ ٤) القائمتان والاختيار (لا كتابة يدوية) ═══
assert app.factory_period_options() == ["2026-09", "2026-08", "2026-07"]


class Combo:
    def __init__(self, v): self.v, self.values = v, None
    def get(self): return self.v
    def set(self, v): self.v = v
    def configure(self, values=None): self.values = values


app.refreshes = 0
app.refresh_factory_boxes_table = lambda: setattr(app, "refreshes", app.refreshes + 1)
app.combo_factory_from, app.combo_factory_to = Combo("2026-09"), Combo("2026-07")
assert app.selected_factory_range() == ("2026-07", "2026-09")
assert app.factory_range_label(*app.selected_factory_range()) == "أرقام كل الأشهر (2026-07 إلى 2026-09)"
app.combo_factory_from.v = app.combo_factory_to.v = "2026-08"
assert app.factory_range_label(*app.selected_factory_range()) == "أرقام شهر 2026-08"
app.combo_factory_from.v = "2026-07"
assert app.factory_range_label(*app.selected_factory_range()) == "أرقام الأشهر من 2026-07 إلى 2026-08"
app.factory_show_all()
assert (app.combo_factory_from.v, app.combo_factory_to.v) == ("2026-07", "2026-09") and app.refreshes == 1
assert app.combo_factory_from.values == ["2026-09", "2026-08", "2026-07"]
app.reset_factory_boxes_period()
assert app.selected_factory_range() == ("2026-09", "2026-09") and app.refreshes == 2
print("✔ القائمتان: الأشهر المسجّلة (الأحدث أولاً)، «الكل» من أقدمها إلى أحدثها، «الشهر الحالي ↺» يعيده، "
      "والسطر يذكر النطاق المعروض")

# ═══ ٥) الشاشة والطباعة والكشف بالنطاق نفسه ═══
build = body("build_factory_boxes_tab")
assert "self.combo_factory_from = self.make_month_combo(" in build and "self.combo_factory_to = self.make_month_combo(" in build
assert "CTkEntry" not in build and "combo_factory_period" not in src and "factory_from_month" not in src
assert "self.factory_show_all" in build and "self.reset_factory_boxes_period" in build
mk = body("make_month_combo")
assert 'state="readonly"' in mk and "command=lambda _v: on_change()" in mk
ref = body("refresh_factory_boxes_table")
assert "self.factory_boxes_totals(from_m, to_m)" in ref and "self.selected_factory_range()" in ref
pr = body("print_factory_boxes_screen")
assert "self.factory_boxes_totals(from_m, to_m)" in pr and "self.factory_range_label(from_m, to_m)" in pr
st = body("open_factory_box_statement")
assert "self.selected_factory_range()" in st and "self.set_statement_range(from_m, to_m)" in st
print("✔ الشاشة والطباعة من الحساب نفسه وبالنطاق نفسه، و«عرض كشف الحساب» بالأشهر المختارة («الكل» = بلا حدّ)")

# ═══ ٦) كشف الحساب: «من شهر/إلى شهر» قائمتان أيضاً، و«الكل» = بلا حدّ ═══
assert app.statement_month_options() == ["الكل", "2026-09", "2026-08", "2026-07"]
app.kh_from_month, app.kh_to_month = Combo("x"), Combo("x")
app.set_statement_range("", "")
assert (app.kh_from_month.v, app.kh_to_month.v) == ("الكل", "الكل") and app.statement_range() == ("", "")
assert app.kh_from_month.values == app.statement_month_options()
app.set_statement_range("2026-09", "2026-07")
assert app.statement_range() == ("2026-07", "2026-09")                       # المقلوب يُصحَّح
app.kh_to_month.v = "الكل"
assert app.statement_range() == ("2026-09", "")                              # من شهر ٩ بلا نهاية
stmt = body("build_account_statement_tab")
assert "self.kh_from_month = self.make_month_combo(" in stmt and "self.kh_to_month = self.make_month_combo(" in stmt
assert "CTkEntry" not in stmt and "YYYY-MM" not in stmt and "self.refresh_account_statement" in stmt
for fn in ("refresh_account_statement", "print_account_statement"):
    assert "from_m, to_m = self.statement_range()" in body(fn) and "kh_from_month.get()" not in body(fn), fn
assert "kh_from_month.insert(" not in src and "kh_from_month.delete(" not in src
print("✔ كشف الحساب: «من شهر/إلى شهر» قائمتان («الكل» ثم الفترات) — الاختيار يحدّث الكشف، و«الكل» بلا حدّ، "
      "والشاشات تفتحه بنطاقها")

print("\n✅ صناديق المصنع: شهر أو من شهر إلى شهر أو «الكل» — بالاختيار لا بالكتابة، وبالمعادلات نفسها")
