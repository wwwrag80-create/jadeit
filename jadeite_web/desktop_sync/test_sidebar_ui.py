# -*- coding: utf-8 -*-
"""اختبار الواجهة الجديدة: الشريط الجانبي وترتيبه وتكيّفه مع الشاشة"""
import ast, io, re, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) البنية: الشريط يمين وحاوية الشاشات يساره ═══
lay = seg("create_layout")
i_side = lay.find('self.sidebar.pack(side="right", fill="y")')
i_shell = lay.find('self.main_shell.pack(fill="both", expand=True')
assert i_side != -1 and i_shell != -1 and i_side < i_shell
print("✔ الشريط الجانبي على **اليمين**، وحاوية الشاشات تأخذ ما تبقّى")
assert "self.sidebar.pack_propagate(False)" in lay
print("✔ عرض الشريط ثابت لا ينكمش")

# الشاشات لم تُمسّ: ما زالت داخل main_shell
assert "ScreenRouter(self.main_shell" in lay
print("✔ الشاشات لم تُمسّ — تُبنى داخل main_shell كما كانت")

# ═══ ٢) الترتيب المطلوب ═══
prim = None
for node in ast.walk(cls):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "SIDEBAR_PRIMARY":
                prim = [x[0] for x in ast.literal_eval(node.value)]
expected = ["المبيعات", "مراحل التصنيع", "صناديق الخياس", "الوارد",
            "شاشة الخسائر", "صناديق المصنع"]
assert prim == expected, prim
print("✔ ترتيب الشاشات الأساسية مطابق للمطلوب:")
for i, n in enumerate(prim, 1):
    print(f"   {i}. {n}")

sec = None
for node in ast.walk(cls):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "SIDEBAR_SECONDARY":
                sec = [x[0] for x in ast.literal_eval(node.value)]
print(f"✔ زر (أخرى) يفتح {len(sec)} شاشة إضافية")

# كل الشاشات مغطاة
registered = set(re.findall(r'self\.tabview\.add\("([^"]+)"\)', src))
covered = set(prim) | set(sec)
missing = registered - covered
assert not missing, f"شاشات بلا زر في الشريط: {missing}"
print(f"✔ كل الشاشات الـ {len(registered)} لها أزرارها (لا شاشة بلا وصول)")
assert not (covered - registered), f"أزرار لشاشات غير مسجّلة: {covered - registered}"
print("✔ ولا زر يشير لشاشة غير موجودة")

# ═══ ٣) المظهر الزجاجي ═══
sb = seg("build_sidebar")
assert 'border_color="#2e86de"' in sb
print("✔ حواف زرقاء على الأزرار")
assert 'fg_color=("#ffffff", "#ffffff")' in sb
print("✔ خلفية بيضاء بالكامل في المظهرين")
assert "def glow" in sb and 'border_color="#5dade2"' in sb
print("✔ الحافة تلمع عند مرور الفأرة")
assert 'text=f"{icon}  {label}"' in sb
print("✔ لكل شاشة أيقونة واسم واضح")

# ═══ ٤) التكيّف مع حجم الشاشة ═══
ns = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(seg("sidebar_width")), "    ")
     + "\n" + textwrap.indent(textwrap.dedent(seg("ui_scale")), "    ")
     + "\n    def __init__(self, w): self._w = w\n"
     "    def winfo_screenwidth(self): return self._w\n", ns)
S = ns["S"]
for w, expect_w in ((1920, 330), (1600, 300), (1366, 268)):
    app = S(w)
    assert app.sidebar_width() == expect_w, (w, app.sidebar_width())
    assert 0.8 <= app.ui_scale() <= 1.0
    print(f"✔ شاشة {w}px → عرض الشريط {app.sidebar_width()} ومعامل {app.ui_scale()}")

# ═══ ٥) الشعار في المساحة الفارغة ═══
home = seg("build_home_screen")
assert 'logo_card.pack(fill="both", expand=True' in home
assert 'relx=0.5, rely=0.5, anchor="center"' in home
print("✔ بطاقة الشعار تملأ المساحة الفارغة")
assert "avail = self.winfo_screenwidth() - self.sidebar_width()" in home
print("✔ وحجم الشعار يُحسب بعد خصم عرض الشريط الجانبي")
assert "self.build_sidebar()" in home
print("✔ الشريط يُبنى مع الشاشة الرئيسية بعد تسجيل الشاشات")

print("\n✅ الواجهة الجديدة جاهزة")
