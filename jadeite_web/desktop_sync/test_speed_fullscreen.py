# -*- coding: utf-8 -*-
"""
اختبار السرعة وملء الشاشة — يشغّل الدوال الحقيقية من البرنامج:

  • فهارس الحركات (بالاسم وبالفترة) تُعاد بلا مسح، وتُبطَل بأي تغيير فعلي
  • الحد الأدنى للنافذة لا يتجاوز الشاشة مهما كان تكبير العرض
  • التكبير يُطلب في كل مرة، وبديله الأخير مساحة العمل بالبكسل الفعلي
  • التحقق بعد الظهور: نافذة لا تملأ الشاشة تُكبَّر من جديد
  • عميل سحابي واحد لكل نوع بمهلة محدّدة (لا اتصال جديد لكل طلب)
  • الدخول: الفحصان معاً، وتسجيل الوقت والرفع في الخلفية
  • الشاشات تُجهَّز في الخلفية فقط والمستخدم لا يكتب أو ينقر
  • رؤوس الشاشات وأقسام مراحل التصنيع تُبنى عند أول فتح لها
"""
import ast, io, sys, textwrap, threading, time, types

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


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def build(methods, extra="", ns=None, cls=APP):
    body = "\n".join(textwrap.indent(method_src(m, cls), "    ") for m in methods)
    ns = {} if ns is None else ns
    exec("class App:\n" + body + "\n" + textwrap.indent(extra, "    "), ns)
    return ns["App"]


seg = method_src

# ═══ ١) فهارس الحركات ═══
App = build(["mark_backup_dirty", "invoices_by_name", "invoices_by_period", "period_invoices", "inv_period"])
app = App()
app.invoice_counter = 3
app.invoices = {
    1: {"الاسم": "أحمد", "التاريخ": "2026-08-03 10:00:00", "period": "2026-08", "الوزن": 5.0},
    2: {"الاسم": "سالم", "التاريخ": "2026-09-01 10:00:00", "period": "", "الوزن": 2.0},
    3: {"الاسم": "أحمد", "التاريخ": "2026-09-02 10:00:00", "period": "2026-09", "الوزن": 1.0},
}
idx = app.invoices_by_name()
assert [i["الوزن"] for i in idx["أحمد"]] == [5.0, 1.0] and len(idx["سالم"]) == 1
assert app.invoices_by_name() is idx
print("✔ فهرس الأسماء يُبنى مرة واحدة ويُعاد كما هو ما دامت البيانات لم تتغيّر")
assert [i["الوزن"] for i in app.period_invoices("2026-09")] == [2.0, 1.0]
assert len(list(app.period_invoices(""))) == 3
print("✔ حركات الفترة (الصريحة والمشتقّة من التاريخ) بلا مسح لكل الحركات")

app.invoices[2]["الوزن"] = 9.0
assert app.invoices_by_name()["سالم"][0]["الوزن"] == 9.0
print("✔ تعديل الوزن يظهر فوراً (الفهرس يحمل كائنات الحركات نفسها)")

app.invoice_counter += 1
app.invoices[4] = {"الاسم": "سالم", "التاريخ": "2026-09-09 10:00:00", "period": "2026-09", "الوزن": 3.0}
assert len(app.invoices_by_name()["سالم"]) == 2 and len(app.period_invoices("2026-09")) == 3
del app.invoices[1]
assert [i["الوزن"] for i in app.invoices_by_name()["أحمد"]] == [1.0]
assert len(app.period_invoices("2026-08")) == 0
print("✔ الإضافة والحذف يُبطلان الفهرسين")

app.invoices[3]["الاسم"] = "سالم"
app.invoices[3]["period"] = "2026-10"
app.mark_backup_dirty()
assert "أحمد" not in app.invoices_by_name() and len(app.invoices_by_name()["سالم"]) == 3
assert [i["الوزن"] for i in app.period_invoices("2026-10")] == [1.0]
print("✔ تغيير الاسم أو الفترة ثم الحفظ (mark_backup_dirty) يُعيد بناء الفهرسين")

app.invoices = {7: {"الاسم": "جديد", "التاريخ": "2026-09-01", "period": "2026-09", "الوزن": 1.0}}
assert list(app.invoices_by_name()) == ["جديد"]
print("✔ إعادة التحميل (قاموس حركات جديد) تُعيد بناء الفهرس")

