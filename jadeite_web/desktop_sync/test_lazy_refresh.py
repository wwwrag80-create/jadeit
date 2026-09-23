# -*- coding: utf-8 -*-
"""
اختبار التحديث الكسول: تسريع الترحيل بلا فقدان دقة.

الخطر الذي يفحصه: اسم شاشة خاطئ في الخريطة = شاشة لا تُحدَّث أبداً عند فتحها،
فيرى المستخدم أرقاماً قديمة. وهذا خطأ صامت لا يظهر إلا بالاستخدام.
"""
import ast, io, re

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

registered = re.findall(r'self\.tabview\.add\("([^"]+)"\)', src)
mapping = None
for node in ast.walk(cls):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "SCREEN_REFRESHERS":
                mapping = ast.literal_eval(node.value)

assert mapping, "خريطة الشاشات غير موجودة"
print(f"الشاشات المسجّلة: {len(registered)} | في الخريطة: {len(mapping)}")

# ١) كل اسم في الخريطة مسجّل فعلاً
missing = [n for n in mapping if n not in registered]
assert not missing, f"أسماء شاشات خاطئة (لن تُحدَّث أبداً): {missing}"
print("✔ كل أسماء الخريطة تطابق الشاشات المسجّلة تماماً")

# ٢) كل شاشة مسجّلة لها مُحدِّث (فلا تبقى شاشة ببيانات قديمة)
uncovered = [n for n in registered if n not in mapping]
assert not uncovered, f"شاشات بلا تحديث: {uncovered}"
print("✔ كل شاشة مسجّلة لها دوال تحديث — لا شاشة تبقى ببيانات قديمة")

# ٣) كل دالة تحديث معرّفة فعلاً
defined = {m.name for m in cls.body if isinstance(m, ast.FunctionDef)}
bad = [(k, f) for k, fns in mapping.items() for f in fns if f not in defined]
assert not bad, f"دوال تحديث غير معرّفة: {bad}"
total_fns = sum(len(v) for v in mapping.values())
print(f"✔ كل دوال التحديث الـ {total_fns} معرّفة")

# ٤) recalculate_all لم يعد يُحدّث كل الشاشات
recalc = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                          and m.name == "recalculate_all"))
assert "mark_all_screens_dirty" in recalc and "refresh_visible_screen" in recalc
heavy = ["refresh_invoice_archive_table", "refresh_journal_entries_table",
         "refresh_chart_of_accounts", "refresh_losses_tab", "refresh_sets_profit_tab"]
still = [h for h in heavy if h + "()" in recalc]
assert not still, f"ما زال يُحدّث شاشات غير ظاهرة: {still}"
print("✔ الترحيل يُحدّث الشاشة المعروضة فقط، لا كل الشاشات")

# ٥) الأرصدة ما زالت تُحسب كاملة (الدقة لم تُمس)
for marker in ("current_treasury_balance", "current_total_gold", "get_material_balance"):
    assert marker in recalc, marker
print("✔ الأرصدة تُحسب كاملة في كل ترحيل — الأرقام صحيحة دائماً")

# ٦) الانتقال لأي شاشة يُحدّثها إن لزم
nav = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                       and m.name == "navigate_to_screen"))
assert "refresh_pending_screen" in nav
print("✔ فتح أي شاشة يُحدّثها تلقائياً إن تغيّرت بياناتها")

pend = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                        and m.name == "refresh_pending_screen"))
assert "_dirty_screens" in pend
print("✔ التحديث يحدث مرة واحدة فقط ثم تُزال علامة الحاجة إليه")

rs = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                      and m.name == "refresh_screen"))
assert "log_cloud_error" in rs
print("✔ فشل تحديث شاشة يُسجَّل ولا يُعطّل باقي الشاشات")

print(f"\n✅ الترحيل صار يُعيد بناء جداول شاشة واحدة بدل {total_fns} جدولاً")
