# -*- coding: utf-8 -*-
"""
اختبار الدفعة الرابعة — يشغّل الدوال الحقيقية من البرنامج:

  • شاشة الخسائر: لكل صندوق الخياس الحالي والفاقد والمسترجع والصافي
  • الوارد: خانة «إلى حساب» تسجّل القبض مسترجعاً لصندوق خياس (والمصدر في البيان)
  • مسترجع المصنعين والمركبين يُخصم من خياسهما الحالي ومن المتبقّي للإقفال
  • حساب «رصيد افتتاحي» في شجرة الحسابات والقيود اليومية
  • البيان المكتوب يظهر في جداول مراحل التصنيع (المصنعون ومسترجع الأشجار)
  • أقرب الأسماء أثناء الكتابة
  • المبيعات: الماس بعد الأحجار، وآخر نسبة خصم تُحفظ ولو كُتبت يدوياً
  • المدير يفتح على فترة عمل العميل
  • الشاشات الصغيرة: الواجهة تتصغّر لتتسع كاملة، والنافذة بحجم الشاشة حتى لو فقدت تكبيرها
"""
import ast, io, sys, textwrap, types

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
lines = src.split("\n")
tree = ast.parse(src)


def get_class(name):
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)


APP = get_class("GoldSystemApp")


def method_src(name, cls=APP):
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))


def attr_src(name, cls=APP):
    node = next(m for m in cls.body if isinstance(m, ast.Assign)
                and any(getattr(t, "id", None) == name for t in m.targets))
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def build(methods, attrs=(), extra="", ns=None):
    body = "\n".join(textwrap.indent(attr_src(a), "    ") for a in attrs)
    body += "\n" + "\n".join(textwrap.indent(method_src(m), "    ") for m in methods)
    ns = {} if ns is None else ns
    exec("class App:\n" + body + "\n" + textwrap.indent(textwrap.dedent(extra), "    "), ns)
    return ns["App"]


seg = method_src
M8, M9 = "2026-08", "2026-09"


def inv(no, name, t, w, period, note="", row=""):
    return {"رقم الفاتورة": no, "التاريخ": f"{period}-10 10:00:00", "الاسم": name, "النوع": t,
            "الوزن": w, "البيان": note, "settled_status": "ACTIVE", "trees_count": 0.0,
            "row_number": row, "set_number": "", "period": period}


BOX_METHODS = ["get_box_loss_summary", "get_box_closed_total", "get_box_recovered_total",
               "get_box_recovery_name", "get_stage_config", "get_display_label", "get_box_account_name",
               "get_current_unclosed_khayas", "get_box_khayas_cumulative", "invoices_by_name",
               "invoices_by_period", "period_invoices", "inv_period", "inv_in_period",
               "get_khayas_box_categories", "get_all_mustarja_names", "get_all_stage_categories"]
BOX_EXTRA = """
def get_actual_section_khayas(self, cat, target_month=None, **k):
    return self._live.get((cat, target_month), 0.0)
def get_sales_ops_khayas_total(self, month=None):
    return 0.0
"""


def new_box_app():
    App = build(BOX_METHODS, attrs=("BOX_DISPLAY_OVERRIDES", "RECOVERY_IN_TYPES"), extra=BOX_EXTRA)
    app = App()
    app.categories = {"المصنعين": [], "المركبين": [], "أقسام_خياس_إضافية": []}
    app.current_display_month = M9
    app.invoice_counter = 0
    app._live = {}
    return app


# ═══ ١) شاشة الخسائر: الأقسام الأربعة ═══
app = new_box_app()
app.invoices = {
    1: inv(1, "كاستنج", "صرف كاستنج", 100.0, M8),
    2: inv(2, "كاستنج", "قبض كاستنج", 90.0, M8),
    # إقفال خياس فترة ٨ (١٠ جم) لحساب الخسائر
    3: inv(3, "حساب الخسائر", "قيد يومي مدين", 10.0, M8, "إقفال"),
    4: inv(4, "الكاستنج", "قيد يومي دائن", 10.0, M8, "إقفال"),
    # فترة ٩: مسترجع ٣ جم من الكاستنج بعد الإقفال، وقيد التصفير التلقائي المعاكس
    5: inv(5, "مسترجع كاستنج", "وارد ذهب (عيار 18)", 3.0, M9, "من المصنع"),
    6: inv(6, "الكاستنج", "قيد يومي مدين", 3.0, M9, "مسترجع"),
    7: inv(7, "حساب الخسائر", "قيد يومي دائن", 3.0, M9, "مسترجع"),
}
sm = app.get_box_loss_summary("الكاستنج", month=M9)
assert sm == {"current": 0.0, "loss": 10.0, "recovered": 3.0, "net": 7.0}, sm
print("✔ الكاستنج: أُقفل ١٠ ثم استُرجع ٣ ← الحالي ٠، فاقد الكاستنج ١٠، المسترجع ٣، الصافي ٧")