save = seg("save_invoice_to_db")
blocked = save[save.index("check_edit_permission"):save.index("return False")]
assert "_inv_version" in blocked
print("✔ منع التعديل يعيد كائن الحركة الأصلي ويُبطل الفهرس معه")

for m in ("calculate_single_ledger", "get_box_closed_total"):
    assert "invoices_by_name()" in seg(m), m
for m in ("get_stage_totals_for_month", "get_box_khayas_cumulative", "collect_stage_ops_rows",
          "treasury_period_components"):
    assert "period_invoices(" in seg(m), m
print("✔ الدفاتر والصناديق والمراحل والخزينة تقرأ من الفهارس")

# ═══ ٢) ملء الشاشة ═══
ns = {"screen_work_area": lambda w: (0, 0, w.sw, w.sh - 48)}


class FakeCtk:
    class ScalingTracker:
        scale = 1.0

        @classmethod
        def get_window_scaling(cls, _w):
            return cls.scale

        @classmethod
        def get_widget_scaling(cls, _w):
            return cls.scale


ns["ctk"] = FakeCtk
ns["time"] = time
ns["tk"] = types.SimpleNamespace(Tk=types.SimpleNamespace(
    wm_geometry=lambda self, g: self.calls.append(("wm_geometry", g))))
exec("\n\n".join(module_src(n) for n in ("fill_work_area", "maximize_window", "ensure_fills_screen",
                                          "keep_maximized_after_show")), ns)
Win = build(["safe_minsize", "force_maximize", "_ensure_fills_screen", "_after_scaling_change",
             "logical_screen_width", "sidebar_width"], extra=textwrap.dedent("""
    def __init__(self, sw, sh, zoom_ok=True, attr_ok=True, size=(0, 0), st="normal"):
        self.sw, self.sh, self.zoom_ok, self.attr_ok = sw, sh, zoom_ok, attr_ok
        self.size, self.st, self.calls = size, st, []
    def winfo_screenwidth(self): return self.sw
    def winfo_screenheight(self): return self.sh
    def winfo_width(self): return self.size[0]
    def winfo_height(self): return self.size[1]
    def update_idletasks(self): pass
    def minsize(self, w, h): self.calls.append(("minsize", w, h))
    def state(self, value=None):
        if value is None:
            return self.st
        self.calls.append(("state", value))
        if value == "zoomed" and not self.zoom_ok:
            raise RuntimeError("no zoomed")
        self.st = value
    def attributes(self, *a):
        self.calls.append(("attributes",) + a)
        if not self.attr_ok:
            raise RuntimeError("no -zoomed")
"""), ns=ns)

FakeCtk.ScalingTracker.scale = 1.25
w = Win(1366, 768)
w.safe_minsize(1100, 620)
_, mw, mh = w.calls[-1]
assert mw * 1.25 <= 1366 and mh * 1.25 <= 768, (mw, mh)
print(f"✔ شاشة ١٣٦٦×٧٦٨ بتكبير ١٢٥٪: الحد الأدنى {mw}×{mh} (كان ١١٠٠×٦٢٠ = ١٣٧٥×٧٧٥ بكسلاً خارج الشاشة)")
FakeCtk.ScalingTracker.scale = 1.0
w = Win(1920, 1080)
w.safe_minsize(1100, 620)
assert w.calls[-1] == ("minsize", 1100, 620)
print("✔ على الشاشات الكبيرة يبقى الحد الأدنى كما هو")
assert "self.minsize(" not in "\n".join(l for l in seg("__init__").split("\n"))
assert src.count("self.safe_minsize(") >= 2
print("✔ النظام يضبط حدّه الأدنى عبر safe_minsize وحدها")

FakeCtk.ScalingTracker.scale = 1.25
assert Win(1920, 1080).logical_screen_width() == 1536 and Win(1920, 1080).sidebar_width() == 300
FakeCtk.ScalingTracker.scale = 1.0
print("✔ الشريط الجانبي يُقاس بعرض الشاشة الفعلي بعد تكبير العرض (١٩٢٠ بتكبير ١٢٥٪ = ١٥٣٦)")

w = Win(1366, 768, st="zoomed")
w.force_maximize()
assert ("state", "zoomed") in w.calls
print("✔ التكبير يُطلب حتى لو ادّعت النافذة أنها مكبّرة (لا خروج مبكر)")
w = Win(1366, 768, zoom_ok=False)
w.force_maximize()
assert ("attributes", "-zoomed", True) in w.calls
w = Win(1366, 768, zoom_ok=False, attr_ok=False)
w.force_maximize()
assert w.calls[-1] == ("wm_geometry", "1366x720+0+0")
print("✔ البديل الأخير: مساحة العمل بالبكسل الفعلي عبر wm_geometry (لا يضربها التكبير)")

