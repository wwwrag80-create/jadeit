# -*- coding: utf-8 -*-
"""
فتح فوري لأي شاشة (الدفعة ٣٣):

  ١) كل الشاشات تُجهَّز في أوقات الفراغ: تُبنى بعد الدخول، وتُحدَّث بعد كل تعديل بيانات،
     وتُرسم مسبقاً خارج حدود النافذة — فعند النقر تُعرض جاهزة بلا بناء ولا حساب ولا رسم.
     خطوة صغيرة كل مرة، ولا خطوة والمستخدم يكتب أو ينقر، والشاشة الظاهرة لا تُلمس.
  ٢) لا حساب مزدوج عند أول بناء: الباني الذي يملأ جداوله بنفسه لا تُعاد حساباته فوراً.
  ٣) الحسابات الثقيلة تقرأ من فهارس جاهزة (الاسم والفترة) بدل مسح كل الحركات —
     والنتائج مطابقة حرفياً للمسح الكامل (المعادلات نفسها لم تتغيّر).
"""
import ast, io, random, re, sys, textwrap, time

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
router = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ScreenRouter")


def node(name, owner=cls):
    return next(x for x in owner.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def body(name, owner=cls):
    n = node(name, owner)
    start = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])
    return textwrap.dedent("\n".join(src.split("\n")[start - 1:n.end_lineno]))


def module_ns():
    """ثوابت المحاسبة ودالة الراجع من البرنامج نفسه"""
    ns = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper():
            try:
                exec(ast.get_source_segment(src, n), ns)       # الثوابت البسيطة وحدها
            except Exception:
                pass
        elif isinstance(n, ast.FunctionDef) and n.name == "raji_ayar":
            exec(ast.get_source_segment(src, n), ns)
    return ns


def build(members, ns=None):
    ns = dict(module_ns(), **(ns or {}))
    exec("class Base:\n" + "\n".join(textwrap.indent(body(m), "    ") for m in members), ns)
    return ns["Base"]


# ═══ ١) لا حساب مزدوج عند أول بناء ═══
builders = dict(re.findall(r'"([^"]+)":\s+self\.(build_\w+),',
                           src[src.index("self._screen_builders = {"):src.index("self._built_screens = set()")]))
seg = src[src.index("SCREEN_REFRESHERS = {"):]
refreshers = {k: re.findall(r'"(\w+)"', v) for k, v in
              re.findall(r'"([^"]+)":\s*\(([^)]*)\)', seg[:seg.index("}")])}
self_refresh = set(re.findall(r'"([^"]+)"', body("BUILDERS_REFRESH_SELF")))
funcs = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}