# المسترجع قبل الإقفال (خصمه من الخياس ثم إقفال الباقي): النتيجة نفسها
app = new_box_app()
app.invoices = {
    1: inv(1, "كاستنج", "صرف كاستنج", 100.0, M9),
    2: inv(2, "كاستنج", "قبض كاستنج", 90.0, M9),
    3: inv(3, "مسترجع كاستنج", "وارد ذهب (عيار 18)", 3.0, M9, row="5"),
}
assert app.get_box_loss_summary("الكاستنج", month=M9)["current"] == 7.0
app.invoices[4] = inv(4, "حساب الخسائر", "قيد يومي مدين", 7.0, M9)
app.invoices[5] = inv(5, "الكاستنج", "قيد يومي دائن", 7.0, M9)
app.invoice_counter = 5
sm = app.get_box_loss_summary("الكاستنج", month=M9)
assert sm == {"current": 0.0, "loss": 10.0, "recovered": 3.0, "net": 7.0}, sm
print("✔ المسترجع قبل الإقفال (مسترجع الأشجار): النتيجة نفسها — الفاقد ١٠ والصافي ٧")
assert sm["net"] == round(sm["loss"] - sm["recovered"], 2)
print("✔ الصافي = الفاقد − المسترجع = ما وصل حساب الخسائر فعلاً (لا يُخصم المسترجع مرتين)")

# كل الصناديق لها مسترجع، والمصنعون والمركبون أيضاً
cats = app.get_khayas_box_categories()
assert cats[:3] == ["الكاستنج", "المصنعين", "المركبين"] and "خياس الطقوم" in cats
names = app.get_all_mustarja_names()
for n in ("مسترجع كاستنج", "مسترجع المصنعين", "مسترجع المركبين", "مسترجع خياس الطقوم"):
    assert n in names, n
print("✔ لكل صندوق حساب مسترجع — بما فيها المصنعون والمركبون")

# مسترجع المصنعين يُخصم من خياسهم الحالي
app = new_box_app()
app._live = {("المصنعين", M9): 12.0}
app.invoices = {1: inv(1, "مسترجع المصنعين", "وارد ذهب (عيار 18)", 2.5, M9)}
assert app.get_current_unclosed_khayas("المصنعين", month=M9) == 9.5
sm = app.get_box_loss_summary("المصنعين", month=M9)
assert sm["recovered"] == 2.5 and sm["current"] == 9.5, sm
print("✔ مسترجع المصنعين (٢٫٥) يُخصم من خياسهم الحالي (١٢ ← ٩٫٥)")
close = seg("close_split_khayas_box")
assert "remaining = round(total_k - already_closed - recovered, 2)" in close
print("✔ وإقفال خياسهم يُقفل المتبقّي بعد المسترجع فقط")

# البطاقات
cards = seg("refresh_losses_cards")
for key in ('"current"', '"loss"', '"recovered"', '"net"'):
    assert key in cards, key
assert 'f"فاقد {display_name}"' in cards and 'f"مسترجع {display_name}"' in cards
assert "self.get_box_loss_summary(cat, month=month)" in seg("refresh_losses_tab")
assert "get_khayas_box_categories()" in cards
print("✔ لوحة كل صندوق: الخياس الحالي، فاقد الصندوق، مسترجع الصندوق، الصافي")

# ═══ ٢) الوارد: «إلى حساب» ═══
msgs = []


class FakeBox:
    @staticmethod
    def askyesno(title, *a, **k):
        msgs.append(title)
        return title != "طباعة"

    @staticmethod
    def showinfo(*a, **k):
        pass

    showwarning = showerror = showinfo


class W:
    def __init__(self, v=""):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v

    def delete(self, *a):
        self.v = ""

    def insert(self, _i, v):
        self.v = str(v) + self.v

    def configure(self, **k):
        pass

    def focus(self):
        pass