w = Win(1366, 768, size=(1366, 720), st="zoomed")
w._ensure_fills_screen()
assert w.calls == []
w = Win(1366, 768, size=(900, 600), st="zoomed")
w._ensure_fills_screen()
assert w.calls[:2] == [("state", "normal"), ("state", "zoomed")], w.calls
assert w.calls[-1] == ("wm_geometry", "1366x720+0+0")
print("✔ نافذة «مكبّرة» بحجم صغير: تُعاد لحالتها ثم تُكبَّر، وإلا تُضبط على مساحة العمل")
w = Win(1366, 768, size=(1, 1), st="iconic")
w._ensure_fills_screen()
assert w.calls == []
print("✔ النافذة المصغّرة في شريط المهام لا تُكبَّر رغماً عن المستخدم")

assert src.count("self.after(1100, self._ensure_fills_screen)") >= 2
print("✔ التحقق من ملء الشاشة مجدول بعد ظهور النظام في مساري الفتح")
ns2 = {"sys": types.SimpleNamespace(platform="linux")}
exec(module_src("screen_work_area"), ns2)
assert ns2["screen_work_area"](Win(1600, 900)) == (0, 0, 1600, 852)
print("✔ مساحة العمل خارج ويندوز: الشاشة ناقص شريط المهام")

# فتح النظام مباشرة (بلا انتقال الدخول): يُثبَّت ظهوره قبل mainloop
init = seg("__init__")
direct = init[init.index("self.deiconify()"):init.index("self._startup_first_calc")]
assert "self.force_maximize()" in direct and "self.update()" in direct
print("✔ فتح النظام مباشرة: يُكبَّر ويُثبَّت ظهوره فلا تخفيه المكتبة ثم تعيده بحجم صغير")

# تغيّر تكبير العرض بعد الظهور
FakeCtk.ScalingTracker.scale = 1.5
w = Win(1366, 768, size=(900, 500), st="zoomed")
w._min_request, w._opened_at = (1100, 620), time.monotonic()
w._after_scaling_change()
mins = [c for c in w.calls if c[0] == "minsize"]
assert mins and mins[-1][1] * 1.5 <= 1366 and mins[-1][2] * 1.5 <= 768, mins
assert ("state", "zoomed") in w.calls
w = Win(1366, 768, size=(900, 500), st="normal")
w._min_request, w._opened_at = (1100, 620), time.monotonic() - 60
w._after_scaling_change()
assert not any(c[0] == "state" for c in w.calls)
FakeCtk.ScalingTracker.scale = 1.0
print("✔ تكبير عرض يُكتشف بعد الفتح: الحد الأدنى يُعاد حسابه، ويُعاد التكبير في الثواني الأولى فقط")


class Base:                                   # CTkScalingBaseClass
    def _set_scaling(self, a, b):
        self.calls.append(("widgets", a, b))


class FakeCTk(Base):                          # ctk.CTk: يفرض ٦٠٠×٥٠٠ حداً أدنى وأعلى
    def _set_scaling(self, a, b):
        self.calls.append(("forced 600x500",))
        super()._set_scaling(a, b)


nsm = {"ctk": types.SimpleNamespace(CTk=FakeCTk)}
exec(module_src("StableWindowMixin"), nsm)


class Stable(nsm["StableWindowMixin"], FakeCTk):
    def __init__(self):
        self.calls = []

    def after(self, ms, fn):
        self.calls.append(("after", ms, fn.__name__))

    def _after_scaling_change(self):
        pass


st = Stable()
st._set_scaling(1.25, 1.25)
assert st.calls == [("widgets", 1.25, 1.25), ("after", 150, "_after_scaling_change")], st.calls
print("✔ تغيّر التكبير يُحدّث مقاييس العناصر ولا يفرض على النافذة ٦٠٠×٥٠٠ (سبب انكماشها)")
for c in ("GoldSystemApp", "LoginWindow", "AdminPanel"):
    assert [getattr(b, "id", getattr(b, "attr", None)) for b in get_class(c).bases] == ["StableWindowMixin", "CTk"], c
print("✔ النوافذ الثلاث (الدخول، النظام، لوحة المدير) محمية من ذلك")

