# -*- coding: utf-8 -*-
"""اختبار: لا اهتزاز ولا «تكوّن» عند فتح النظام أو أي شاشة"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) الأعمدة تُضبط قبل أول رسم ═══
fit = seg("fit_columns_to_content")
assert "avail = self.expected_table_width()" in fit
print("✔ عرض الجدول يُقدَّر قبل ظهوره — الأعمدة صحيحة من أول رسم")
assert "tree.after(120, lambda: self.fit_columns_to_content" not in fit
print("✔ أُزيلت إعادة الضبط المؤجَّلة (كانت تُرى كقفز للأعمدة بعد الظهور)")

exp = seg("expected_table_width")
ns = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(exp), "    ")
     + "\n    def __init__(self, w, sb): self._w, self._sb = w, sb\n"
     "    def winfo_width(self): return self._w\n"
     "    def winfo_screenwidth(self): return 1920\n"
     "    def sidebar_width(self): return self._sb\n", ns)
S = ns["S"]
assert S(1920, 330).expected_table_width() == 1530
assert S(1, 330).expected_table_width() == 1530   # نافذة لم تُرسم بعد → تُقدَّر من الشاشة
assert S(400, 330).expected_table_width() >= 600  # حدّ أدنى معقول
print("✔ التقدير سليم: نافذة مرسومة، أو غير مرسومة، أو ضيقة جداً")

assert "abs(new_w - last) < 40" in fit
print("✔ تغيّر العرض الطفيف لا يُعيد الضبط — لا اهتزاز عند الظهور")

# ═══ ٢) تجميد الرسم أثناء البناء ═══
fr = seg("frozen_redraw")
assert "winfo_viewable()" in fr and "finally" in fr
print("✔ الرسم يُجمَّد أثناء البناء ويُستأنف دائماً حتى عند الخطأ")

nav = seg("navigate_to_screen")
assert "with self.frozen_redraw():" in nav
i_build = nav.index("ensure_screen_built")
i_show = nav.index("self.tabview.show(name)")
i_with = nav.index("with self.frozen_redraw():")
assert i_with < i_build < i_show
print("✔ البناء والتحديث والعرض داخل تجميد واحد — الشاشة تظهر جاهزة دفعةً واحدة")

# ═══ ٣) النافذة الرئيسية ═══
init = seg("__init__")
for a, b in (("self.withdraw()", "self.create_layout()"),
             ("self.create_layout()", "self.deiconify()"),
             ("self.deiconify()", "_startup_first_calc")):
    assert init.index(a) < init.index(b), (a, b)
print("✔ النافذة مخفية حتى تكتمل الواجهة ثم تظهر جاهزة")
assert "self.recalculate_all()" not in init
print("✔ ولا حساب شامل داخل البناء — الظهور فوري")

print("\n✅ لا اهتزاز ولا تكوّن تدريجي")
