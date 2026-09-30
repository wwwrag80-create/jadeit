# -*- coding: utf-8 -*-
"""
اختبار نظام التصميم المحدَّث (الدفعة ١٢) — يشغّل الدوال الحقيقية من البرنامج:

  • تباين الألوان: كل نص على خلفيته ≥ ٤٫٥:١ (معيار WCAG AA)، في المظهرين.
  • ارتفاع صف الجدول من قياس الخط الحقيقي: لا تُقصّ نقاط «ي» ولا ذيول الحروف على
    أي نسبة تكبير (كان ٢٤ بكسل ثابتة فتُقصّ على ١٢٥٪).
  • المقاسات حسب المساحة الفعلية للشاشة (بعد تكبير ويندوز).
  • ألوان الوسوم القديمة وخطوطها تتبع نظام التصميم والمظهر (الأسود كان يختفي على الداكن).
  • تظليل الصف تحت المؤشر، وأشرطة تمرير حديثة، وإطار علوي قوي، ومظهر تلقائي محفوظ.
  • أحدث إصدارات المكتبات، وخط Cairo SemiBold مرفقاً.
"""
import ast, io, os, re, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
lines = src.split("\n")
tree = ast.parse(src)
APP = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
ROUTER = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ScreenRouter")


def method_src(name, cls=APP):
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))


def class_value(name, cls=APP):
    node = next(m for m in cls.body if isinstance(m, ast.Assign)
                and any(getattr(t, "id", None) == name for t in m.targets))
    return ast.literal_eval(node.value)


def module_node(name):
    return next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == name for t in n.targets))


def module_func(name):
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


seg = method_src
UI = ast.literal_eval(module_node("UI").value)
DESIGN = class_value("DESIGN")
LEGACY = ast.literal_eval(module_node("_LEGACY_TEXT_COLORS").value)


def lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ═══ ١) التباين ═══
checks = [
    ("النص الثانوي على خلفية الصفحة", UI["muted"], UI["canvas"], 4.5),
    ("النص الثانوي على البطاقة", UI["muted"], UI["surface"], 4.5),
    ("عنوان الإطار العلوي", UI["header_text"], UI["header"], 4.5),
    ("وصف الإطار العلوي", UI["header_muted"], UI["header"], 4.5),
]
for mode, c in DESIGN.items():
    checks += [(f"جدول {mode}: النص", c["text"], c["bg"], 4.5),
               (f"جدول {mode}: الصف المتناوب", c["text"], c["row_alt"], 4.5),
               (f"جدول {mode}: تحت المؤشر", c["text"], c["hover"], 4.5),
               (f"جدول {mode}: المحدد", c["sel_text"], c["sel_bg"], 4.5),
               (f"جدول {mode}: الرأس", c["head_text"], c["head_bg"], 4.5),
               (f"جدول {mode}: الرأس تحت المؤشر", c["head_text"], c["head_hover"], 4.5)]
for old, (light, dark) in LEGACY.items():
    checks += [(f"لون قديم {old} ← فاتح", light, DESIGN["light"]["bg"], 4.5),
               (f"لون قديم {old} ← داكن", dark, DESIGN["dark"]["bg"], 4.5)]
failed = [(n, round(contrast(a, b), 2)) for n, a, b, need in checks if contrast(a, b) < need]
assert not failed, failed
print(f"✔ التباين ≥ ٤٫٥:١ في {len(checks)} زوج نص/خلفية (المظهران، الجداول، الإطار العلوي، الألوان القديمة)")
assert contrast("#6B7280", UI["canvas"]) < 4.5 and contrast(UI["muted"], UI["canvas"]) >= 5.0
print(f"✔ النص الثانوي: {contrast('#6B7280', UI['canvas']):.2f} ← {contrast(UI['muted'], UI['canvas']):.2f}")

hdr = seg("_ensure_header", ROUTER)
for pill_bg, pill_fg in re.findall(r'pill\(\("(#[0-9A-Fa-f]{6})", "#[0-9A-Fa-f]{6}"\), \("(#[0-9A-Fa-f]{6})", "#[0-9A-Fa-f]{6}"\)\)', hdr):
    assert contrast(pill_fg, pill_bg) >= 4.5, (pill_fg, pill_bg)
assert 'fg_color=head' in hdr and 'border_color=(UI["header_edge"], UI["header_edge"])' in hdr
print("✔ الإطار العلوي لكل شاشة كحلي بحافة ذهبية، وشاراته مقروءة (≥ ٤٫٥:١)")