# لوحة المدير: تُكبَّر بعد ظهورها الفعلي، وعند العودة من حساب عميل
admin = get_class("AdminPanel")
assert "keep_maximized_after_show(self)" in seg("__init__", admin)
assert 'self.geometry("1000x650")' not in seg("__init__", admin)
assert "self.deiconify()\n        maximize_window(self)" in "\n".join(lines[admin.lineno - 1:admin.end_lineno])
after_calls = []
fake = types.SimpleNamespace(after=lambda ms, fn: after_calls.append(ms))
ns["keep_maximized_after_show"](fake)
assert after_calls == [60, 350, 1100] and fake._opened_at > 0
print("✔ لوحة المدير: تُكبَّر بعد أن تُظهرها المكتبة (لا بحجم ١٠٠٠×٦٥٠)، وبعد العودة من حساب عميل")

# شاشة الدخول
login = get_class("LoginWindow")
assert "self._go_fullscreen()" in seg("__init__", login)
L = build(["_go_fullscreen", "_ensure_fullscreen"], ns={"tk": ns["tk"]}, cls=login, extra=textwrap.dedent("""
    def __init__(self, size, pos=(0, 0), st="normal"):
        self.W, self.H, self._alive, self.size, self.pos, self.st, self.calls = 1366, 768, True, size, pos, st, []
    def state(self): return self.st
    def winfo_width(self): return self.size[0]
    def winfo_height(self): return self.size[1]
    def winfo_rootx(self): return self.pos[0]
    def winfo_rooty(self): return self.pos[1]
    def update_idletasks(self): pass
    def attributes(self, *a): self.calls.append(a)
"""))
lw = L((1366, 768))
lw._ensure_fullscreen()
assert lw.calls == []
for bad in (L((1100, 700)), L((1366, 768), pos=(1920, 0))):
    bad._ensure_fullscreen()
    assert bad.calls == [("-fullscreen", False), ("wm_geometry", "1366x768+0+0"), ("-fullscreen", True)], bad.calls
lw = L((300, 200), st="iconic")
lw._ensure_fullscreen()
assert lw.calls == []
print("✔ شاشة الدخول: أصغر من الشاشة أو على شاشة أخرى ← تُعاد لملء الشاشة الرئيسية (والمصغّرة تُترك)")

# ═══ ٣) عميل سحابي مشترك بمهلة محدّدة ═══
created = []


class ClientOptions:
    def __init__(self, postgrest_client_timeout=None):
        self.timeout = postgrest_client_timeout


def fake_create(url, key, options=None):
    time.sleep(0.02)
    created.append(options.timeout if options else None)
    return types.SimpleNamespace(postgrest=object())


sys.modules["supabase"] = types.SimpleNamespace(ClientOptions=ClientOptions)
ns3 = {"threading": threading, "SUPABASE_AVAILABLE": True, "SUPABASE_URL": "https://x",
       "SUPABASE_PUBLISHABLE_KEY": "pub", "SUPABASE_SECRET_KEY": "", "_sb_create_client": fake_create,
       "log_cloud_error": lambda *a: None}
exec("\n\n".join(module_src(n) for n in ("_SB_CLIENTS", "_SB_LOCK", "_shared_supabase_client",
                                          "get_supabase_public_client", "get_supabase_login_client")), ns3)
got = []
ts = [threading.Thread(target=lambda: got.append(ns3["get_supabase_login_client"]())) for _ in range(8)]
[t.start() for t in ts]
[t.join() for t in ts]
assert len(created) == 1 and len({id(c) for c in got}) == 1
print("✔ ثمانية طلبات متزامنة ← عميل واحد فقط (اتصال واحد يُعاد استخدامه)")
ns3["get_supabase_public_client"]()
ns3["get_supabase_public_client"]()
assert created == [12, 60], created
print("✔ مهلة الدخول ١٢ ثانية، وبقية الطلبات ٦٠ (كانت ١٢٠ لكل طلب)")
del sys.modules["supabase"]
assert "_shared_supabase_client(\"admin\"" in module_src("get_supabase_admin_client")
assert "prewarm_supabase_clients()" in seg("__init__", get_class("LoginWindow"))
print("✔ عميل المدير مشترك أيضاً، والعميلان يُجهَّزان أثناء شاشة الترحيب")

