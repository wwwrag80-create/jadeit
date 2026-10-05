# -*- coding: utf-8 -*-
"""
مظهر حساب العميل عند فتحه من لوحة المدير = مظهر برنامج العميل نفسه (الدفعة ٢٥).

لوحة المدير نافذة Tk أولى، فهي «الجذر الافتراضي». فكان كل ما يُنشأ بلا master عند فتح
حساب عميل منها — أنماط الجداول (ttk.Style) والخطوط والصور والرسائل — يذهب إلى اللوحة
المخفية، فتظهر جداول العميل بالسمة الافتراضية القديمة (عناوين رصاصية وخط صغير وصفوف
متلاصقة). أُعيد إنتاجه على البرنامج الحقيقي: السمة «default» بدل «clam» وخط TkDefaultFont.
"""
import ast, io, re, sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)


def method(cls_name, name):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name))


# ═══ ١) أنماط الجداول والخطوط على نافذة البرنامج نفسها ═══
assert "ttk.Style()" not in src, "ttk.Style() بلا master يُطبَّق على الجذر الافتراضي (لوحة المدير)"
assert src.count("ttk.Style(self)") >= 2
print("✔ أنماط الجداول (السمة، الألوان، الخط، ارتفاع الصف، شريط الإجمالي) على نافذة البرنامج نفسها")

fonts = re.findall(r"tkfont\.Font\(([^)]*)\)", src)
assert fonts and all("root=" in f for f in fonts), [f for f in fonts if "root=" not in f]
print(f"✔ كل الخطوط المقيسة ({len(fonts)}) مربوطة بنافذتها — لا بالجذر الافتراضي")

assert 'style.theme_use("clam")' in src and "style = ttk.Style(self)" in src
print("✔ السمة «clam» القابلة للتخصيص تُضبط على نافذة البرنامج")

# ═══ ٢) فتح حساب عميل من لوحة المدير: البرنامج هو الجذر الافتراضي طوال جلسته ═══
if "class AdminPanel" in src:
    op = method("AdminPanel", "open_as_client")
    i_none = op.index("tk._default_root = None")
    i_app = op.index("GoldSystemApp(")
    i_loop = op.index("app.mainloop()")
    i_back = op.index("tk._default_root = self")
    assert i_none < i_app < i_loop < i_back and "finally:" in op[i_loop:i_back]
    print("✔ لوحة المدير ← فتح حساب عميل: البرنامج يصبح الجذر الافتراضي، وتعود اللوحة جذراً بعد إغلاقه (ولو بخطأ)")

login = method("LoginWindow", "try_login")
assert login.index("tk._default_root = None") < login.index("app = GoldSystemApp(")
print("✔ والدخول بحساب العميل كما كان: البرنامج الجذر الافتراضي")

print("\n✅ حساب العميل من لوحة المدير بمظهر البرنامج نفسه: الجداول والخطوط والإطارات")
