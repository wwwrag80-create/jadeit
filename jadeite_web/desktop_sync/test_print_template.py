# -*- coding: utf-8 -*-
"""اختبار قالب الطباعة: سند رقم التشغيل بقالب المصنع الورقي (الدفعة ٢١) —
لا يُعبّأ منه إلا رقم التشغيل (NO) وجدول «الوزن النهائي»"""
import ast, io, re

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def method(name):
    fn = next((m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name), None)
    assert fn is not None, f"{name} مفقودة"
    return fn


tpl = ast.get_source_segment(src, method("draw_set_voucher_page"))
values_fn = method("set_voucher_values")

# ═══ ١) القيم الخمس بترتيب النموذج الورقي من الأعلى للأسفل ═══
ns = {}
exec(compile(ast.Module(body=[values_fn], type_ignores=[]), "set_voucher_values", "exec"), ns)
gold, gems, stones, diamond = 100.0, 5.0, 20.0, 3.0
rows = ns["set_voucher_values"](None, {"gold": gold, "gems": gems, "stones": stones, "diamond": diamond,
                                       "khayas": 9.0, "stones_discount": "18"})
expected = [("الوزن النهائي", 128.0), ("ناقص فصوص", 5.0), ("ناقص احجار", 20.0),
            ("ناقص الماس", 3.0), ("الوزن الصافي", 100.0)]
assert rows == expected, rows
print("✔ جدول الوزن النهائي بترتيب النموذج الورقي:")
for label, value in rows:
    print(f"   • {label:14} = {value:.2f}")
print("✔ الوزن النهائي = الوزن القائم (ذهب + فصوص + أحجار + ماس) — لا خياس ولا خصم أحجار")

empty = ns["set_voucher_values"](None, {"gold": None})
assert [v for _l, v in empty] == [0.0] * 5, empty
print("✔ القيم الناقصة تُطبع 0.00 بلا خطأ")

# ═══ ٢) لا يُعبّأ غير رقم التشغيل وجدول الوزن النهائي ═══
reads = re.findall(r'data\.get\("(\w+)"', tpl)
assert reads == ["set_number"], reads
assert tpl.count("self.set_voucher_values(data)") == 1
print("✔ القالب لا يقرأ من بيانات الطقم إلا رقم التشغيل، وقيمه الخمس من set_voucher_values وحدها")

assert 'cell(290, 172, 460, 218, str(data.get("set_number")' in tpl
print("✔ رقم التشغيل في الخانة البيضاء بجوار NO أعلى السند")

assert 'f"{value:.2f}"' in tpl and "fit_font_size(label" in tpl
print("✔ كل قيمة بخانتين عشريتين، وكل نص يتقلّص داخل خانته فلا يخرج عنها")

# ═══ ٣) أقسام النموذج الورقي كلها مرسومة (فارغة للتعبئة اليدوية) ═══
for part in ("مصنع جاديت", "NO:", ":DATE", ":NAME", "رقم الموديل:", "اسم العميل:", "النوع:", "اسم المركب:",
             '"التصنيع"', '"البوليش"', '"التركيب"', '"التلميع النهائي"', '"0.08%"', '"0.04%"', '"خياس"',
             '"السلسال"', '"الوزن الأجمالي:"', '"الوزن النهائي"', '"الاجمالي"', '"الأجمالي"',
             '"الوزن المقيد"', "range(18)", "توقيع المدير", "توقيع المحاسب", "توقيع مدير الانتاج"):
    assert part in tpl, part
print("✔ كل أقسام النموذج الورقي مرسومة: التصنيع، البوليش، التركيب، التلميع النهائي، جدول القطع ١–١٨، "
      "الإجماليات، التوقيعات")

# ═══ ٤) مقاس الصفحة: صورة النموذج ١٤٥٠ بكسل = عرض A4 ═══
assert "VOUCHER_PX_W = 1450.0" in src and "k = PW / self.VOUCHER_PX_W" in tpl
print("✔ إحداثيات القالب من صورة النموذج نفسها مُحجّمة إلى صفحة A4")

print("\n✅ قالب سند رقم التشغيل مطابق للنموذج الورقي المرفق")
