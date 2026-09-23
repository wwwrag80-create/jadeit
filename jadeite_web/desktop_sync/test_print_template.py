# -*- coding: utf-8 -*-
"""اختبار قالب الطباعة: جدول الوزن النهائي ورقم التشغيل"""
import ast, io, re

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
tpl = None
for m in cls.body:
    if isinstance(m, ast.FunctionDef):
        b = ast.get_source_segment(src, m)
        if "materials_fill" in b:
            tpl = b
            break
assert tpl, "لم يُعثر على دالة القالب"

# ═══ ١) ترتيب صفوف جدول الوزن النهائي ═══
# نقصر البحث على كتلة materials_fill وحدها (هناك جداول أخرى بنفس الشكل)
block = tpl[tpl.index("materials_fill = {"):tpl.index("draw_mini_table(M, row3_top")]
order = re.findall(r'^\s*(\d+): \{0: ', block, re.M)
labels = re.findall(r'^\s*\d+: \{0: f?"([^"]+)"', block, re.M)
top5 = [(i, labels[i]) for i in range(5)]
expected = [(0, "الوزن النهائي"), (1, "ناقص فصوص"), (2, "ناقص احجار"),
            (3, "ناقص الماس"), (4, "الوزن الصافي")]
assert top5 == expected, top5
print("✔ ترتيب الجدول مطابق للنموذج الورقي من الأعلى للأسفل:")
for _i, lbl in top5:
    print(f"   • {lbl}")

# ═══ ٢) ربط كل صف بخانته ═══
pairs = {
    "الوزن الصافي": "gold",
    "ناقص الماس": "diamond",
    "ناقص احجار": "stones",
    "ناقص فصوص": "gems",
}
for label, var in pairs.items():
    m = re.search(r'\{0: "' + re.escape(label) + r'", 1: f"\{(\w+):', block)
    assert m and m.group(1) == var, (label, m.group(1) if m else None)
    print(f"✔ {label:14} ← خانة {var}")

# ═══ ٣) الوزن النهائي = مجموع الأربعة ═══
assert "final_weight = round(gold + diamond + stones + gems, 2)" in tpl
assert re.search(r'\{0: "الوزن النهائي", 1: f"\{final_weight:', block)
print("✔ الوزن النهائي = الذهب + الماس + الأحجار + الفصوص")

gold, diamond, stones, gems = 100.0, 3.0, 20.0, 5.0
assert round(gold + diamond + stones + gems, 2) == 128.0
print(f"   مثال: {gold} + {diamond} + {stones} + {gems} = 128.00")

# ═══ ٤) رقم التشغيل في خانة NO أعلى الصفحة ═══
i_no = tpl.find('set_no_txt = str(data.get("set_number")')
i_tbl = tpl.find("materials_fill")
assert i_no != -1 and i_no < i_tbl, "رقم التشغيل غير مرسوم في الرأس"
assert 'txt(M + 16 * mm' in tpl and "set_no_txt" in tpl
print("✔ رقم التشغيل يُطبع في الخانة البيضاء أعلى الصفحة (NO)")
assert "fit_font_size(set_no_txt" in tpl
print("✔ وحجم خطه يتقلّص تلقائياً لو طال الرقم فلا يخرج عن خانته")

# ═══ ٥) عدد الصفوف يطابق الخريطة ═══
n_rows = int(re.search(r'"الوزن النهائي", materials_cols, (\d+), row_h', tpl).group(1))
assert n_rows == len(order), (n_rows, len(order))
print(f"✔ عدد صفوف الجدول ({n_rows}) مطابق لعدد البنود المعرّفة")

print("\n✅ قالب الطباعة مطابق للنموذج المرفق")
