# -*- coding: utf-8 -*-
"""اختبار قالب الطباعة: سند رقم التشغيل بقالب المصنع الورقي (الدفعة ٢١) —
رقم التشغيل (NO) وجدول «الوزن النهائي» (set_voucher_values)، وبقية الخانات من set_voucher_sections
(تتبع رقم التشغيل + سطر بيعه — 1.74)"""
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

# ═══ ٢) القالب يقرأ قيمه من مصدرين محسوبين فقط (لا حساب داخل الرسم) ═══
reads = re.findall(r'data\.get\("(\w+)"', tpl)
assert reads == ["set_number"], reads
assert tpl.count("self.set_voucher_values(data)") == 1 and tpl.count("self.set_voucher_sections(data)") == 1
print("✔ القالب يقرأ رقم التشغيل وحده من بيانات الطقم؛ «الوزن النهائي» من set_voucher_values، "
      "وبقية الخانات من set_voucher_sections")

assert 'cell(left + 17 * MM, t0 + 6 * MM, left + 66 * MM, t1 - 6 * MM, str(data.get("set_number") or ""), WHITE' in tpl
print("✔ رقم التشغيل في الخانة البيضاء بجوار NO أعلى السند")

assert 'f"{value:.2f}"' in tpl and "fit_font_size(label" in tpl
print("✔ كل قيمة بخانتين عشريتين، وكل نص يتقلّص داخل خانته فلا يخرج عنها")

# ═══ ٣) أقسام النموذج الورقي كلها مرسومة (فارغة للتعبئة اليدوية) ═══
for part in ("مصنع جاديت", "NO:", ":DATE", ":NAME", "رقم الموديل:", "اسم العميل:", "النوع:", "اسم المركب:",
             '"التصنيع"', '"البوليش"', '"التركيب"', '"بوليش 2"', '"0.08%"', '"0.04%"', '"خياس"',
             '"السلسال"', '"الوزن الأجمالي:"', '"الوزن النهائي"', '"الاجمالي"', '"الأجمالي"',
             '"الوزن المقيد"', "range(18)", "توقيع المدير", "توقيع المحاسب", "توقيع مدير الانتاج"):
    assert part in tpl, part
print("✔ كل أقسام النموذج الورقي مرسومة: التصنيع، البوليش، التركيب، بوليش 2 («التلميع النهائي» سابقاً)، جدول القطع ١–١٨، "
      "الإجماليات، التوقيعات")
assert '"التلميع النهائي"' not in tpl

# ═══ ٤) الصفحة كاملة: هامش متساوٍ، وعمودان بعرض واحد ينتهيان على سطر واحد فوق التوقيعات ═══
import sys, types
layout_fn = method("set_voucher_layout")
exec(compile(ast.Module(body=[layout_fn], type_ignores=[]), "set_voucher_layout", "exec"), ns)
fake = types.SimpleNamespace(VOUCHER_MARGIN_MM=10.0)
L = ns["set_voucher_layout"](fake)
MM, PW, PH, M = L["MM"], L["PW"], L["PH"], L["M"]
close = lambda a, b: abs(a - b) < 0.01
assert close(M, 10 * MM) and close(L["left"], M) and close(PW - L["right"], M) and close(L["head"][0], M)
(cl0, cl1), (cr0, cr1) = L["col_left"], L["col_right"]
assert close(cl0, M) and close(cr1, PW - M) and close(cl1 - cl0, cr1 - cr0) and close(cr0 - cl1, 6 * MM)
span = L["body_bottom"] - L["body_top"]
assert close(20 * L["r"] + 4 * L["v"] + 4 * L["g"], span), "المراحل تنتهي على سطر نهاية العمودين"
assert close(8 * L["r"] + 18 * L["p"] + 2 * L["g"], span), "جدول القطع والإجماليات تنتهي على السطر نفسه"
assert close(L["body_bottom"] + 20 * MM + M, PH) and close(L["sig_line"], PH - M - 9 * MM)
assert 7 * MM < L["r"] < 8.5 * MM and 7 * MM < L["p"] < 8.5 * MM and L["v"] > 9 * MM, (L["r"] / MM, L["p"] / MM)
print(f"✔ هامش 10 مم من الجهات الأربع؛ عمودان بعرض {(cl1 - cl0) / MM:.0f} مم ينتهيان معاً فوق التوقيعات؛ "
      f"الصف {L['r'] / MM:.1f} مم، وصف القطعة {L['p'] / MM:.1f} مم، وخانة الكتابة {L['v'] / MM:.1f} مم")

