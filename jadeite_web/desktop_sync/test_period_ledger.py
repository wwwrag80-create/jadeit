# -*- coding: utf-8 -*-
"""
اختبار سلوكي: دفتر الخزينة الموحّد للفترات.

يشغّل الدوال الحقيقية من البرنامج (لا نسخاً منها) على بيانات فترتين، ويثبت:
  • كل حركة تنتمي لفترتها (عمود period) أياً كان تاريخها
  • رصيد أول فترة ٩ = رصيد نهاية فترة ٨ بالضبط (ترحيل تلقائي)
  • التقرير الشهري يعطي الأرقام نفسها سواء فُتح من فترة ٨ أو ٩  ← خطأ العميل
  • رصيد نهاية الفترة في التقرير = شريط الخزينة = آخر رصيد في كشف حسابها
  • إقفال خياس فترة ٨ لا يغيّر رصيد افتتاح فترة ٩
  • الإقفال القديم (أرشفة) والجديد (قيد) يعطيان الرصيد نفسه
"""
import ast, calendar, datetime, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
lines = src.split("\n")
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def method_src(name):
    """نص الدالة كاملاً مع مزخرفاتها (@staticmethod/@classmethod)"""
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))


def class_attr_src(name):
    node = next(m for m in cls.body if isinstance(m, ast.Assign)
                and any(getattr(t, "id", None) == name for t in m.targets))
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


REAL = ["inv_period", "inv_in_period", "get_treasury_type_sets", "treasury_bucket",
        "treasury_effect", "get_workers_khayas", "treasury_period_components",
        "get_treasury_ledger", "get_opening_treasury_balance", "get_monthly_report_rows",
        "calculate_single_ledger", "get_actual_section_khayas", "get_all_stage_categories",
        "get_stage_config", "get_display_label", "get_box_account_name", "get_box_closed_total",
        "period_closing_datetime", "get_account_ledger_rows", "_account_ledger_rows_all",
        "_post_closing_entry", "recalculate_all"]

body = "\n".join(class_attr_src(a) for a in ("BOX_DISPLAY_OVERRIDES", "MADIN_DAEN_ACCOUNTS"))
body += "\n" + "\n".join(method_src(m) for m in REAL)
# ما يمسّ الواجهة فقط يُستبدل ببدائل صامتة — الحساب كله حقيقي
body += textwrap.dedent('''
    cloud_sync = None
    def get_total_gold_balance(self): return 0.0
    def refresh_screen_info_bar(self): pass
    def get_material_balance(self, m): return 0.0
    def get_stage_totals_for_month(self, cat, month): return 0.0, 0.0
    def mark_all_screens_dirty(self): pass
    def refresh_visible_screen(self): pass
    def save_invoice_to_db(self, i, inv): return True
    def get_smart_default_date(self): return "2026-09-15"
''')

ns = {"calendar": calendar, "datetime": datetime}
exec("\n".join(module_src(n) for n in ("en", "ALLOWANCE_8", "ALLOWANCE_4", "COUNTED_STATUSES")), ns)
exec("class App:\n" + textwrap.indent(body, "    "), ns)

P8, P9 = "2026-08", "2026-09"
_n = [0]


def op(period, t, w, name="المصنع", date=None, st="ACTIVE", **extra):
    _n[0] += 1
    inv = {"رقم الفاتورة": _n[0], "التاريخ": date or f"{period}-10 10:00:00", "الاسم": name,
           "النوع": t, "الوزن": w, "البيان": extra.pop("note", ""), "settled_status": st,
           "trees_count": extra.pop("trees", 0.0), "قبل": 0.0, "بعد": 0.0,
           "set_number": "", "row_number": "", "period": period}
    inv.update(extra)
    return inv


