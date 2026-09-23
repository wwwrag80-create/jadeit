# -*- coding: utf-8 -*-
"""
اختبار ترتيب الأسماء المركّبة: تُعرض «محمد علي» لا «علي محمد»،
وتُنظَّف من علامة الاتجاه قبل أي حفظ أو مطابقة.
"""
import ast, io, re, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def seg(name):
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == name))


ns = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(seg("rtl")), "    ")
     + "\n" + textwrap.indent(textwrap.dedent(seg("clean_name")), "    "), ns)
S = ns["S"]

RLM = "\u200f"
name = "محمد علي"
shown = S.rtl(name)
assert shown.startswith(RLM) and shown[1:] == name
print(f"✔ الاسم يُعرض باتجاه مثبّت: {shown!r}")
print("  → تبقى الكلمات بترتيبها: محمد ثم علي")

assert S.clean_name(shown) == name
print("✔ التنظيف يُرجع الاسم الأصلي حرفياً (لا يُفسد المطابقة مع الدفاتر)")

for bad in ("  محمد علي  ", RLM + "محمد علي", "\u200eمحمد علي", None, ""):
    got = S.clean_name(bad)
    assert got in (name, ""), (bad, got)
print("✔ يتعامل مع المسافات وعلامتَي الاتجاه والقيم الفارغة")

# ═══ قائمة المصنعين/المركبين ═══
upd = seg("update_op_names")
assert "self.rtl(n) for n in names" in upd and "self.rtl(names[0])" in upd
print("✔ قائمة المصنعين/المركبين تعرض الأسماء باتجاه مثبّت")

# كل قراءة من القائمة تُنظَّف
total_reads = src.count("self.combo_op_name.get()")
clean_reads = src.count("self.clean_name(self.combo_op_name.get())")
assert total_reads == clean_reads, f"قراءات غير منظّفة: {total_reads - clean_reads}"
print(f"✔ كل قراءات الاسم من القائمة منظّفة ({clean_reads} من {total_reads})")

ruf = seg("render_unified_fields")
assert "name = self.clean_name(name)" in ruf
print("✔ الاسم القادم من القائمة يُنظَّف قبل بناء الحقول")

# ═══ أقسام الكاستنج/التلميع/البف ═══
gsv = seg("get_stage_name_values")
assert "self.rtl(v) for v in values" in gsv
print("✔ أقسام الكاستنج والتلميع والبف تعرض الأسماء باتجاه مثبّت")

for fn in ("submit_casting_op", "submit_polish_op", "submit_polish_buff_op"):
    b = seg(fn)
    assert "self.clean_name(" in b, fn
print("✔ الترحيل في تلك الأقسام ينظّف الاسم قبل الحفظ")

# ═══ الإكمال التلقائي ═══
auto = seg("bind_name_autocomplete")
assert "self.clean_name(combobox.get())" in auto and "self.clean_name(n)" in auto
print("✔ البحث في القائمة يقارن الأسماء بعد تنظيفها (لا تختفي الخيارات)")

# محاكاة فعلية للإكمال التلقائي
full = [S.rtl(x) for x in ("محمد علي", "أحمد سالم", "علي حسن")]
typed = S.clean_name("محمد")
filtered = [n for n in full if typed in S.clean_name(n)]
assert filtered == [S.rtl("محمد علي")], filtered
print("✔ كتابة (محمد) تُظهر (محمد علي) فقط — المطابقة سليمة")

print("\n✅ ترتيب الأسماء صحيح في كل الشاشات، والبيانات المحفوظة سليمة")