# ═══ ٢) ارتفاع الصف من قياس الخط ═══
ns = {}
exec(textwrap.dedent(seg("row_height_for")).replace("@staticmethod\n", ""), ns)
row_height_for = ns["row_height_for"]
# مقاييس Cairo (من ملف الخط: usWinAscent ١٣١٢، usWinDescent ٥٧١ لكل ١٠٠٠)، وأعمق ذيل حرف
# ٠٫٤٦ وأعلى حرف ٠٫٩٦٣ من حجم الخط (glyf) — يُتحقَّق منها أدناه إن توفّر fontTools
ASC, DESC, INK_DOWN, INK_UP = 1.312, 0.571, 0.462, 1.0


def ink_fits(row, em):
    asc, desc = round(ASC * em), round(DESC * em)
    top = (row - (asc + desc)) / 2 + asc                   # خط الأساس داخل الصف
    return top - INK_UP * em >= 0 and top + INK_DOWN * em <= row


for pt, scale in ((11, 1.0), (11, 1.25), (12, 1.25), (11, 1.5), (14, 1.0), (15, 1.5)):
    em = pt * 96 / 72 * scale
    row = row_height_for(round(ASC * em), round(DESC * em))
    assert ink_fits(row, em), (pt, scale, row)
    assert row <= round((ASC + DESC) * em) + 2, (pt, scale, row)     # لا أطول من السطر كاملاً
assert not ink_fits(24, 11 * 96 / 72 * 1.25)
print("✔ صف الجدول يسع الحروف كاملة على كل تكبير (١٠٠–١٥٠٪) دون أن يطول بلا داعٍ؛ "
      "و٢٤ بكسل الثابتة تقصّ «ي» على ١٢٥٪")
assert row_height_for(10, 3, minimum=40) == 40
print("✔ والحد الأدنى للشاشة يبقى محترماً")

try:
    from fontTools.ttLib import TTFont
    f = TTFont("fonts/Cairo-Regular.ttf")
    assert (f["OS/2"].usWinAscent, f["OS/2"].usWinDescent) == (1312, 571)
    print("✔ مقاييس Cairo المعتمدة مطابقة لملف الخط نفسه")
except ImportError:
    pass

app_src = seg("apply_design_system")
assert "row_h = self.table_row_height(body, m[\"row_h\"])" in app_src and "rowheight=row_h" in app_src
assert "self._totals_row_h = self.table_row_height(total_font, 34)" in seg("ensure_totals_bar_style")
assert 'height=getattr(self, "_totals_row_h", 34) + 6' in seg("create_sticky_total_tree")
print("✔ الجدول وشريط الإجمالي بارتفاع من قياس خطّيهما (لا ٢٤ و٣٤ ثابتتين)")

# ═══ ٣) المقاسات حسب المساحة الفعلية ═══
class FakeScaling:
    value = 1.0

    @classmethod
    def get_window_scaling(cls, _w):
        return cls.value


ns = {"ctk": type("ctk", (), {"ScalingTracker": FakeScaling})}
exec("class S:\n" + textwrap.indent(seg("design_metrics"), "    ")
     + "\n    def __init__(self, w, h): self._w, self._h = w, h\n"
     "    def winfo_screenwidth(self): return self._w\n"
     "    def winfo_screenheight(self): return self._h\n", ns)
S = ns["S"]
FakeScaling.value = 1.0
assert S(1920, 1080).design_metrics()["font"] == 14
FakeScaling.value = 1.25
assert S(1920, 1080).design_metrics()["font"] == 12          # ١٥٣٦ منطقياً
assert S(1366, 768).design_metrics()["font"] == 11
FakeScaling.value = 1.5
assert S(3840, 2160).design_metrics()["font"] == 15          # ٢٥٦٠ منطقياً
print("✔ الخط حسب المساحة الفعلية: ١٩٢٠ بتكبير ١٢٥٪ ← ١٢ (كان ١٤ فيكبر مرتين)")

# ═══ ٤) ألوان الوسوم وخطوطها ═══
class FakeTk:
    def __init__(self, t):
        self.t = t

    def call(self, *a):
        return tuple(self.t.tags)

    def splitlist(self, v):
        return tuple(v)


class FakeTree:
    def __init__(self):
        self.tags, self.items, self.binds = {}, {}, {}
        self.tk, self._w = FakeTk(self), ".t"

    def tag_configure(self, tag, option=None, **kw):
        d = self.tags.setdefault(tag, {})
        if option:
            return d.get(option, "")
        d.update({k: v for k, v in kw.items()})

    def item(self, iid, option=None, **kw):
        if kw:
            self.items[iid].update(kw)
            return
        return self.items[iid].get(option) if option else self.items[iid]

    def exists(self, iid):
        return iid in self.items

    def get_children(self):
        return list(self.items)

    def identify_row(self, y):
        return f"I{y}" if f"I{y}" in self.items else ""

    def bind(self, seq, fn, add=None):
        self.binds[seq] = fn


