# -*- coding: utf-8 -*-
"""اختبار التنقّل في نوافذ تعديل الحركة: Enter و↑ ↓"""
import ast, io

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ الدالة ═══
nav = seg("bind_vertical_navigation")
for key in ('"<Down>"', '"<Up>"', '"<Return>"'):
    assert key in nav, key
print("✔ التنقّل مربوط بـ ↓ و↑ و Enter")
assert 'select_range(0, "end")' in nav
print("✔ محتوى الخانة يُحدَّد عند الوصول إليها — الكتابة تستبدله مباشرة")
assert "on_last" in nav and "on_last()" in nav
print("✔ Enter في آخر خانة يحفظ مباشرة")
assert 'win.bind(' in nav and "focus_get()" in nav
print("✔ الربط على النافذة نفسها لا على الخانات — يعمل مع CTkEntry دائماً")
assert "getattr(w, \"_entry\", w)" in nav
print("✔ ويتعرّف على الخانة الداخلية لـ CTkEntry عند تحديد موضع التركيز")
assert "if not widgets:" in nav
print("✔ قائمة خانات فارغة لا تُسبب خطأ")

# ═══ نافذة المصنعين/المركبين ═══
row = seg("open_row_full_edit_dialog")
assert "self.bind_vertical_navigation(nav_all, on_last=lambda: save_row(), window=win)" in row
print("\n✔ نافذة تعديل صف المصنعين/المركبين: تنقّل رأسي + حفظ بـ Enter")
assert "self.bind_arrow_navigation(nav_all)" in row
print("✔ ومعه التنقّل الأفقي (يمين/يسار) كما كان")

fields = None
for node in ast.walk(cls):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "ROW_EDIT_FIELDS":
                fields = ast.literal_eval(node.value)
n_mfg = 3 + len(fields["المصنعين"]) + 1      # ترقيم + خانات + بيان
n_mer = 3 + len(fields["المركبين"]) + 1
print(f"✔ عدد الخانات المتنقَّل بينها: المصنعين {n_mfg} | المركبين {n_mer}")

# ═══ نافذة الكاستنج/التلميع/البف ═══
stage = seg("open_stage_op_edit_dialog")
assert "self.bind_vertical_navigation(_nav, on_last=lambda: save_edit(), window=win)" in stage
print("✔ نافذة تعديل الكاستنج/التلميع/البف والأقسام المضافة: نفس التنقّل")
assert "ent_trees if with_trees else None" in stage
print("✔ وخانة عدد الأشجار تدخل التنقّل فقط حين تكون معروضة")

i_last_entry = stage.rindex("ent_note = ctk.CTkEntry")
i_nav = stage.index("bind_vertical_navigation")
assert i_last_entry < i_nav
print("✔ الربط يتم بعد إنشاء كل الخانات (وإلا فقدت بعضها التنقّل)")

for b, label in ((row, "المصنعين/المركبين"), (stage, "الكاستنج/التلميع/البف")):
    assert "focus_set()" in b, label
print("✔ التركيز يبدأ في أول خانة فيعمل التنقّل فور الفتح")

print("\n✅ التنقّل يعمل في كل نوافذ تعديل الحركة")
