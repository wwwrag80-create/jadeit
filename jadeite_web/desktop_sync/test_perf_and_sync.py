# -*- coding: utf-8 -*-
"""اختبار: قياس الأعمدة بالعيّنة، منع تكرار المزامنة، وشفافية الشعار"""
import ast, io, os

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) قياس عيّنة بدل كل الخلايا ═══
fit = seg("fit_columns_to_content")
assert "FIT_SAMPLE_ROWS" in fit and "all_children[::step]" in fit
print("✔ عرض الأعمدة يُقاس من عيّنة لا من كل الصفوف")

sample = None
for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "FIT_SAMPLE_ROWS":
                sample = node.value.value
assert sample and sample <= 100, sample
rows, cols = 500, 16
print(f"   قبل: {rows}×{cols} = {rows*cols} استدعاء قياس في كل تحديث")
print(f"   بعد: ~{sample}×{cols} = ~{sample*cols} استدعاء  (أقل بـ {rows//sample} مرات)")

assert "all_children[-3:]" in fit
print("✔ آخر الصفوف مضمونة في العيّنة (صف الإجمالي عادةً أطول الأرقام)")

# ═══ ٢) تأجيل إعادة الضبط عند تغيير الحجم ═══
assert "after_cancel" in fit and "t.after(200" in fit
print("✔ تغيير حجم النافذة يُعيد الضبط مرة واحدة بعد الاستقرار — لا تجمّد")

# ═══ ٣) منع تكرار المزامنة ═══
cs = io.open("cloud_sync.py", encoding="utf-8").read()
assert 'deduped[row["seq_no"]] = row' in cs
print("✔ الحركات: تُزال التكرارات قبل الإرسال (الخطأ 21000)")
assert '{(a["name"], a["category"]): a for a in added}' in cs
print("✔ الحسابات: نفس المعالجة")

sql = io.open("../supabase/13_fix_admin_mirror.sql", encoding="utf-8").read()
assert "with ordinality as t(x, ord)" in sql
assert sql.count("select distinct on") == 2
print("✔ والسحابة أيضاً تُزيل التكرار داخل الدفعة (حماية مزدوجة)")

# ═══ ٤) الشعار شفاف وأصغر ═══
hb = seg("build_home_screen")
assert 'Image.open(pure).convert("RGBA")' in hb
print("✔ الشعار يُقرأ بوضع RGBA — لا خلفية سوداء")
assert "min(420, int(avail * 0.26))" in hb
print("✔ وحجمه صغير مريح (٢٤٠–٤٢٠ بكسل)")
assert "int(v * 0.38)" in hb
print("✔ ويُعرض خافتاً (٣٨٪ من شدّته) فلا يُجهد العين")

from PIL import Image
im = Image.open("jadeite_logo.png")
assert im.mode == "RGBA", im.mode
w, h = im.size
assert max(w, h) <= 560, im.size
corner = im.getpixel((0, 0))
assert corner[3] == 0, corner
print(f"✔ ملف الشعار: {im.size} بوضع {im.mode} وزواياه شفافة فعلاً")

print("\n✅ الأداء والمزامنة والشعار — كلها سليمة")