ns_in = {"messagebox": FakeBox, "datetime": __import__("datetime")}
App = build(BOX_METHODS + ["submit_inbound", "get_inbound_account_options"],
            attrs=("BOX_DISPLAY_OVERRIDES", "RECOVERY_IN_TYPES", "INBOUND_DEFAULT_ACCOUNT"),
            extra=BOX_EXTRA + """
def check_name_exists(self, n): return any(n in v for v in self.categories.values())
def save_name_to_db(self, *a): pass
def save_invoice_to_db(self, i, d):
    self._inv_version = getattr(self, "_inv_version", 0) + 1
    return True
def register_operation_period(self, d): pass
def recalculate_all(self): pass
def get_supplier_name_values(self): return ["المصنع"]
""", ns=ns_in)
a = App()
a.categories = {"المصنعين": [], "المركبين": [], "الموردين": [], "أقسام_خياس_إضافية": []}
a.current_display_month, a.invoice_counter, a._live = M9, 0, {}
a.invoices = {1: inv(1, "كاستنج", "صرف كاستنج", 20.0, M9), 2: inv(2, "كاستنج", "قبض كاستنج", 15.0, M9)}
a.invoice_counter = 2
opts = a.get_inbound_account_options()
assert opts[0] == "الخزينة (وارد عادي)" and "مسترجع كاستنج" in opts and "مسترجع المصنعين" in opts
a.in_date, a.in_invoice_num, a.in_supplier = W(f"{M9}-12"), W("V-7"), W("المصنع")
a.in_type, a.in_weight, a.in_carat, a.in_note = W("ذهب"), W("2"), W("18"), W("")
a.in_to_account = W("مسترجع كاستنج")
a.submit_inbound()
rec = [i for i in a.invoices.values() if i["النوع"] == "وارد ذهب (عيار 18)"]
assert len(rec) == 1 and rec[0]["الاسم"] == "مسترجع كاستنج" and rec[0]["البيان"] == "من المصنع", rec
assert a.in_to_account.get() == "الخزينة (وارد عادي)"
print("✔ قبض من المصنع «إلى حساب: مسترجع كاستنج» ← يُسجَّل مسترجعاً للكاستنج، و«من المصنع» في البيان")
sm = a.get_box_loss_summary("الكاستنج", month=M9)
assert sm["recovered"] == 2.0 and sm["current"] == 0.0, sm
print(f"✔ ويظهر في شاشة الخسائر: مسترجع الكاستنج {sm['recovered']}، والباقي (٣) أُقفل للخسائر فالحالي صفر")
assert "before=self.lbl_in_type" in seg("toggle_in_carat_field")
print("✔ خانة العيار تعود لمكانها قبل نوع الوارد (لا بعد «إلى حساب»)")

# ═══ ٣) رصيد افتتاحي ═══
assert attr_src("OPENING_ACCOUNT").endswith('"رصيد افتتاحي"')
assert "self.OPENING_ACCOUNT" in seg("get_account_statement_options")
assert "self.get_account_statement_options()" in seg("get_journal_entry_account_options")
coa = seg("refresh_chart_of_accounts")
assert "add_leaf(g_opening, self.OPENING_ACCOUNT)" in coa and "self.OPENING_ACCOUNT}" in coa
print("✔ حساب «رصيد افتتاحي» في شجرة الحسابات وفي خانتي القيد اليومي (مدين/دائن)")
tb = seg("treasury_bucket")
assert 'if t == "رصيد افتتاحي":' in tb
print("✔ وهو حساب قيود: لا يمسّ الخزينة إلا إن كان الطرف الآخر «حساب الخزينة»")

# ═══ ٤) البيان في جداول مراحل التصنيع ═══
uni = seg("submit_unified_op")
assert 'current_note = " — ".join(x for x in (type_label, note) if x)' in uni
print("✔ المصنعون/المركبون: البيان المكتوب يُحفظ مع الحركة ويظهر في عمود البيان")
led = seg("open_worker_ledger_window")
assert 'head = note_str.split(" — ")[0].strip()' in led
print("✔ ونوع القبض (زركون/أحجار…) يبقى في أول البيان فيُصنَّف به القبض صحيحاً")

S = build(["collect_stage_ops_rows", "is_row_recovery", "period_invoices", "invoices_by_period",
           "inv_period", "row_sort_key"], attrs=("INBOUND_TYPES",))