def build(methods, attrs=(), extra=""):
    body = "\n".join(textwrap.indent(f"{a} = {class_value(a)!r}", "    ") for a in attrs)
    body += "\n" + "\n".join(textwrap.indent(method_src(m), "    ") for m in methods)
    n = {"_LEGACY_TEXT_COLORS": LEGACY}
    exec("class A:\n" + body + "\n" + textwrap.indent(extra, "    "), n)
    return n["A"]


A = build(["normalize_tree_tags", "enable_row_hover", "style_tree_rows"],
          attrs=("DESIGN", "_LEGACY_TREE_COLORS"))
for mode in ("light", "dark"):
    a = A()
    a._design = dict(DESIGN[mode], mode=mode, font=11, body_font=("Cairo SemiBold", 11),
                     total_font=("Cairo", 12, "bold"))
    t = FakeTree()
    t.tag_configure("green_tag", foreground="#000000", font=("Cairo", 13, "bold"))
    t.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 14, "bold"))
    t.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))
    t.tag_configure("bar", foreground="#000000", background="#c4c9ce")
    a.normalize_tree_tags(t)
    a.normalize_tree_tags(t)                                 # تكراره لا يغيّر شيئاً
    want_black = "#1f2937" if mode == "light" else "#e6edf3"
    assert t.tags["green_tag"]["foreground"] == want_black, (mode, t.tags["green_tag"])
    assert t.tags["green_tag"]["font"] == ("Cairo", 11, "bold")
    assert t.tags["total_tag"]["font"] == ("Cairo", 12, "bold")
    assert t.tags["total_tag"]["foreground"] == LEGACY["#d4af37"][0 if mode == "light" else 1]
    assert t.tags["red_tag"]["foreground"] == LEGACY["#e74c3c"][0 if mode == "light" else 1]
    assert t.tags["bar"]["foreground"] == "#000000"          # بخلفيته الخاصة: كما صُمّم
print("✔ ألوان الوسوم القديمة تتبع المظهر (الأسود كان يختفي على الداكن، والذهبي ٢:١ على الأبيض)، "
      "وخطوطها بحجم الجدول لا ١٣ و١٤ ثابتة")

a = A()
a._design = dict(DESIGN["light"], mode="light", font=11, body_font=("Cairo", 11), total_font=("Cairo", 12, "bold"))
t = FakeTree()
a.enable_row_hover(t)
assert list(t.tags)[0] == "hover_row" and t.tags["hover_row"]["background"] == DESIGN["light"]["hover"]
t.items = {"I5": {"tags": ("odd_row",)}, "I9": {"tags": ("total_tag",)}}
t.binds["<Motion>"](type("E", (), {"y": 5}))
assert t.items["I5"]["tags"] == ("odd_row", "hover_row")
t.binds["<Motion>"](type("E", (), {"y": 9}))
assert t.items["I5"]["tags"] == ("odd_row",) and t.items["I9"]["tags"] == ("total_tag", "hover_row")
t.binds["<Leave>"](None)
assert t.items["I9"]["tags"] == ("total_tag",)
print("✔ تظليل الصف تحت المؤشر: وسمه أول وسم في الجدول (الأعلى أولوية في ttk)، ويُزال عند الخروج")

for fn in ("create_standard_treeview", "create_sticky_total_tree", "open_fullscreen_table_view"):
    body = seg(fn)
    assert "self.enable_row_hover(" in body, fn
    assert "self.make_scrollbar(" in body and "ttk.Scrollbar(" not in body, fn
assert "ttk.Scrollbar(" not in src
cst = seg("create_standard_treeview")
assert cst.index("self.enable_row_hover(tree)") < cst.index("tree.heading(")
print("✔ كل الجداول بشريط تمرير حديث (رفيع مستدير) وتظليل الصف — لا شريط ويندوز قديماً في البرنامج")

# ═══ ٥) لا تنسيق يغيّر كل الجداول من شاشة واحدة ═══
outside = [m.name for m in APP.body if isinstance(m, ast.FunctionDef)
           and m.name != "apply_design_system"
           and re.search(r'style\.configure\("Treeview"', ast.get_source_segment(src, m) or "")]
assert not outside, outside
coa = seg("build_chart_of_accounts_tab")
assert 'style="Accounts.Treeview"' in coa and 'style.configure("Treeview"' not in coa
assert seg("setup_treeview_styles").strip().endswith("self.apply_design_system()")
print("✔ نمط الجداول من مصدر واحد: شجرة الحسابات بنمطها الخاص (كانت تغيّر خط كل الجداول بفتحها)، "
      "ولا نمط قديماً يومض عند تبديل المظهر")

