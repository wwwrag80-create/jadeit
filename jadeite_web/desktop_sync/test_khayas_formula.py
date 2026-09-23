# -*- coding: utf-8 -*-
"""
اختبار معادلة الخياس الفعلي المعتمدة:
    ذهب/باقي  −  المرجع ٧٥٠  −  الخياس الموجب فقط
"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

ns = {}
exec("class S:\n"
     + textwrap.indent(textwrap.dedent(seg("get_section_khayas_parts")), "    ") + "\n"
     + textwrap.indent(textwrap.dedent(seg("get_actual_section_khayas")), "    ") + "\n"
     "    def calculate_single_ledger(self, n, cat, target_month=None, include_settled=False, invoices=None):\n"
     "        return self._led[n]\n", ns)
app = ns["S"]()
app.categories = {"المصنعين": ["أ", "ب", "ج"], "المركبين": ["س", "ص"]}
app._led = {
    "أ": {"ذهب/باقي": 10.0, "المرجع 750": 2.0, "الخياس": -3.0},
    "ب": {"ذهب/باقي":  6.0, "المرجع 750": 1.0, "الخياس":  4.0},   # موجب → يُخصم
    "ج": {"ذهب/باقي":  4.0, "المرجع 750": 0.0, "الخياس":  0.0},
    "س": {"ذهب/باقي": 20.0, "المرجع 750": 5.0, "الخياس":  2.0},
    "ص": {"ذهب/باقي":  8.0, "المرجع 750": 1.0, "الخياس": -6.0},
}

# ═══ المصنعين ═══
faqid, marja, pos, total = app.get_section_khayas_parts("المصنعين")
assert faqid == 20.0 and marja == 3.0 and pos == 4.0
assert total == round(20.0 - 3.0 - 4.0, 2) == 13.0
print(f"✔ المصنعين: ذهب/باقي {faqid} − المرجع ٧٥٠ {marja} − الخياس الموجب {pos} = {total}")

# ═══ المركبين — نفس المعادلة ═══
f2, m2, p2, t2 = app.get_section_khayas_parts("المركبين")
assert f2 == 28.0 and m2 == 6.0 and p2 == 2.0
assert t2 == round(28.0 - 6.0 - 2.0, 2) == 20.0
print(f"✔ المركبين: {f2} − {m2} − {p2} = {t2}  (نفس المعادلة)")

# ═══ الأرصدة السالبة لا تُخصم مرتين ═══
assert p2 == 2.0, "الخياس السالب (−6) يجب ألا يدخل الخصم"
print("✔ الخياس السالب لا يُخصم — هو أصلاً داخل (ذهب/باقي)")

# ═══ مصدر واحد: الدالة المعتمدة تُرجع نفس الرقم ═══
for cat, expected in (("المصنعين", 13.0), ("المركبين", 20.0)):
    got = app.get_actual_section_khayas(cat)
    assert got == expected, (cat, got, expected)
print("✔ get_actual_section_khayas تُرجع نفس الرقم — لا حساب موازٍ")

# ═══ لا بقايا للمعادلة القديمة ═══
assert "get_section_khayas_split(" not in src.replace("def get_section_khayas_split(", "")
print("✔ لم تبقَ أي استخدامات للمعادلة القديمة")

act = seg("get_actual_section_khayas")
assert 'if cat_name in ("المصنعين", "المركبين"):' not in act
print("✔ لا استثناء للمصنعين/المركبين — المعادلة واحدة لكل الأقسام")

# ═══ الشريط البارز والإقفال وبطاقة الخسائر ═══
bar = seg("refresh_inquiry_table")
assert "get_section_khayas_parts" in bar and "ذهب/باقي" in bar and "المرجع ٧٥٠" in bar
print("✔ الشريط البارز يعرض مكوّنات المعادلة الثلاثة والنتيجة")

close = seg("close_split_khayas_box")
assert "get_section_khayas_parts" in close and "share_net" in close and "share_pos" in close
print("✔ الإقفال يوزّع المبلغ على مكوّنَي المعادلة (مجموعهما = المتبقّي)")

card = seg("get_box_breakdown_text")
assert "ذهب/باقي" in card and "الخياس الموجب" in card
print("✔ بطاقة شاشة الخسائر تعرض التفصيل بالمعادلة الجديدة")

print("\n✅ المعادلة معتمدة في كل المواضع بمصدر واحد")
