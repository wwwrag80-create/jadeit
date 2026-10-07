# -*- coding: utf-8 -*-
"""أزرار أقسام شاشة صناديق الخياس: مدمجة وتلتفّ على أكثر من سطر — أي عدد من الأقسام
يظهر كاملاً بلا تمدّد للواجهة، من اليمين لليسار — يشغّل الدوال الحقيقية"""
import ast, io, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
lines = src.split("\n")
APP = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def seg(name):
    node = next(m for m in APP.body if isinstance(m, ast.FunctionDef) and m.name == name)
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


ns = {}
exec("class A:\n" + "\n".join(textwrap.indent(seg(m), "    ") for m in
                               ("khayas_category_columns", "layout_khayas_category_buttons")) +
     "\n    def winfo_width(self): return 1366\n    def sidebar_width(self): return 220\n", ns)


class Bar:
    def __init__(self, w):
        self.w, self.cols = w, {}

    def winfo_width(self):
        return self.w

    def grid_columnconfigure(self, c, **k):
        self.cols[c] = k


class Btn:
    def __init__(self, name):
        self.name, self.pos, self.grids = name, None, 0

    def winfo_reqwidth(self):
        return 100

    def grid(self, row, column, **k):
        self.pos, self.grids = (row, column), self.grids + 1


a = ns["A"]()
names = ["الكاستنج", "المصنعين", "المركبين", "التلميع", "البوليش", "النهائي",
         "صب داخلي", "بوليش ١", "بوليش ٢", "قسم ١٠", "قسم ١١", "قسم ١٢"]
a.khayas_category_bar = Bar(640)
a.khayas_category_buttons = {n: Btn(n) for n in names}
a.layout_khayas_category_buttons()
b = a.khayas_category_buttons
assert a._khayas_cat_cols == 6
assert b["الكاستنج"].pos == (0, 5) and b["النهائي"].pos == (0, 0) and b["صب داخلي"].pos == (1, 5)
assert b["قسم ١٢"].pos == (1, 0)
print("✔ ١٢ قسماً في عرض ٦٤٠: ستة في كل سطر على سطرين — كلها ظاهرة، والأول في أقصى اليمين")

a.layout_khayas_category_buttons()
assert all(x.grids == 1 for x in b.values())
print("✔ لا إعادة رصف ما دام عدد الأعمدة لم يتغيّر (لا اهتزاز عند كل حدث تحجيم)")

a.khayas_category_bar.w = 1300
a.layout_khayas_category_buttons()
assert a._khayas_cat_cols == 12 and b["قسم ١٢"].pos == (0, 0)
print("✔ على شاشة أعرض تعود الأقسام الاثنا عشر إلى سطر واحد")
assert a.khayas_category_columns(300, [100, 100]) == 2 and a.khayas_category_columns(50, [100] * 5) == 1
# عرض كل عمود = أطول زر فيه وحده: أزرار قصيرة مع زر طويل واحد تتّسع لسطر أطول
# في ٧٠٠: ستة تحتاج 236 + 5×106 = 766، وخمسة 236 + 4×106 = 660 ← خمسة في السطر
# (قاعدة «كلها بعرض أطولها» كانت تعطي 700 ÷ 236 = اثنين فقط)
assert a.khayas_category_columns(700, [230, 100, 100, 100, 100, 100]) == 5
assert a.khayas_category_columns(800, [230, 100, 100, 100, 100, 100]) == 6
print("✔ كل عمود بعرض أطول زر فيه وحده — فيتّسع السطر لأكثر عدد ممكن من الأقسام")

body = seg("refresh_khayas_category_buttons")
assert 'font=(UI_FONT, 13, "bold")' in body and "height=32" in body and "b.pack(" not in body
assert 'self.khayas_category_bar.bind("<Configure>", self.layout_khayas_category_buttons)' in seg("build_inquiries_tab")
print("✔ الأزرار مدمجة (خط ١٣، ارتفاع ٣٢ بدل ١٦ و٤٥) وتُرصف من جديد عند تغيّر عرض الشاشة")
print("\n✅ أزرار أقسام صناديق الخياس تتّسع لأي عدد")
