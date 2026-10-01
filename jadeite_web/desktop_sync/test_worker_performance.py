# -*- coding: utf-8 -*-
"""
تقرير أداء العمال (الدفعة ١٥) — من دالة البرنامج نفسها على دفاتر مضبوطة:

  • كل خلية من دفتر العامل نفسه: الإنتاج = «حجم الإنتاج»، والفاقد = −الخياس
    (ذهب/صافي − المرجع ٧٥٠)، والنسبة = الفاقد ÷ الإنتاج × ١٠٠٠.
  • الفترة بلا حركة لا تظهر، والإنتاج الصفري بلا نسبة (لا قسمة على صفر).
  • الاتجاه من آخر فترتين منتهيتين (الفترة الجارية لا تدخله)، والترتيب من الأعلى نسبةً.
  • إجمالي القسم = مجموع العمال، ونسبته من المجموعين لا متوسط النسب.
"""
import ast, io, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def body(name):
    return ast.get_source_segment(src, node(name))


ns = {}
exec("class Base:\n" + "\n".join(textwrap.indent(textwrap.dedent(ast.get_source_segment(src, node(m))), "    ")
                                 for m in ("TREND_STEP", "worker_performance_rows")), ns)

# دفاتر مضبوطة: (الإنتاج، الخياس) لكل عامل وفترة — الخياس سالب = فاقد عند العامل
LEDGERS = {
    ("أحمد", "2026-07"): (1000.0, -2.0),    # 2‰
    ("أحمد", "2026-08"): (500.0, -2.0),     # 4‰  ← يزداد
    ("أحمد", "2026-09"): (10.0, -9.0),      # جارية: 900‰ لا تدخل الاتجاه
    ("سالم", "2026-07"): (400.0, -2.0),     # 5‰
    ("سالم", "2026-08"): (1000.0, -3.0),    # 3‰  ← يتحسّن
    ("سالم", "2026-09"): (100.0, -50.0),    # جارية: 500‰ — لو دخلت الاتجاه لقلبته «يزداد»
    ("خالد", "2026-08"): (0.0, -1.5),       # بلا إنتاج: فاقد بلا نسبة
    ("مريم", "2026-07"): (1000.0, 0.30),    # زيادة لصالح العامل: −0.30‰
    ("مريم", "2026-08"): (1000.0, 0.34),    # −0.34‰ ← ثابت (فرق ٠٫٠٤ أقل من الخطوة)
}


class App(ns["Base"]):
    def __init__(self):
        self.categories = {"المصنعين": ["أحمد", "سالم", "خالد", "مريم", "بلا حركة"]}
        self.calls = []

    def calculate_single_ledger(self, name, cat, target_month=None):
        self.calls.append((name, cat, target_month))
        prod, khayas = LEDGERS.get((name, target_month), (0.0, 0.0))
        return {"حجم الإنتاج": prod, "الخياس": khayas}


app = App()
P = ["2026-07", "2026-08", "2026-09"]
rows, total = app.worker_performance_rows("المصنعين", P, open_period="2026-09")
by = {r["name"]: r for r in rows}
assert set(by) == {"أحمد", "سالم", "خالد", "مريم"}, "العامل بلا حركة في كل الفترات لا يظهر"
assert all(c[1] == "المصنعين" for c in app.calls)
a = by["أحمد"]
assert a["cells"] == {"2026-07": (1000.0, 2.0, 2.0), "2026-08": (500.0, 2.0, 4.0), "2026-09": (10.0, 9.0, 900.0)}
assert a["production"] == 1510.0 and a["loss"] == 13.0 and a["ratio"] == round(13 / 1510 * 1000, 2)
print("✔ الخلية من دفتر العامل: الإنتاج، والفاقد = −الخياس، والنسبة بالألف")

assert a["trend"] == "⬆️ يزداد", a["trend"]
assert by["سالم"]["trend"] == "⬇️ يتحسّن" and by["مريم"]["trend"] == "➖ ثابت" and by["خالد"]["trend"] == "—"
rows2, _t = app.worker_performance_rows("المصنعين", P, open_period=None)
assert {r["name"]: r for r in rows2}["سالم"]["trend"] == "⬆️ يزداد", "بلا فترة جارية تدخل كل الفترات"
rows3, _t = app.worker_performance_rows("المصنعين", ["2026-08", "2026-09"], open_period="2026-09")
assert {r["name"]: r for r in rows3}["أحمد"]["trend"] == "—", "فترة منتهية واحدة لا تكفي للاتجاه"
print("✔ الاتجاه من آخر فترتين منتهيتين (الجارية لا تدخله)، والفرق الصغير ثابت")

k = by["خالد"]
assert k["cells"] == {"2026-08": (0.0, 1.5, None)} and k["ratio"] is None
assert by["مريم"]["loss"] == -0.64 and by["مريم"]["ratio"] == -0.32
print("✔ إنتاج صفري بلا نسبة (لا قسمة على صفر)، والزيادة لصالح العامل نسبة سالبة")

assert [r["name"] for r in rows] == ["سالم", "أحمد", "مريم", "خالد"], [r["name"] for r in rows]
assert total["production"] == round(sum(r["production"] for r in rows), 2) == 5010.0
assert total["loss"] == round(sum(r["loss"] for r in rows), 2) == 68.86
assert total["ratio"] == round(68.86 / 5010 * 1000, 2)
print("✔ الأعلى نسبةً أولاً وبلا نسبة آخراً، وإجمالي القسم من المجموعين لا متوسط النسب")

win = body("open_worker_performance_report")
assert "self.worker_performance_rows(sec, periods, open_period=open_period)" in win
assert 'tags=("warn",) if warn else ()' in win and "self.print_generic_table_screen(" in win
assert "self.open_worker_performance_report(" in body("build_inquiries_tab")
print("✔ النافذة من شاشة صناديق الخياس: تمييز من فوق متوسط القسم، واختيار القسم والمدى، والطباعة")

print("\n✅ تقرير أداء العمال سليم")
