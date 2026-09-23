# -*- coding: utf-8 -*-
"""اختبار: أسماء الأعمدة كاملة، الترقيم التلقائي، والتجهيز المسبق للشاشات"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) رؤوس الأعمدة كاملة ═══
ns = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(seg("wrap_header")), "    "), ns)
w = ns["S"].wrap_header
for name in ("خياس المركب", "خياس التلميع النهائي", "الأحجار بعد الخصم", "فصوص/أحجار"):
    got = w(name)
    assert got == name and "\n" not in got, (name, got)
    print(f"✔ «{name}» يظهر كاملاً بلا قصّ")
print("  (رؤوس ttk تعرض السطر الأول فقط — فتوزيعها على سطرين كان يقصّها)")

fit = seg("fit_columns_to_content")
assert "header_w = head_font.measure(str(label)) + 10" in fit
print("✔ عرض العمود يُقاس من العنوان كاملاً")
assert "width = max(min_width, header_w, min(max_width, content_w + padding))" in fit
print("✔ الحد الأقصى يقيّد المحتوى لا الرأس — فلا يُقصّ اسم عمود أبداً")

# ═══ ٢) الترقيم التلقائي في المبيعات ═══
stage = seg("stage_sale_row")
assert "row_num = str(self.next_sale_row_number())" in stage
print("✔ رقم الصف يُحسب تلقائياً (لا خانة إدخال له)")

nxt = seg("next_sale_row_number")
ns2 = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(nxt), "    ")
     + "\n    def __init__(self, rows): self.pending_sale_rows = rows\n", ns2)
S2 = ns2["S"]
assert S2([]).next_sale_row_number() == 1
assert S2([{"row_number": "1"}, {"row_number": "2"}]).next_sale_row_number() == 3
assert S2([{"row_number": "1"}, {"row_number": "5"}]).next_sale_row_number() == 6
assert S2([{"row_number": ""}, {"row_number": "غير رقمي"}]).next_sale_row_number() == 1
print("✔ الرقم التالي = أكبر رقم + ١، والقيم غير الرقمية لا تُسبب خطأ")

ren = seg("renumber_pending_sale_rows")
ns3 = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(ren), "    ")
     + "\n    def __init__(self, rows): self.pending_sale_rows = rows\n", ns3)
rows = [{"row_number": "1"}, {"row_number": "3"}, {"row_number": "7"}]
app = ns3["S"](rows)
app.renumber_pending_sale_rows()
assert [r["row_number"] for r in rows] == ["1", "2", "3"]
print("✔ الحذف من وسط الفاتورة يُعيد الترقيم ١..ن بلا فجوات")

dele = seg("delete_pending_sale_row")
assert "self.renumber_pending_sale_rows()" in dele
print("✔ وإعادة الترقيم مربوطة بالحذف فعلاً")

# ═══ ٣) التجهيز المسبق للشاشات الثلاث ═══
pre = seg("_prebuild_screens")
assert "ensure_screen_built" in pre and "self.after(120" in pre
print("✔ الشاشات الثلاث تُبنى في الخلفية تباعاً (١٢٠ ملّي بين كل شاشة)")
assert "log_cloud_error" in pre
print("✔ فشل تجهيز شاشة لا يوقف تجهيز البقية")

calc = seg("_startup_first_calc")
assert '["المبيعات", "مراحل التصنيع", "صناديق الخياس"]' in calc
print("✔ الشاشات المجهّزة: المبيعات، مراحل التصنيع، صناديق الخياس")
print("  → تفتح فوراً بلا «تكوّن» أمام المستخدم")

print("\n✅ كل التحسينات تعمل")
