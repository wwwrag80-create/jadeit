# -*- coding: utf-8 -*-
"""
لوحة المؤشرات (الدفعة ١٦) — أرقامها من مصادر الشاشات نفسها، ورسومها بمواصفات موحّدة:

  • خط الخزينة = دفتر الخزينة لكل فترة، والمبيعات/الوارد/الخياس = مكوّنات الفترة (كالرئيسية والتقرير).
  • نسبة الفاقد لكل قسم = تقرير أداء العمال للفترة، والفاقد الحالي لكل صندوق = شاشة الخسائر.
  • بطاقة الطقوم المفتوحة = تقرير الطقوم المفتوحة، والمدى (٦/١٢/الكل) يقصّ الفترات من آخرها.
  • التدريج مقروء ويشمل الصفر، والأرقام الكبيرة مختصرة، ولونا السلسلتين مُتحقَّق منهما لعمى الألوان.
"""
import ast, io, math, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def body(name):
    return ast.get_source_segment(src, node(name))


def module_src(name):
    n = next(x for x in tree.body if (isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x.name == name)
             or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))
    return ast.get_source_segment(src, n)


ns = {"math": math}
for name in ("CHART_SERIES", "nice_ticks", "fmt_compact"):
    exec(module_src(name), ns)

# ═══ ١) التدريج والاختصار والألوان ═══
assert ns["nice_ticks"](0, 66702.75) == [0, 20000, 40000, 60000, 80000]
assert ns["nice_ticks"](-1308.87, 1500) == [-2000, -1000, 0, 1000, 2000]
assert ns["nice_ticks"](3, 3) [0] == 0 and ns["nice_ticks"](5, 5)[-1] >= 5
t = ns["nice_ticks"](120, 870)
assert t[0] == 0 and t[-1] >= 870 and len(t) <= 7
assert ns["fmt_compact"](66702.75) == "67K" and ns["fmt_compact"](2500) == "2,500" and ns["fmt_compact"](1_250_000) == "1.2M"
assert ns["fmt_compact"](372.63, 2) == "372.63" and ns["fmt_compact"](-1308.87, 2) == "-1,308.87"
assert ns["CHART_SERIES"] == {"light": ("#2A78D6", "#EB6834"), "dark": ("#3987E5", "#D95926")}
print("✔ التدريج نظيف ويشمل الصفر (0/20K/40K…)، والأرقام الكبيرة مختصرة، ولونا السلسلتين المُتحقَّق منهما "
      "(أزرق/برتقالي، مستقلّان لعمى الألوان في المظهرين)")

# ═══ ٢) أرقام اللوحة من مصادر الشاشات نفسها ═══
mns = {}
exec("class Base:\n" + "\n".join(textwrap.indent(textwrap.dedent(ast.get_source_segment(src, node(m))), "    ")
                                 for m in ("WORKER_SECTIONS", "DASH_SPANS", "dashboard_data")), mns)
PERIODS = ["2026-0%d" % m for m in range(1, 10)]


class App(mns["Base"]):
    current_display_month = "2026-09"
    current_treasury_balance = 950.0
    current_total_gold = 1010.0

    def get_treasury_ledger(self):
        return [{"period": p, "closing": 100.0 * (i + 1)} for i, p in enumerate(PERIODS)]

    def treasury_period_components(self, p):
        i = PERIODS.index(p) + 1
        return {"sales": -10.0 * i, "inbound": 20.0 * i, "boxes": -1.0, "workers": -0.5 * i, "closed": 0.0}

    def worker_performance_rows(self, sec, periods):
        return [], {"ratio": (2.0 if sec == "المصنعين" else 3.0) * int(periods[0][-1])}

    def open_jobs(self, today=None):
        return [{"issued": 5.0, "overdue": True}, {"issued": 7.5, "overdue": False}]

    def get_khayas_box_categories(self):
        return ["الكاستنج", "المصنعين", "التلميع"]

    def get_box_loss_summary(self, cat, month=None):
        return {"current": {"الكاستنج": 3.333, "المصنعين": -12.0, "التلميع": 0.0}[cat]}

    def get_display_label(self, cat):
        return "لـ" + cat


app = App()
d = app.dashboard_data(6)
assert d["periods"] == PERIODS[-6:] and d["treasury"] == [400.0, 500.0, 600.0, 700.0, 800.0, 900.0]
assert d["sales"][-1] == 90.0 and d["inbound"][-1] == 180.0 and d["khayas"][-1] == round(1.0 + 4.5, 2)
assert d["ratios"]["المصنعين"][-1] == 18.0 and d["ratios"]["المركبين"][0] == 12.0
assert d["boxes"] == [("لـالمصنعين", -12.0), ("لـالكاستنج", 3.33)], "الصندوق الصفري لا يظهر، والأكبر أولاً"
k = d["kpi"]
assert k["treasury"] == 950.0 and k["total"] == 1010.0 and k["prev_treasury"] == 800.0
assert k["sales"] == 90.0 and k["prev_sales"] == 80.0 and k["inbound"] == 180.0
assert k["open_jobs"] == 2 and k["overdue_jobs"] == 1 and k["open_gold"] == 12.5
assert k["ratio"] == {"المصنعين": 18.0, "المركبين": 27.0}
assert len(app.dashboard_data(None)["periods"]) == 9 and len(app.dashboard_data(12)["periods"]) == 9
print("✔ اللوحة: الخزينة من دفترها، والمبيعات والوارد والخياس من مكوّنات الفترة، والنسب من أداء العمال، "
      "والصناديق من شاشة الخسائر، والطقوم من تقريرها — والمقارنة بالفترة السابقة")

# ═══ ٣) الربط في البرنامج ═══
assert '("لوحة المؤشرات",   "🧭", "لوحة المؤشرات")' in src
assert 'self.tabview.add("لوحة المؤشرات")' in src and '"لوحة المؤشرات":    self.build_dashboard_tab' in src
assert '"لوحة المؤشرات": ("refresh_dashboard",)' in src and '"لوحة المؤشرات"]' in body("get_home_screens_default")
assert '"لوحة المؤشرات": "مؤشرات الإدارة' in src
build = body("build_dashboard_tab")
assert build.count("MiniChart(") == 1 and '"hbars"' in build and '"bars"' in build and '"line"' in build
assert "self.show_dashboard_table(k, t)" in build and "self.open_open_jobs_report" in build
assert "navigate_to_screen(\"لوحة المؤشرات\")" in body("build_home_screen")
mc = module_src("MiniChart")
assert "width=2" in mc and "min(24.0" in mc and 'tags="hover"' in mc and "لا توجد بيانات بعد" in mc
print("✔ شاشة «لوحة المؤشرات» مسجّلة (الشريط، البناء الكسول، التحديث، الرئيسية)، بأربعة رسوم ولوحة قيم عند المرور "
      "وزر «الأرقام» لكل رسم")

print("\n✅ لوحة المؤشرات سليمة")