st = S()
st.current_display_month, st.invoice_counter = M9, 0
st.invoices = {1: inv(1, "كاستنج", "صرف كاستنج", 10.0, M9, "شجرة ذهب أبيض", "5"),
               2: inv(2, "مسترجع كاستنج", "وارد ذهب (عيار 18)", 1.0, M9, "مسترجع الأشجار — من الغبار", "5")}
rows = st.collect_stage_ops_rows("صرف كاستنج", "قبض كاستنج", "مسترجع كاستنج")
assert rows[0][2]["البيان"] == "شجرة ذهب أبيض | من الغبار", rows[0][2]["البيان"]
print("✔ الكاستنج: بيان الصرف وبيان مسترجع الأشجار يظهران معاً في عمود البيان")

# ═══ ٥) أقرب الأسماء ═══
R = build(["rank_name_matches", "normalize_name_for_match", "clean_name"], attrs=("_AR_FOLD",),
          ns={"re": __import__("re"), "difflib": __import__("difflib")})
r = R()
names = ["أحمد علي", "محمد سالم", "إبراهيم خالد", "أحمد", "سالم عيسى", "فاطمة"]
assert r.rank_name_matches("احمد", names)[:2] == ["أحمد", "أحمد علي"]
assert r.rank_name_matches("سالم", names)[:2] == ["سالم عيسى", "محمد سالم"]
assert r.rank_name_matches("ابراهيم", names)[0] == "إبراهيم خالد"
assert r.rank_name_matches("فاطمه", names)[0] == "فاطمة"
assert r.rank_name_matches("محمد سلم", names)[0] == "محمد سالم"
assert "خالد" not in " ".join(r.rank_name_matches("زيد", names))
print("✔ أقرب الأسماء: يبدأ به ← كلمة تبدأ به ← يحتويه ← قريب الكتابة (أ/ا، ة/ه، حرف ناقص)")
ac = seg("bind_name_autocomplete")
assert "on_pick" in ac and '"<Down>"' in ac and "return None          # يكمل Enter" in ac
assert "combo_op_name" in seg("build_mfg_ui") and "on_pick=self.render_unified_fields" in seg("build_mfg_ui")
print("✔ القائمة تظهر أثناء الكتابة في كل خانات الأسماء، واسم المصنع/المركب المختار يعرض خاناته")

# ═══ ٦) المبيعات ═══
fields = [k for _l, k in ast.literal_eval(attr_src("SALE_EDIT_FIELDS").split("=", 1)[1].strip())]
assert fields.index("الماس") == fields.index("أحجار") + 1
sales = seg("build_sales_tab")
assert '"الأحجار", "الماس", "الأحجار بعد الخصم"' in sales
assert "self.sale_stones, self.sale_diamond, self.sale_stones_discount" in sales
assert '"الأحجار", "الماس",' in seg("refresh_pending_sales_table")
print("✔ الماس بعد الأحجار مباشرة: في خانات الإدخال والتنقّل بـEnter والجدول ونافذة التعديل")

settings = {}
D = build(["remember_discount_pct"], extra="""
def get_last_discount_percentage(self): return settings.get("last", "30")
def set_last_discount_percentage(self, v): settings["last"] = v
""", ns={"settings": settings})
d = D()
d.sale_discount_pct = W("25%")
d.remember_discount_pct()
assert settings["last"] == "25"
d.sale_discount_pct = W("abc")
d.remember_discount_pct()
assert settings["last"] == "25"
assert "self.remember_discount_pct()" in seg("stage_sale_row")
print("✔ آخر نسبة خصم تُحفظ تلقائياً ولو كُتبت يدوياً (والنص غير الرقمي يُتجاهل)")

# ═══ ٧) المدير يفتح على فترة عمل العميل ═══
for admin, saved, expect in ((True, "2026-08", "2026-08"), (True, "", M9), (False, "2026-08", M9)):
    store = {"client_working_period": saved}
    P = build(["sync_working_period", "_remember_working_period"], attrs=("WORKING_PERIOD_KEY",),
              extra="""
def get_setting(self, k, d=None): return store.get(k, d)
def set_setting(self, k, v): store[k] = v
""", ns={"IS_ADMIN_BUILD": admin, "re": __import__("re"), "store": store})
    p = P()
    p.client_id, p.current_display_month = "C1", M9
    p.sync_working_period()
    assert p.current_display_month == expect, (admin, saved, p.current_display_month)
    if not admin:
        assert store["client_working_period"] == M9