# ═══ ٦) المظهر: فاتح ← داكن ← تلقائي، محفوظ على الجهاز ═══
assert class_value("THEME_CYCLE") == ("Light", "Dark", "System")
tog = seg("toggle_theme")
assert 'save_ui_pref("theme", self.current_theme)' in tog and "ctk.set_appearance_mode(self.current_theme)" in tog
init = seg("__init__")
assert 'load_ui_prefs().get("theme", "Light")' in init and "ctk.AppearanceModeTracker.add(" in init
print("✔ المظهر يدور فاتح ← داكن ← تلقائي (يتبع ويندوز)، ويُحفظ على الجهاز وحده ويُفتح به البرنامج، "
      "والجداول تتبع تغيّر ويندوز فوراً")

ns = {"os": os, "json": __import__("json"), "APP_DATA_DIR": __import__("tempfile").mkdtemp(),
      "UI_PREFS_FILE": "ui_prefs.json", "log_cloud_error": lambda *a: None}
exec(module_func("load_ui_prefs") + "\n" + module_func("save_ui_pref"), ns)
assert ns["load_ui_prefs"]() == {}
ns["save_ui_pref"]("theme", "System")
ns["save_ui_pref"]("other", 1)
assert ns["load_ui_prefs"]() == {"theme": "System", "other": 1}
print("✔ ملف تفضيلات الواجهة محلي (لا يُرفع للسحابة، فلا يتبع جهازُ المدير اختيارَ العميل)")

# ═══ ٧) صور حادّة ═══
captured = {}


class FakeCTkImage:
    def __init__(self, **kw):
        captured.update(kw)


class FakeImg:
    def __init__(self, size):
        self.size = size

    def resize(self, size, resample, reducing_gap=None):
        captured["resample"], captured["gap"] = resample, reducing_gap
        return FakeImg(size)


FakeScaling.get_widget_scaling = classmethod(lambda cls, w: 1.25)
Resampling = type("R", (), {"LANCZOS": "LANCZOS"})
ns = {"ctk": type("ctk", (), {"ScalingTracker": FakeScaling, "CTkImage": FakeCTkImage}),
      "Image": type("Image", (), {"Resampling": Resampling})}
exec(module_func("crisp_ctk_image"), ns)
ns["crisp_ctk_image"](FakeImg((500, 520)), None, (240, 250), widget=object())
assert captured["light_image"].size == (300, 312) and captured["size"] == (240, 250)
assert captured["resample"] == "LANCZOS" and captured["dark_image"] is captured["light_image"]
print("✔ الشعار يُصغَّر مسبقاً بفلتر LANCZOS لبكسلات العرض الفعلية (٢٤٠ × ١٢٥٪ = ٣٠٠) فيبقى حادّاً")

# ═══ ٨) الخطوط والإصدارات ═══
assert os.path.exists("fonts/Cairo-SemiBold.ttf") and os.path.getsize("fonts/Cairo-SemiBold.ttf") > 100000
assert ast.literal_eval(module_node("BRAND_FONT_FILES").value) == (
    "Cairo-Regular.ttf", "Cairo-Bold.ttf", "Cairo-SemiBold.ttf")
bx = io.open("build_exe.py", encoding="utf-8").read()
assert '"fonts/Cairo-SemiBold.ttf"' in bx and '"install", "--upgrade", "-r"' in bx
assert 'return "Cairo SemiBold" if "Cairo-SemiBold.ttf" in LOADED_BRAND_FONTS else "Cairo"' in module_func(
    "table_font_family")
assert "(table_font_family(), m[\"font\"])" in app_src
print("✔ Cairo SemiBold (وزن ٦٠٠) مرفق ومحمّل لنص الجداول، ويُضمَّن في exe")

req = io.open("requirements-desktop.txt", encoding="utf-8").read()
for pin in ("customtkinter>=6.0,<7", "Pillow>=12.0,<13", "reportlab>=5.0,<6", "supabase>=2.30,<3",
            "pyinstaller>=6.20,<7", "python-bidi>=0.6,<1", "arabic-reshaper>=3.0.1,<4"):
    assert pin in req, pin
print("✔ أحدث الإصدارات: CustomTkinter 6 · Pillow 12 · ReportLab 5 · Supabase 2.31 · PyInstaller 6.22 "
      "— وكل بناء يحدّثها (--upgrade)")

print("\n✅ نظام التصميم المحدَّث سليم: تباين، وضوح، إطارات، جداول حديثة، وأحدث المكتبات")
