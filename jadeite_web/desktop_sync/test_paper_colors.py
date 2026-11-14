# -*- coding: utf-8 -*-
"""1.93: ألوان «قالب رقم التشغيل» كالقالب الورقي — على الشاشة وفي السند المطبوع، من لوحة ألوان واحدة:
  أخضر: الرأس وعناوين الأقسام وعناوين «الوزن بعد / السلسال / الوزن الإجمالي»؛ بنفسجي فاتح: عناوين الأعمدة
  وفصوص/احجار/الماس وعناوين الوزن النهائي وجدول القطع والإجماليات؛ كريمي: عناوين بيانات الطقم؛ بيج وردي:
  خانات الخياس؛ وخانات الإدخال بيضاء."""
import ast, io, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))


def member(name):
    return textwrap.dedent(ast.get_source_segment(src, node(name)))


colors = ast.literal_eval(node("SET_PAPER_COLORS").value)
assert set(colors) == {"green", "lavender", "cream", "khayas"}
for name, h in colors.items():
    assert len(h) == 7 and h.startswith("#") and int(h[1:], 16) >= 0
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    assert (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 >= 0.7, f"{name}: لونٌ فاتح يُقرأ عليه النص الأسود ({h})"
assert colors["green"][3:5] > colors["green"][1:3], "الأخضر أخضر"
paper_src = member("SB_PAPER")
for key in ("green", "lavender", "cream", "khayas"):
    assert f'"{key}": SET_PAPER_COLORS["{key}"]' in paper_src
print("✔ لوحة ألوان واحدة (SET_PAPER_COLORS) للشاشة والسند المطبوع، كلها فاتحة يُقرأ عليها النص")

# ═══ الشاشة: لون كل عنوان وخانة في الورقة المرسومة ═══
ns = {"BRAND_KEY": "brand_identity", "json": __import__("json"), "sqlite3": __import__("sqlite3")}     # هوية المصنع (1.98): رأس القالب
exec("class Paper:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in (
    "VOUCHER_MARGIN_MM", "set_voucher_layout", "SB_CELL_KINDS", "SB_PIECE_ROWS", "SB_PIECE_COLS",
    "SB_KHAYAS_KEYS", "sb_paper_spec", "BRAND_FIELDS", "BRAND_DEFAULT", "_brand_setting", "brand_identity")), ns)
spec = ns["Paper"]().sb_paper_spec()
assert spec[0][0] == "box" and spec[0][5] == "green", "الرأس (مصنع جاديت) أخضر"
fill_of_text, fill_of_cell = {}, {}
for i, el in enumerate(spec):
    if el[0] == "text" and i and spec[i - 1][0] == "box":
        fill_of_text.setdefault(el[3], set()).add(spec[i - 1][5])
    if el[0] in ("cell", "calc") and i and spec[i - 1][0] == "box":
        fill_of_cell[el[1]] = spec[i - 1][5]
for text in ("التصنيع", "البوليش", "التركيب", "بوليش 2", "الاجمالي", "الأجمالي", "الوزن بعد", "السلسال",
             "الوزن الأجمالي:"):
    assert fill_of_text[text] == {"green"}, (text, fill_of_text[text])
assert fill_of_text["الوزن النهائي"] == {"green", "lavender"}, "عنوان القسم أخضر، وسطره في جدوله بنفسجي"
for text in ("0.08%", "0.04%", "قبل", "بعد", "خياس", "فصوص", "احجار", "الماس", "ناقص فصوص", "ناقص احجار",
             "ناقص الماس", "الوزن الصافي", "الوزن المقيد", "الاحجار %", "العدد", "المقاس", "النوع", "الوزن",
             "البيان", "فصوص:", "احجار:"):
    assert fill_of_text[text] == {"lavender"}, (text, fill_of_text[text])
for text in ("اسم العميل:", "رقم الموديل:", ":NAME", ":DATE", "اسم المركب:", "النوع:"):
    assert fill_of_text[text] == {"cream"}, (text, fill_of_text[text])
for key in ("mfg_khayas", "p1_khayas", "asm_khayas", "p2_khayas"):
    assert fill_of_cell[key] == "khayas", (key, fill_of_cell[key])
for key in ("p08", "p04", "p1_before", "p1_after", "asm_before", "asm_after", "gems", "chain", "p2_before",
            "customer", "assembler", "piece:0:0"):
    assert fill_of_cell[key] is None, (key, fill_of_cell[key])
assert fill_of_text["1"] == {None}, "أرقام صفوف القطع بيضاء"
layout = member("sb_layout_paper")
assert '"green": P["green"], "lavender": P["lavender"], "cream": P["cream"], "khayas": P["khayas"]' in layout
tint = member("sb_tint")
assert 'base = P["khayas"] if key in self.SB_KHAYAS_KEYS else P["page"]' in tint
print("✔ الشاشة: الرأس والأقسام و«الوزن بعد/السلسال/الإجمالي» خضراء، والعناوين بنفسجية، وبيانات الطقم كريمية، "
      "والخياس بيج وردي (وخانته المكتوبة كذلك)، والإدخال أبيض")

# ═══ السند المطبوع: الألوان نفسها ═══
draw = member("draw_set_voucher_page")
assert 'HEAD, LABEL, WHITE = paper("green"), paper("lavender"), Color(1, 1, 1)' in draw
assert 'CREAM, KHAYAS = paper("cream"), paper("khayas")' in draw
assert "h = self.SET_PAPER_COLORS[name]" in draw
assert 'cell(x1 - 24 * MM, a0, x1, a1, label, CREAM, size=10.5)' in draw
assert 'cell(x1 - 24 * MM, b0, x1, b1, label, CREAM, size=10.5)' in draw
assert 'KHAYAS if h == "خياس" else None' in draw
assert "pair(lx0, lx1, t, t + r, label, value_fill, value=fmt(val), label_fill=HEAD)" in draw
assert 'cell(lx0, top, lx1, top + r, title, HEAD, size=13)' in draw
assert 'Color(0.80, 0.80, 0.80)' not in draw, "لا رمادي قديم"
print("✔ السند المطبوع بالألوان نفسها: أخضر للأقسام، بنفسجي للعناوين، كريمي لبيانات الطقم، بيج وردي للخياس")

print("\n✅ 1.93: قالب رقم التشغيل بألوان القالب الورقي على الشاشة وفي الطباعة")