print("✔ فترة عمل العميل تُحفظ عنده وتصل المدير، فيفتح برنامج المدير على الفترة نفسها")
assert "self._remember_working_period(selected_period)" in seg("on_period_changed")

# ═══ ٨) الشاشات الصغيرة ═══
class Tracker:
    dpi = 1.0
    widget_scaling = 1.0

    @classmethod
    def get_window_scaling(cls, _w):
        return cls.dpi


nsf = {"ctk": types.SimpleNamespace(ScalingTracker=Tracker),
       "screen_work_area": lambda w: (0, 0, w[0], w[1] - 48)}
exec(module_src("DESIGN_WORK_AREA") + "\n" + module_src("MIN_UI_FIT") + "\n" + module_src("screen_fit_factor"), nsf)
fit = nsf["screen_fit_factor"]
for (sw, sh, dpi), lo, hi in (((1920, 1080, 1.0), 1.0, 1.0), ((1920, 1080, 1.5), 1.0, 1.0),
                              ((1366, 768, 1.0), 1.0, 1.0), ((1366, 768, 1.25), 0.8, 0.9),
                              ((1366, 768, 1.5), 0.7, 0.72), ((1366, 768, 2.0), 0.7, 0.7)):
    Tracker.dpi = dpi
    f = fit((sw, sh))
    assert lo <= f <= hi, (sw, sh, dpi, f)
    print(f"✔ شاشة {sw}×{sh} بتكبير {int(dpi * 100)}٪ ← الواجهة {int(f * 100)}٪ من حجمها")
login = seg("__init__", get_class("LoginWindow"))
assert "max(self.winfo_screenheight(), 240)" in login and "apply_screen_fit(self)" in login
assert "get_widget_scaling" in login
print("✔ شاشة الدخول بحجم الشاشة الفعلي (كان زر «دخول» يقع تحت حافة الشاشات القصيرة)")
init = seg("__init__")
assert init.index("apply_screen_fit(self)") < init.index("self.create_layout()")
assert init.index("fill_work_area(self)") < init.index("self.force_maximize()")
assert "fill_work_area(self)" in seg("__init__", get_class("AdminPanel"))
print("✔ الحجم العادي للنافذة = الشاشة كاملة قبل التكبير: لو فقدت تكبيرها تبقى تملأ الشاشة (لا نصفها)")

# ═══ ٩) الكاستنج: عمود الاسم، والكشف كاملاً أو لاسم واحد ═══
F = build(["get_cast_name_filter"], extra="""
def clean_name(self, n): return (n or "").replace("\\u200f", "").strip()
def get_stage_name_values(self, d, c): return ["\\u200fكاستنج", "\\u200fعامل 1", "\\u200fعامل 2"]
def invoices_by_name(self): return {"اسم قديم": [{"النوع": "صرف كاستنج"}]}
""")
f = F()
for typed, expect in (("", None), ("   ", None), ("\u200fعامل 1", "عامل 1"), ("عامل 2", "عامل 2"),
                      ("اسم جديد", None), ("اسم قديم", "اسم قديم")):
    f.cast_name = W(typed)
    assert f.get_cast_name_filter() == expect, (typed, f.get_cast_name_filter())
print("✔ خانة الاسم فارغة ← كل الأسماء؛ اسم مختار ← حركته وحدها؛ اسم جديد بلا حركات ← الكشف كاملاً")
rc = seg("refresh_casting_table")
assert "show_name=True, name_filter=name_filter" in rc and "self._cast_filter_shown = name_filter" in rc
assert "كل الأسماء" in rc
rs = seg("render_stage_ops_table")
assert "rows = [r for r in rows if r[1] == name_filter]" in rs
assert "on_name_change=self.on_cast_name_change" in seg("build_casting_ui")
panel = seg("build_stage_panel")
assert "command=(lambda _v: on_name_change())" in panel and "on_pick=(lambda _v: on_name_change())" in panel
assert 'ent.bind("<KeyRelease>", on_typed)' in panel
print("✔ الكاستنج: عمود الاسم في الجدول، والاختيار أو المسح يحدّث الكشف وإجمالياته فوراً")

print("\n✅ الدفعة الرابعة سليمة")
