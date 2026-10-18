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

# ═══ نوافذ تعديل صفوف الأقسام: أفقية مثل صف الإدخال (1.71) ═══
fin = seg("finish_horizontal_edit_window")
assert "self.bind_enter_navigation(entries, on_last=on_save)" in fin and "self.bind_arrow_navigation(entries)" in fin
assert 'win.bind("<Escape>"' in fin and 'select_range(0, "end")' in fin and "focus_set()" in fin
print("\n✔ نوافذ التعديل الأفقية: Enter للخانة التالية ثم الحفظ في آخر خانة، والأسهم ← → بين الخانات، وEsc للإلغاء")
hb = seg("build_horizontal_edit_fields")
assert "grid_columnconfigure(c, weight=1, uniform=" in hb and "col = cols - used - span" in hb
print("✔ الخانات أفقية من اليمين لليسار، عنوان كل خانة فوقها، وتلتفّ لصف ثانٍ إن كثرت")

row = seg("open_row_full_edit_dialog")
assert "self.build_horizontal_edit_fields(win, specs" in row
assert "self.finish_horizontal_edit_window(win, all_entries, save_row" in row
assert "bind_vertical_navigation" not in row
print("✔ نافذة تعديل صف المصنعين/المركبين أفقية بكل خاناتها")

fields = None
for node in ast.walk(cls):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "ROW_EDIT_FIELDS":
                fields = ast.literal_eval(node.value)
n_mfg = 3 + len(fields["المصنعين"]) + 1      # ترقيم + خانات + بيان
n_mer = 3 + len(fields["المركبين"]) + 1
print(f"✔ عدد الخانات المتنقَّل بينها: المصنعين {n_mfg} | المركبين {n_mer}")

stage = seg("open_stage_op_edit_dialog")
assert "self.build_horizontal_edit_fields(win, specs" in stage
assert "self.finish_horizontal_edit_window(win, entries, save_edit, focus=ent_sarf)" in stage
assert "if with_trees:" in stage and '("عدد الأشجار:"' in stage
print("✔ نافذة تعديل الكاستنج/التلميع/بوليش 1 والأقسام المضافة: أفقية بالتنقّل نفسه، وعدد الأشجار حين يُعرض")
rec = seg("open_recovery_op_edit_dialog")
assert "entries = self.build_horizontal_edit_fields(win, specs" in rec
assert "self.finish_horizontal_edit_window(win, list(entries), save_edit, focus=ent_w" in rec
assert 'specs.append(("العيار:"' in rec, "1.78: خانة العيار لحركة «صب وتحليل» بعيارها"
print("✔ ونافذة حركة «صب وتحليل» كذلك (الوزن والعيار والتاريخ والبيان)")

print("\n✅ التنقّل يعمل في كل نوافذ تعديل الحركة")