def self_calls(fn):
    return {n.func.attr for n in ast.walk(funcs[fn]) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"}


really = {name for name, b in builders.items() if set(refreshers.get(name, ())) <= self_calls(b)}
assert self_refresh == really, (self_refresh ^ really)
print(f"✔ {len(self_refresh)} شاشة يملأ بانيها جداولها بنفسه — لا تُحسب مرة ثانية فور بنائها "
      "(والبقية: الوارد، المبيعات، مراحل التصنيع، صناديق الخياس، كشف حساب تُحدَّث بعد البناء كما كانت)")

ens = body("ensure_screen_built")
assert "def ensure_screen_built(self, name, background=False):" in ens
assert "self.BUILDERS_REFRESH_SELF" in ens and "self._dirty_screens.discard(name)" in ens
assert re.search(r"if not background:\s+messagebox\.showerror", ens)
print("✔ البناء في الخلفية بلا مؤشّر انتظار ولا رسالة (الرسالة تظهر عند فتح الشاشة إن تعذّر بناؤها)")

# ═══ ٢) التجهيز في الخلفية: خطوة صغيرة كل مرة ═══
P = build(["WARM_FIRST", "WARM_STEP_MS", "_note_user_input", "warm_order", "screen_needs_warm",
           "warm_screens", "_prebuild_screens", "BUILDERS_REFRESH_SELF", "ensure_screen_built",
           "refresh_pending_screen", "refresh_screen", "SCREEN_REFRESHERS", "mark_all_screens_dirty"],
          {"time": time, "log_cloud_error": lambda *a: None, "messagebox": None})


class TV:
    def __init__(self): self.current_screen, self.mapped = None, False
    def winfo_ismapped(self): return self.mapped


class W(P):
    def __init__(self):
        self.log, self.jobs, self.cancelled = [], [], []
        self.tabview = TV()
        self.home_order = ["الحسابات", "الوارد", "المبيعات", "لوحة المؤشرات"]
        self._screen_builders = {n: (lambda n=n: self.log.append(("build", n))) for n in
                                 ("الحسابات", "الوارد", "المبيعات", "لوحة المؤشرات", "مراحل التصنيع")}
        self._screen_builders["مراحل التصنيع"] = lambda: 1 / 0          # بانٍ معطوب
        self._built_screens = set()
        self.size = (1380, 852)
        self._last_user_input = 0.0

    def get_home_screens_default(self): return list(self.home_order)
    def get_setting(self, *a): return None
    def bind_all(self, *a, **k): pass
    def configure(self, **k): self.log.append(("cursor", k.get("cursor")))
    def update_idletasks(self): pass
    def screen_area_size(self): return self.size

    def after(self, ms, fn):
        self.jobs.append((ms, fn))
        return f"job{len(self.jobs)}"

    def after_cancel(self, job): self.cancelled.append(job)

    def prerender_screen(self, name):
        self.log.append(("render", name))
        self._rendered_size = getattr(self, "_rendered_size", {})
        self._rendered_size[name] = self.size

    def refresh_dashboard(self): self.log.append(("refresh", "لوحة المؤشرات"))
    def refresh_inout_tables(self): self.log.append(("refresh", "الوارد"))
    def refresh_chart_of_accounts(self): self.log.append(("refresh", "الحسابات"))

    def run(self, limit=60):
        """يشغّل سلسلة التجهيز حتى تنتهي (كما تفعل الحلقة الرئيسية)"""
        n = 0
        while self.jobs and n < limit:
            _ms, fn = self.jobs.pop(0)
            fn()
            n += 1
        return n


w = W()
assert w.warm_order() == ["المبيعات", "مراحل التصنيع", "الحسابات", "الوارد", "لوحة المؤشرات"]
w.mark_all_screens_dirty()
w.warm_screens(delay=0)
w.run()
steps = [x for x in w.log if x[0] != "cursor"]
assert ("cursor", "watch") not in w.log, "التجهيز في الخلفية لا يغيّر مؤشّر الفأرة"
assert steps[:2] == [("build", "المبيعات"), ("refresh", "المبيعات")] or steps[0] == ("build", "المبيعات")
built_order = [n for k, n in steps if k == "build"]
assert built_order == ["المبيعات", "الحسابات", "الوارد", "لوحة المؤشرات"], built_order
assert "مراحل التصنيع" in w._warm_failed and "مراحل التصنيع" not in w._built_screens
# الوارد لا يملأ جداوله في بانيه ← يُحدَّث بعد بنائه؛ الحسابات واللوحة يملآنها ← لا تحديث ثانٍ
assert ("refresh", "الوارد") in steps and ("refresh", "الحسابات") not in steps
assert ("refresh", "لوحة المؤشرات") not in steps
for n in ("المبيعات", "الحسابات", "الوارد", "لوحة المؤشرات"):
    i_b, i_r = steps.index(("build", n)), steps.index(("render", n))
    assert i_b < i_r, n
assert not w.jobs and all(not w.screen_needs_warm(n) for n in w.warm_order())
print("✔ بعد الدخول: كل الشاشات تُبنى ثم تُرسم مسبقاً، خطوة صغيرة كل مرة (بناء أو تحديث أو رسم)")
print("✔ وشاشة تعذّر بناؤها لا تُعاد محاولتها بلا نهاية — تُترك لأول فتح فتظهر رسالتها")

# بعد ترحيل: كل الشاشات بحاجة لتحديث — الظاهرة لا تُلمس، والبقية تُحدَّث وتُرسم
w.log.clear()
w.tabview.current_screen, w.tabview.mapped = "الوارد", True
w.mark_all_screens_dirty()
w.warm_screens()
first_job = w._warm_job
w.warm_screens()                              # ترحيل ثانٍ قبل أن تبدأ: سلسلة واحدة لا اثنتان
assert w.cancelled == [first_job] and w._warm_job != first_job
w.jobs = w.jobs[-1:]                          # الملغاة لا تعمل (كما يفعل after_cancel)
w.run()
refreshed = [n for k, n in w.log if k == "refresh"]
assert "الوارد" not in refreshed, "الشاشة الظاهرة أمام المستخدم لا تُحدَّث في الخلفية"
assert {"الحسابات", "لوحة المؤشرات"} <= set(refreshed)
assert ("render", "لوحة المؤشرات") in w.log, "بعد التحديث تُرسم من جديد (قد تُنشأ أدوات جديدة)"
print("✔ بعد كل تعديل بيانات: الشاشات المخفية تُحدَّث ثم تُرسم في الفراغ، والظاهرة لا تُلمس، "
      "وترحيلان متتاليان سلسلة واحدة")

# المستخدم يكتب أو ينقر ← تنتظر
w.log.clear()
w.mark_all_screens_dirty()
w._last_user_input = time.monotonic()
w.jobs.clear()
w._prebuild_screens(w.warm_order())
assert w.log == [] and w.jobs and w.jobs[-1][0] == 700
print("✔ لا خطوة تجهيز والمستخدم يكتب أو ينقر (تنتظر هدوءاً ١٫٥ ثانية)")

# تغيّر مقاس النافذة ← تُرسم الشاشات من جديد بالمقاس الجديد
w._last_user_input = 0.0
w.jobs.clear()
w.tabview.mapped = False
w._dirty_screens = set()
w.size = (1200, 700)
assert all(w.screen_needs_warm(n) for n in ("الحسابات", "لوحة المؤشرات"))
w.log.clear()
w._prebuild_screens(w.warm_order())
w.run()
assert {n for k, n in w.log if k == "render"} == {"المبيعات", "الحسابات", "الوارد", "لوحة المؤشرات"}
print("✔ تغيّر مقاس النافذة ← تُرسم الشاشات مسبقاً بالمقاس الجديد")

# ═══ ٣) الربط في البرنامج ═══
rec = body("recalculate_all")
assert rec.index("self.refresh_visible_screen()") < rec.index("self.warm_screens()")
calc = body("_startup_first_calc")
assert "self.warm_screens(delay=0)" in calc
pre = body("_prebuild_screens")
assert 'getattr(self, "_intro_cv", None) is not None' in pre, "لا تقطيع لحركة الانتقال من شاشة الدخول"
rs = body("refresh_screen")
assert '_rendered_size", {}).pop(name, None)' in rs
nav = body("navigate_to_screen")
assert nav.index("self.tabview.show(name)") < nav.index("self._rendered_size[name] = size")
print("✔ الحساب الشامل يحدّث الظاهرة فوراً ثم يجهّز البقية، والدخول يبدأ التجهيز بعد ظهور النظام")

# الرسم المسبق: خارج حدود النافذة، ويُعاد كل شيء لمكانه دائماً
pr = body("prerender", router)
assert "tk.Place.place_configure(self, x=-(w + 400)" in pr
assert "tk.Place.place_configure(wrapper, x=-(w + 400)" in pr
assert "finally:" in pr and "tk.Place.place_forget(widget)" in pr
assert "self.update_idletasks()" in pr and "self.update()" not in pr.replace("self.update_idletasks()", "")
assert re.search(r"if router_mapped and self\.current_screen == name:\s+return False", pr)
show = body("show", router)
assert 'target.winfo_manager() != "pack"' in show
print("✔ الرسم المسبق خارج حدود النافذة (مقصوص لا يُرى)، بلا معالجة أحداث المستخدم في منتصفه، "
      "ويُعاد كل شيء لمكانه حتى عند الخطأ")

sz = body("screen_area_size")
assert "shell.winfo_width() + extra_w" in sz and "shell.winfo_height() + shell.winfo_y()" in sz
assert "saved[0] == win" in sz
print("✔ مقاس منطقة الشاشات: الفعلي داخل الشاشات، ومحسوباً من الرئيسية قبل أول فتح")

# ═══ ٤) الفهارس: النتائج مطابقة حرفياً للمسح الكامل ═══
SALE_TYPES = ("مبيعات ذهب", "مبيعات فصوص وأحجار", "قيد يومي مدين", "وارد ذهب (عيار 18)", "قيد يومي دائن")
WORKER_TYPES = ("صرف ذهب", "قبض ذهب", "الليز", "البوليش", "المفنش ٨ بالالف", "المفنش ٤ بالالف",
                "السلك الراجع", "العيار بعد الفحص", "خياس الاله/المكائن")
I = build(["inv_period", "inv_in_period", "mark_backup_dirty", "invoices_by_period", "period_invoices",
           "invoices_by_name", "invoices_by_name_period", "calculate_single_ledger", "worker_rows_raji",
           "get_recorded_periods", "get_supplier_totals", "get_set_khayas_breakdown", "get_sets_gems_stones",
           "get_treasury_type_sets", "treasury_bucket", "get_workers_khayas", "treasury_period_components",
           "get_actual_section_khayas", "get_treasury_ledger"])


class A(I):
    current_display_month = "2026-09"

    def __init__(self, invoices):
        self.invoices = invoices
        self.invoice_counter = len(invoices)
        self.categories = {"المصنعين": ["أحمد", "سالم"], "المركبين": ["خالد"], "الآلة/المكائن": ["مكينة"]}

    def get_all_stage_categories(self): return ["الكاستنج"]
    def get_stage_config(self, cat): return ("صرف كاستنج", "قبض كاستنج", "مسترجع الكاستنج")


rnd = random.Random(33)
PERIODS = ["2026-0%d" % m for m in range(5, 10)]
invs = {}
for k in range(1, 2500):
    name = rnd.choice(["أحمد", "سالم", "خالد", "مكينة", "مورد ١", "مورد ٢", "حساب الخزينة"])
    t = rnd.choice(WORKER_TYPES + SALE_TYPES + ("خياس طقوم", "صرف كاستنج", "قبض كاستنج"))
    p = rnd.choice(PERIODS)
    inv = {"رقم الفاتورة": k, "الاسم": name, "النوع": t, "الوزن": round(rnd.uniform(0.1, 90), 2),
           "التاريخ": f"{p}-{rnd.randint(1, 28):02d} 10:00", "settled_status": rnd.choice(
               ["ACTIVE"] * 6 + ["SETTLED", "SETTLED_INOUT", "MEMO"]),
           "trees_count": rnd.choice([0.0, 0.0, 5.0, 7.0, 9.0, 3.0]), "set_number": str(rnd.randint(1, 40)),
           "row_number": str(rnd.randint(1, 30)), "قبل": 1.0, "بعد": 0.5}
    if rnd.random() < 0.8:
        inv["period"] = p if rnd.random() < 0.9 else rnd.choice(PERIODS)      # فترة تختلف عن شهر التاريخ
    invs[k] = inv
a = A(invs)


def check_all(a, label):
    every = list(a.invoices.values())
    n = 0
    for cat, names in a.categories.items():
        for name in names:
            for p in PERIODS + [None]:
                for settled in (False, True):
                    fast = a.calculate_single_ledger(name, cat, target_month=p, include_settled=settled)
                    # المسح الكامل: كل الحركات تُمرَّر صراحةً فتُفلتر بالاسم والفترة داخل الدالة كما كانت
                    slow = a.calculate_single_ledger(name, cat, target_month=p or a.current_display_month,
                                                     include_settled=settled, invoices=every)
                    assert fast == slow, (label, name, p, settled)
                    n += 1
    old_periods = {a.inv_period(i) for i in every if i.get("settled_status") == "ACTIVE" and a.inv_period(i)}
    old_periods.add(a.current_display_month)
    assert a.get_recorded_periods() == sorted(old_periods, reverse=True), label

    class Full(type(a)):
        def period_invoices(self, month): return self.invoices.values()      # المسح الكامل القديم

        def invoices_by_name(self):
            class All(dict):
                def get(s, k, d=None): return list(self.invoices.values())
            return All()

    full = Full.__new__(Full)
    full.__dict__.update(a.__dict__)
    for m in PERIODS + [None, ""]:
        assert a.get_set_khayas_breakdown(m) == full.get_set_khayas_breakdown(m), (label, m)
        assert a.get_sets_gems_stones(m) == full.get_sets_gems_stones(m), (label, m)
    for name in ("مورد ١", "مورد ٢", "أحمد", "غير موجود"):
        assert a.get_supplier_totals(name) == full.get_supplier_totals(name), (label, name)
    # دفتر الخزينة: التجميع القديم بالفترة يدوياً
    by_period = {}
    for inv in every:
        if a.inv_period(inv):
            by_period.setdefault(a.inv_period(inv), []).append(inv)
    assert {p: [i["رقم الفاتورة"] for i in v] for p, v in by_period.items()} == \
           {p: [i["رقم الفاتورة"] for i in v] for p, v in a.invoices_by_period().items() if p}, label
    return n


n = check_all(a, "قبل التعديل")
print(f"✔ {n} دفتر عامل (كل عامل × كل فترة × مع/بلا المُقفل) بالفهرس = المسح الكامل حرفياً، "
      "وقائمة الفترات والأطقم والموردين ودفتر الخزينة كذلك")

# تعديلات: نقل حركة لفترة أخرى، تغيير اسم، حذف، إضافة — والفهارس تُبطل بالحفظ (mark_backup_dirty)
first = a.calculate_single_ledger("أحمد", "المصنعين", target_month="2026-07")
moved = next(i for i in a.invoices.values() if i["الاسم"] == "أحمد" and a.inv_period(i) == "2026-07"
             and i["النوع"] == "صرف ذهب" and i["settled_status"] == "ACTIVE")
moved["period"] = "2026-08"
a.mark_backup_dirty()
after = a.calculate_single_ledger("أحمد", "المصنعين", target_month="2026-07")
assert round(first["الصرف"] - after["الصرف"], 2) == round(moved["الوزن"], 2)
renamed = next(i for i in a.invoices.values() if i["الاسم"] == "سالم")
renamed["الاسم"] = "أحمد"
a.mark_backup_dirty()
del a.invoices[next(iter(a.invoices))]
a.invoices[99999] = {"رقم الفاتورة": 99999, "الاسم": "خالد", "النوع": "قبض ذهب", "الوزن": 3.0,
                     "التاريخ": "2026-09-02 09:00", "period": "2026-09", "settled_status": "ACTIVE"}
check_all(a, "بعد التعديل")
print("✔ بعد نقل حركة لفترة أخرى وتغيير اسم وحذف وإضافة: الفهارس تُبنى من جديد والنتائج مطابقة للمسح الكامل")

dash = body("dashboard_data")
assert "comp_of(month)" in dash and "comp_of(prev[-1])" in dash and "by_period = {r[\"period\"]: r for r in ledger}" in dash
print("✔ لوحة المؤشرات تقرأ بنود كل فترة من صفّها في دفتر الخزينة — لا حساب ثانٍ (كانت ٢٧ حساباً)")

print("\n✅ أي شاشة تفتح فوراً: مجهّزة مسبقاً، ومحدَّثة في الفراغ، ومرسومة قبل النقر — بالأرقام نفسها")