def build():
    app = ns["App"]()
    app.categories = {"المصنعين": ["عامل أ"], "المركبين": ["مركب ب"],
                      "أقسام_خياس_إضافية": [], "الموردين": []}
    invs = [
        # ═══ فترة ٨ ═══
        op(P8, "وارد ذهب (عيار 18)", 1000.0, trees=1.0, note="قيد افتتاحي"),   # قيد افتتاحي
        op(P8, "وارد ذهب (عيار 18)", 200.0),
        op(P8, "مبيعات ذهب", 150.0, name="عميل"),
        op(P8, "صادر ذهب", 30.0),
        # سُجّلت وأنت على فترة ٨ لكن تاريخها في شهر ٩ ← تنتمي لفترة ٨
        op(P8, "مبيعات ذهب", 20.0, name="عميل", date="2026-09-02 09:00:00"),
        op(P8, "صرف كاستنج", 40.0, name="الكاستنج"),
        op(P8, "قبض كاستنج", 25.0, name="الكاستنج"),
        op(P8, "وارد ذهب (عيار 18)", 5.0, name="مسترجع كاستنج"),              # يعود للصندوق مرة واحدة
        op(P8, "صرف ذهب", 100.0, name="عامل أ"),
        op(P8, "قبض ذهب", 90.0, name="عامل أ"),                                  # خياس فعلي ١٠
        op(P8, "قيد يومي مدين", 3.0, name="حساب الخزينة"),
        op(P8, "خياس طقوم", 7.0, name="خياس الطقوم", st="MEMO"),                # معلوماتي: لا أثر
        op(P8, "مبيعات ذهب", 999.0, name="عميل", st="SETTLED"),                 # ملغاة: لا أثر
        # ═══ فترة ٩ ═══
        op(P9, "وارد ذهب (عيار 18)", 50.0),
        op(P9, "مبيعات ذهب", 10.0, name="عميل"),
        op(P9, "صرف ذهب", 30.0, name="مركب ب"),
        op(P9, "قبض ذهب", 25.0, name="مركب ب"),                                  # خياس فعلي ٥
    ]
    app.invoices = {i["رقم الفاتورة"]: i for i in invs}
    app.invoice_counter = max(app.invoices)
    app.current_display_month = P8
    return app


def bar(app, month):
    app.current_display_month = month
    app.recalculate_all()
    return app.current_treasury_balance


def final_balance(app, account, from_m="", to_m=""):
    rows = app.get_account_ledger_rows(account, from_m, to_m)
    md = account in app.MADIN_DAEN_ACCOUNTS
    return round(sum((r["مدين"] - r["دائن"]) if md else (r["دائن"] - r["مدين"]) for r in rows), 2), rows


# ═══ ١) دفتر الفترات والترحيل ═══
app = build()
led = {r["period"]: r for r in app.get_treasury_ledger()}
# فترة ٨: 1000 افتتاحي + 200 وارد − 200 مبيعات/صادر − 10 صناديق − 10 خياس عمال + 3 قيد
assert led[P8]["closing"] == 983.0, led[P8]
assert led[P8]["sales"] == -200.0 and led[P8]["boxes"] == -10.0 and led[P8]["workers"] == -10.0
print("✔ فترة ٨ = 1000 + 200 − 200 − 10 (صناديق) − 10 (خياس عمال) + 3 (قيد) = 983")
assert led[P9]["carry"] == led[P8]["closing"]
assert led[P9]["closing"] == 1018.0, led[P9]
print("✔ فترة ٩ تبدأ تلقائياً بـ 983 (نهاية ٨) وتنتهي بـ 1018")
assert app.get_opening_treasury_balance(P8) == 0.0
assert app.get_opening_treasury_balance(P9) == 983.0
print("✔ رصيد أول المدة لفترة ٩ = رصيد نهاية فترة ٨ بالضبط")

# ═══ ٢) التقرير الشهري لا يتغيّر بتغيير الفترة المعروضة ═══
app.current_display_month = P8
rep8 = [r for r in app.get_monthly_report_rows() if r["period"] in (P8, P9)]
app.current_display_month = P9
rep9 = [r for r in app.get_monthly_report_rows() if r["period"] in (P8, P9)]
assert rep8 == rep9, (rep8, rep9)
print("✔ التقرير الشهري بالأرقام نفسها من فترة ٨ ومن فترة ٩  ← الخطأ المُبلَّغ عنه")
for r in rep8:
    assert round(r["start"] - r["sales"] - r["khayas"] + r["inbound"] + r["journal"], 2) == r["end"], r
assert rep8[1]["start"] == rep8[0]["end"]
print("✔ كل صف: البداية − المبيعات − الخياس + الوارد ± القيود = النهاية، وبداية ٩ = نهاية ٨")
r8 = rep8[0]
assert (r8["start"], r8["sales"], r8["khayas"], r8["inbound"], r8["journal"]) == (1000.0, 200.0, 20.0, 200.0, 3.0), r8
print("✔ الذهب المسترجع يُحتسب مرة واحدة (لا وارداً وخصماً من الخياس معاً)")

# ═══ ٣) الشريط = نهاية الفترة في التقرير ═══
assert bar(app, P8) == r8["end"] == 983.0
assert bar(app, P9) == rep8[1]["end"] == 1018.0
print("✔ شريط الخزينة = رصيد نهاية الفترة في التقرير (فترة ٨ وفترة ٩)")