# الرسم الفعلي على لوحة وهمية: كل الخانات داخل الهوامش، ويملأ الصفحة طولاً وعرضاً
rects, lines = [], []


drawn = []


class Canvas:
    def rect(self, x, y, w, h, **k): rects.append((x, y, x + w, y + h))
    def line(self, x0, y0, x1, y1): lines.append((x0, y0, x1, y1))
    def drawCentredString(self, x, y, s): drawn.append(s)
    drawRightString = drawString = drawCentredString
    def __getattr__(self, name): return lambda *a, **k: None


if "reportlab.lib.colors" not in sys.modules:
    try:
        import reportlab.lib.colors  # noqa: F401
    except ImportError:              # فحص CI بلا reportlab: لون بديل يكفي للرسم الوهمي
        mod = types.ModuleType("reportlab.lib.colors"); mod.Color = lambda *a: a
        sys.modules.update({"reportlab": types.ModuleType("reportlab"), "reportlab.lib": types.ModuleType("reportlab.lib"),
                            "reportlab.lib.colors": mod})
draw_fn = method("draw_set_voucher_page")
ns.update(re=re, ar=lambda t: t, fit_font_size=lambda *a, **k: a[2], _ARABIC_FONT_NAME="f", _ARABIC_FONT_BOLD_NAME="b")
exec(compile(ast.Module(body=[draw_fn, method("set_voucher_sections")], type_ignores=[]), "voucher", "exec"), ns)
fake.set_voucher_layout = lambda: ns["set_voucher_layout"](fake)
fake.set_voucher_values = lambda d: ns["set_voucher_values"](fake, d)
fake.set_voucher_sections = lambda d: ns["set_voucher_sections"](fake, d)
fake.set_tracking_values = lambda k: {"polish_before": 33.6, "polish_after": 33.0, "polish_khayas": 0.6,
                                      "asm_before": 33.0, "asm_after": 32.5, "asm_khayas": 0.5, "names": ["سالم"]}
fake.pdf_logo = lambda: None
fake.get_display_label = lambda k: "بوليش 2"
ns["draw_set_voucher_page"](fake, Canvas(), {"set_number": "88001", "gold": 35.25, "gems": 2.5, "stones": 3.0,
                                             "stones_discount": "0.90", "diamond": 0.4, "khayas": 0.6,
                                             "invoice_no": 7, "name": "المصنع", "date": "2026-10-05 10:00:00",
                                             "kind": "الماس"})
for value in ("33.60", "33.00", "0.60", "32.50", "0.50", "38.40", "3.35", "41.75", "41.15", "39.05", "30%",
              "سالم", "المصنع", "2026-10-05", "الماس", "88001"):
    assert value in drawn, (value, drawn)
print("✔ الرسم الفعلي يكتب القيم في خاناتها: البوليش 33.60/33.00/0.60، التركيب 33.00/32.50/0.50، الوزن بعد 38.40، "
      "السلسال 3.35، الإجمالي 41.75، بوليش 2 41.75/41.15/0.60، المقيد 39.05، ونسبة الأحجار 30%")
xs = [v for r_ in rects for v in (r_[0], r_[2])]
ys = [v for r_ in rects for v in (r_[1], r_[3])]
assert close(min(xs), M) and close(max(xs), PW - M) and close(max(ys), PH - M), (min(xs), max(xs), max(ys))
bottom = PH - L["body_bottom"]
assert close(min(ys), bottom), (min(ys), bottom)
left_bottom = min(r_[1] for r_ in rects if r_[2] <= cl1 + 0.01)
right_bottom = min(r_[1] for r_ in rects if r_[0] >= cr0 - 0.01)
assert close(left_bottom, bottom) and close(right_bottom, bottom), (left_bottom, right_bottom, bottom)
sig = [ln for ln in lines if close(ln[1], PH - L["sig_line"])]
assert len(sig) == 3 and close(min(min(x0, x1) for x0, _y, x1, _y2 in sig), M + ((PW - 2 * M) / 3) / 2 - 28 * MM)
print("✔ الرسم الفعلي: كل الخانات داخل الهوامش وتصل إليها من الجهات الأربع، والعمودان ينتهيان معاً، والتوقيعات الثلاثة أسفلها")

print("\n✅ قالب سند رقم التشغيل: أقسام النموذج الورقي كلها على صفحة A4 كاملة ومرتبة")
