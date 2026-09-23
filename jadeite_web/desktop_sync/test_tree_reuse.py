# -*- coding: utf-8 -*-
"""
اختبار إعادة استخدام الجداول: التحديث يمسح الصفوف بدل إعادة بناء الأدوات،
فتفتح الشاشات فوراً بلا «تكوّن».
"""
import ast, io, re

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) المصنع ═══
f = seg("reuse_or_create_tree")
assert "_cached_tree" in f and "_cached_cols" in f
print("✔ الجدول يُخزَّن على إطاره مع أعمدته")
assert "cached.delete(*cached.get_children())" in f
print("✔ التحديث يمسح الصفوف فقط — الأدوات تبقى")
assert "cached_cols == tuple(columns)" in f
print("✔ تغيّر الأعمدة يُجبر إعادة البناء (لا جدول بأعمدة قديمة)")
assert "cached.winfo_exists()" in f and "except Exception" in f
print("✔ جدول تالف أو محذوف يُعاد بناؤه بدل الانهيار")
assert "_cached_total_tree" in f
print("✔ شجرة الإجمالي الثابتة تُعاد استخدامها أيضاً")

# ═══ ٢) الشاشات الثلاث تستخدمه ═══
targets = {
    "refresh_pending_sales_table": "المبيعات/الصادر",
    "refresh_op_ledger_table":     "كشف المصنعين/المركبين",
    "render_stage_ops_table":      "أقسام مراحل التصنيع",
    "refresh_inquiry_table":       "صناديق الخياس",
}
for fn, label in targets.items():
    b = seg(fn)
    assert "reuse_or_create_tree" in b, fn
    print(f"✔ {label}: يُعيد استخدام جدوله")

# ═══ ٣) لا هدم زائد في مسارات التحديث ═══
for fn, label in targets.items():
    b = seg(fn)
    destroys = len(re.findall(r'\.winfo_children\(\):\s*\n\s*widget\.destroy\(\)', b))
    # refresh_inquiry_table يُنظّف مرة واحدة عند أول بناء فقط
    assert destroys <= 1, (fn, destroys)
print("✔ لا مسار يهدم أدواته في كل تحديث")

# ═══ ٤) لا تراكم أدوات ═══
rsm = seg("render_stage_monthly_inquiry")
assert "for widget in self.table_frame.winfo_children()" in rsm
assert "self._inquiry_holder = None" in rsm
print("✔ فرع صناديق الخياس الشهري ينظّف إطاره ويُبطل ذاكرة الفرع الآخر")

inq = seg("refresh_inquiry_table")
i_branch = inq.find("self.render_stage_monthly_inquiry()")
i_clean = inq.find("for widget in self.table_frame.winfo_children()")
assert i_branch < i_clean, "التنظيف يسبق التفرّع — بناء مزدوج في كل تحديث"
print("✔ التفرّع يسبق التنظيف — لا بناء مزدوج")

# ═══ ٥) التجهيز المسبق ═══
calc = seg("_startup_first_calc")
assert '["المبيعات", "مراحل التصنيع", "صناديق الخياس"]' in calc
print("✔ الشاشات الثلاث تُجهَّز مسبقاً في الخلفية")

print("\n✅ الجداول تُعاد استخدامها — الشاشات تفتح فوراً")