# ═══ ٤) كشف حساب الخزينة بالفترة ═══
b_all, _ = final_balance(app, "حساب الخزينة")
b8, rows8 = final_balance(app, "حساب الخزينة", P8, P8)
b9, rows9 = final_balance(app, "حساب الخزينة", P9, P9)
assert b_all == 1018.0 and b8 == 983.0 and b9 == 1018.0, (b_all, b8, b9)
print("✔ آخر رصيد في كشف الخزينة = نهاية الفترة في التقرير = الشريط")
assert rows9[0].get("is_opening") and rows9[0]["مدين"] == 983.0
assert not any(r.get("is_opening") for r in app.get_account_ledger_rows("حساب الخزينة", "", ""))
print("✔ كشف فترة ٩ يبدأ بسطر «رصيد أول المدة» = 983")
late_sale = [r for r in rows8 if r["التاريخ"].startswith("2026-09-02")]
assert late_sale and late_sale[0]["period"] == P8
assert not any(r["التاريخ"].startswith("2026-09-02") for r in rows9)
print("✔ حركة تاريخها ٢٠٢٦-٠٩-٠٢ سُجّلت على فترة ٨ تظهر في كشف ٨ لا ٩")

b_sup, sup_rows = final_balance(app, "المصنع", P9, P9)
# المصنع في فترة ٨: وارد 1000 + 200 − صادر 30 = 1170 (دائن)، وفترة ٩: + 50
assert sup_rows[0].get("is_opening") and sup_rows[0]["دائن"] == 1170.0 and b_sup == 1220.0, (sup_rows[0], b_sup)
assert final_balance(app, "المصنع")[0] == b_sup
print("✔ كشف المورد من فترة ٩ يبدأ برصيده المُرحَّل (1170) لا بالصفر، وينتهي برصيده الكامل")

# ═══ ٥) إقفال خياس فترة ٨ لا يغيّر شيئاً في الخزينة ═══
report_before = app.get_monthly_report_rows()
app.current_display_month = P9
app._post_closing_entry("صندوق خياس المصنعين", 10.0, "إقفال خياس فترة ٨",
                        app.period_closing_datetime(P8), period=P8)
assert app.get_box_closed_total("المصنعين", month=P8) == 10.0
assert app.get_opening_treasury_balance(P9) == 983.0
assert app.get_monthly_report_rows() == report_before
assert bar(app, P9) == 1018.0
print("✔ بعد إقفال خياس فترة ٨: افتتاح ٩ ما زال 983، والتقرير والشريط لم يتغيّرا")
print("  (كان يصبح 993 — يرتفع بقيمة المُقفل — فتختلف أرقام فترة ٩ عن نهاية ٨)")
wk = [r for r in app.get_account_ledger_rows("حساب الخزينة", P8, P8) if r["الاسم"] == "الخياس الفعلي - المصنعين"]
assert len(wk) == 1 and wk[0]["دائن"] == 10.0 and "أُقفل منه 10.00" in wk[0]["البيان"]
print("✔ كشف الخزينة يبقي سطر الخياس كاملاً ويذكر أن ١٠ منه أُقفل لحساب الخسائر")

# ═══ ٦) الإقفال القديم بالأرشفة يعطي الرصيد نفسه ═══
legacy = build()
for inv in legacy.invoices.values():
    if inv["الاسم"] == "عامل أ":
        inv["settled_status"] = "SETTLED"
legacy.invoices[999] = op(P8, "صرف خياس مقفل", 10.0, name="الخياس الفعلي لقسم (المصنعين)")
lled = {r["period"]: r for r in legacy.get_treasury_ledger()}
assert lled[P8]["closing"] == 983.0 and lled[P8]["workers"] == 0.0 and lled[P8]["closed"] == -10.0
print("✔ الإقفال القديم (أرشفة + صرف خياس مقفل) يعطي نهاية ٨ = 983 أيضاً — بلا خصم مزدوج")

# ═══ ٧) عزل الفترات في الشريط ═══
app = build()
app.invoices[500] = op(P9, "قيد يومي دائن", 4.0, name="حساب الخزينة")
assert bar(app, P8) == 983.0, "قيد فترة ٩ على الخزينة تسرّب إلى شريط فترة ٨"
assert bar(app, P9) == 1014.0
print("✔ قيد يومي على الخزينة في فترة ٩ لا يمسّ شريط فترة ٨")
app.invoices[501] = op(P9, "رصيد افتتاحي", 100.0)
assert bar(app, P9) == 1114.0
print("✔ «رصيد افتتاحي» يُضاف للرصيد ولا يمحو ما رُحّل قبله")

print("\n✅ دفتر الفترات موحّد: التقرير والشريط وكشف الحساب ورصيد أول المدة رقم واحد")