# ═══ ٤) مسار الدخول ═══
login = seg("try_login", get_class("LoginWindow"))
verify = login[login.index("def verify"):login.index("self._busy = True")]
assert "threading.Thread(" in verify and "cloud_verify_client_login(username, password, touch=False)" in verify
print("✔ فحص المدير المساعد وفحص العميل يجريان معاً (طلب واحد من الوقت بدل طلبين)")
assert "touch_client_login_async(client_id)" in login
assert "threading.Thread" in module_src("touch_client_login_async")
print("✔ تسجيل وقت الدخول للمدير في الخلفية")
assert "if IS_ADMIN_BUILD and SYNC_AVAILABLE and CURRENT_SYNC_TOKEN:" in login
print("✔ نسخة العميل لا تنتظر الرفع عند الدخول — محرك المزامنة يرفع في الخلفية فور الفتح")
assert "install_sync_schema(self.db_path)" in io.open("cloud_sync.py", encoding="utf-8").read()
assert "self.cloud_sync.start()" in seg("start_cloud_sync_engine")
print("✔ ومحرك المزامنة يُجهّز بنية التتبّع بنفسه قبل أول رفع")
assert "cloud_verify_client_login" not in login[login.index("if kind == \"sub_admin\""):]
assert "CURRENT_SYNC_TOKEN = None" in login
print("✔ دخول المدير المساعد لا يرث رمز مزامنة من الفحص المتزامن")

# ═══ ٥) التجهيز في الخلفية لا يزاحم المستخدم ═══
P = build(["_note_user_input", "_prebuild_screens"], ns={"time": time, "log_cloud_error": lambda *a: None})


class Pre(P):
    def __init__(self):
        self.built, self.after_calls, self.binds = [], [], []

    def bind_all(self, seq, fn, add=None):
        self.binds.append((seq, add))

    def after(self, ms, fn):
        self.after_calls.append(ms)

    def ensure_screen_built(self, name):
        self.built.append(name)

    def refresh_pending_screen(self, name):
        pass


p = Pre()
p._note_user_input()
p._prebuild_screens(["المبيعات", "مراحل التصنيع"])
assert p.built == [] and p.after_calls == [700]
assert ("<KeyPress>", "+") in p.binds and ("<ButtonPress>", "+") in p.binds
print("✔ المستخدم يكتب أو ينقر ← التجهيز ينتظر (لا توقّف تحت يده)")
p._last_user_input = time.monotonic() - 5
p._prebuild_screens(["المبيعات", "مراحل التصنيع"])
assert p.built == ["المبيعات"] and p.after_calls[-1] == 120 and len(p.binds) == 2
print("✔ بعد الهدوء تُجهَّز شاشة كل مرة، والمراقبة تُركَّب مرة واحدة")

# ═══ ٦) البناء عند أول فتح ═══
router = get_class("ScreenRouter")
add = seg("add", router)
assert "top_bar" not in add and "CTkLabel" not in add
assert "self._ensure_header(name)" in seg("show", router)
assert "before=content" in seg("_ensure_header", router)
print("✔ رأس كل شاشة يُبنى عند أول فتح لها لا للشاشات كلها عند الدخول")
ops = seg("build_operations_tab")
assert "self._stage_builders" in ops and "self.build_mfg_ui(" not in ops
assert "self.build_casting_ui(" not in ops and "self.build_polish_ui(" not in ops
assert "self.build_stage_on_demand(stage)" in seg("switch_op_stage")
S = build(["build_stage_on_demand"])
s = S()
box, calls = object(), []
s._stage_builders = {"المصنعين": (box, calls.append), "المركبين": (box, calls.append)}
s._built_stage_containers = set()
for st in ("المصنعين", "المركبين", "المصنعين", "غير موجود"):
    s.build_stage_on_demand(st)
assert calls == [box]
print("✔ أقسام مراحل التصنيع تُبنى عند أول فتح، والمصنعون والمركبون يتشاركون واجهة واحدة")

# ═══ ٧) الانتقال سريع ═══
body = "\n".join(lines[APP.lineno - 1:APP.end_lineno])
fade = float(body.split("_INTRO_FADE_S = ")[1].split()[0])
reveal = float(body.split("_INTRO_REVEAL_S = ")[1].split()[0])
assert fade <= 0.2 and reveal <= 0.8, (fade, reveal)
print(f"✔ ظهور النظام {fade} ث وانحسار الأمواج {reveal} ث")

print("\n✅ السرعة وملء الشاشة سليمان")
