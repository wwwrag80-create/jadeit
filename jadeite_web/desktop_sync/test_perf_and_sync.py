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

# ═══ ٣) منع تكرار المزامنة (في السحابة؛ الرفع صفاً صفاً أُزيل مع الويب — الدفعة ٢١) ═══
sql = io.open("../supabase/13_fix_admin_mirror.sql", encoding="utf-8").read()
assert "with ordinality as t(x, ord)" in sql
assert sql.count("select distinct on") == 2
print("✔ السحابة تُزيل التكرار داخل الدفعة")

# ═══ ٤) الشعار شفاف وأصغر ═══
hb = seg("build_home_screen")
assert 'Image.open(pure).convert("RGBA")' in hb
print("✔ الشعار يُقرأ بوضع RGBA — لا خلفية سوداء")
assert "min(420, int(avail * 0.26))" in hb
print("✔ وحجمه صغير مريح (٢٤٠–٤٢٠ بكسل)")
# الشعار بلون الشريط البارز «رصيد الخزينة الحالي» نفسه (بطلب العميل)
assert "logo_tint_for(TREASURY_BAR_TEXT[0])" in hb and "logo_tint_for(TREASURY_BAR_TEXT[1]" in hb
assert "opacity=" not in hb.split("logo_tint_for(TREASURY_BAR_TEXT[0])")[1].split("\n")[0]
_bar_line = next(l for l in src.splitlines() if "self.lbl_live_treasury = ctk.CTkLabel(" in l)
assert "text_color=TREASURY_BAR_TEXT)" in _bar_line, _bar_line
print("✔ الشعار والشريط يأخذان لونهما من ثابت واحد (TREASURY_BAR_TEXT) — لا يفترقان مستقبلاً")

import re as _re
from PIL import Image
_ns = {}
exec("\n".join(ast.get_source_segment(src, n) for n in ast.parse(src).body
               if isinstance(n, ast.FunctionDef) and n.name in ("shade_color", "logo_tint_for", "tint_logo")), _ns)
_ui = dict(_re.findall(r'"(gold_dark|gold_soft)": "(#[0-9A-Fa-f]{6})"', src))
_bar = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign)
            and getattr(n.targets[0], "id", "") == "TREASURY_BAR_TEXT")
_bar = eval(ast.get_source_segment(src, _bar.value), {"UI": _ui})
assert _bar[0] == _ui["gold_dark"] == "#9C7A12", _bar


def _mean(img):
    from PIL import ImageStat
    opaque = img.getchannel("A").point(lambda v: 255 if v > 200 else 0)
    return tuple(round(v) for v in ImageStat.Stat(img.convert("RGB"), mask=opaque).mean)


_logo = Image.open("jadeite_logo.png").convert("RGBA")
for mode, color, args in (("الفاتح", _bar[0], ()), ("الداكن", _bar[1], (0.90, 1.10))):
    want = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    got = _mean(_ns["tint_logo"](_logo, *_ns["logo_tint_for"](color, *args)))
    assert max(abs(a - b) for a, b in zip(got, want)) <= 8, (mode, got, want)
    print(f"✔ الوضع {mode}: متوسط لون الشعار #{''.join(f'{v:02X}' for v in got)} ≈ لون الشريط {color}")

im = Image.open("jadeite_logo.png")
assert im.mode == "RGBA", im.mode
w, h = im.size
assert max(w, h) <= 560, im.size
corner = im.getpixel((0, 0))
assert corner[3] == 0, corner
print(f"✔ ملف الشعار: {im.size} بوضع {im.mode} وزواياه شفافة فعلاً")

print("\n✅ الأداء والمزامنة والشعار — كلها سليمة")
