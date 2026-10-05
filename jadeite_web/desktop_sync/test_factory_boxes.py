# -*- coding: utf-8 -*-
"""
صناديق المصنع (الدفعة ٢٥): اختيار الشهر يعرض أرقامه وحده، و«الكل» يعرض كل الأشهر —
بالمعادلات نفسها التي كانت (تُقارن هنا بنسخة حرفية من الحساب القديم «من شهر/إلى شهر»).
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
    "LOSSES_ALL", "inv_period", "get_recorded_periods", "factory_period_options", "selected_factory_period",
    "factory_period_label", "factory_boxes_totals")), ns)
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

# ═══ ٣) القائمة والاختيار ═══
assert app.factory_period_options() == ["الكل", "2026-09", "2026-08", "2026-07"]


class Combo:
    def __init__(self, v): self.v = v
    def get(self): return self.v


app.combo_factory_period = Combo("الكل")
assert app.selected_factory_period() == "الكل" and app.factory_period_label("الكل") == "أرقام كل الأشهر"
app.combo_factory_period = Combo("2026-08")
assert app.selected_factory_period() == "2026-08" and app.factory_period_label("2026-08") == "أرقام شهر 2026-08"
print("✔ القائمة: «الكل» ثم الأشهر المسجّلة (الأحدث أولاً)، والسطر يذكر النطاق المعروض")

# ═══ ٤) الشاشة والطباعة والكشف بالاختيار نفسه ═══
build = body("build_factory_boxes_tab")
assert "self.combo_factory_period = ctk.CTkComboBox(" in build and "factory_from_month" not in src
assert 'state="readonly"' in build and "self.refresh_factory_boxes_table()" in build
ref = body("refresh_factory_boxes_table")
assert "self.factory_boxes_totals(month)" in ref and "self.selected_factory_period()" in ref
pr = body("print_factory_boxes_screen")
assert "self.factory_boxes_totals(month)" in pr and "self.factory_period_label(month)" in pr
st = body("open_factory_box_statement")
assert "self.selected_factory_period()" in st and "kh_from_month" in st
print("✔ الشاشة والطباعة من الحساب نفسه وبالشهر نفسه، و«عرض كشف الحساب» بالشهر المختار («الكل» = كل الأشهر)")

print("\n✅ صناديق المصنع: شهر تختاره أو «الكل» — بالمعادلات نفسها")
