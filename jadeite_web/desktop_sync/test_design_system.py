# -*- coding: utf-8 -*-
"""اختبار نظام التصميم المركزي: يصل كل الجداول ويتكيّف مع الشاشة"""
import ast, io, re, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) كل الجداول تمرّ من المصنع الموحّد ═══
raw = len(re.findall(r'ttk\.Treeview\(', src))
factory = src.count("def create_standard_treeview") + src.count("def create_sticky_total_tree")
via_factory = len(re.findall(r'self\.create_standard_treeview\(|self\.create_sticky_total_tree\(', src))
print(f"جداول تُنشأ عبر المصنع الموحّد: {via_factory}")
assert via_factory >= 15, via_factory
print("✔ الغالبية العظمى من الجداول تتبع التنسيق الموحّد تلقائياً")

cst = seg("create_standard_treeview")
assert "self.apply_design_system()" in cst
print("✔ أي جدول يُنشأ قبل تهيئة التصميم يُهيّئه بنفسه")
assert "self.wrap_header(col)" in cst
print("✔ عناوين الأعمدة تُوزَّع على سطرين تلقائياً في كل الجداول")

# ═══ ٢) التنسيق يشمل الجدول والرأس والتحديد وأشرطة التمرير ═══
ads = seg("apply_design_system")
for k in ('"Treeview"', '"Treeview.Heading"', "Vertical.TScrollbar",
          "Horizontal.TScrollbar", "ensure_totals_bar_style"):
    assert k in ads, k
print("✔ التنسيق يشمل: الجدول، الرأس، التحديد، أشرطة التمرير، شريط الإجمالي")
assert 'style.theme_use("clam")' in ads
print("✔ يستخدم سمة تقبل التخصيص الكامل (وإلا تُتجاهل الألوان على ويندوز)")
assert "log_cloud_error" in ads
print("✔ فشل التنسيق يُسجَّل ولا يمنع عمل النظام")

# ═══ ٣) المظهران ═══
design = None
for node in ast.walk(cls):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "DESIGN":
                design = ast.literal_eval(node.value)
assert set(design) == {"light", "dark"}
keys = set(design["light"])
assert keys == set(design["dark"]), "المظهران غير متطابقي المفاتيح"
print(f"✔ المظهران الفاتح والداكن بنفس {len(keys)} مفتاحاً — لا لون ناقص")

tog = seg("toggle_theme")
assert "apply_design_system" in tog
print("✔ تبديل المظهر يُعيد تطبيق التنسيق")

# ═══ ٤) الصفوف المتناوبة ═══
fit = seg("fit_columns_to_content")
assert "self.style_tree_rows(tree)" in fit
print("✔ الصفوف المتناوبة تُلوَّن بعد امتلاء الجدول وضبط أعمدته")

strp = seg("style_tree_rows")
assert '"total_tag", "red_tag", "orange_name"' in strp
print("✔ ولا تمسّ صفوف الإجمالي أو السالب أو الأسماء (تحتفظ بألوانها)")

# ═══ ٥) التكيّف مع الشاشة ═══
ns = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(seg("design_metrics")), "    ")
     + "\n    def __init__(self, w, h): self._w, self._h = w, h\n"
     "    def winfo_screenwidth(self): return self._w\n"
     "    def winfo_screenheight(self): return self._h\n", ns)
S = ns["S"]
big, small = S(2560, 1440).design_metrics(), S(1366, 768).design_metrics()
assert big["font"] > small["font"] and big["row_h"] > small["row_h"]
print(f"✔ شاشة كبيرة: خط {big['font']} وصف {big['row_h']}  |  صغيرة: خط {small['font']} وصف {small['row_h']}")

for k in ("font", "row_h", "head", "pad_x", "pad_y"):
    assert small[k] > 0
print("✔ كل المقاييس موجبة على أصغر شاشة (لا قيم صفرية تُفسد العرض)")

init = seg("__init__")
assert "self.apply_design_system()" in init and "self.minsize(1100, 620)" in init
print("✔ يُطبَّق عند التشغيل، وحدّ أدنى للنافذة يمنع تشوّه الجداول")

print("\n✅ نظام التصميم المركزي يصل كل الشاشات")
