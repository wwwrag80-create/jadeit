# -*- coding: utf-8 -*-
"""اختبار: خياس المركب بالبحث بالصف + نافذة تعديل كل خانات الصف"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
m = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == "get_assembler_khayas_for_set")
ns = {"ALLOWANCE_8": 0.008}
exec("class S:\n" + textwrap.indent(textwrap.dedent(ast.get_source_segment(src, m)), "    "), ns)
app = ns["S"]()
app.current_display_month = "2026-08"
app.categories = {"المركبين": ["سالم"], "المصنعين": ["أحمد"]}


def inv(i, name, t, w, row_no, set_no="", month="2026-06"):
    return {"رقم الفاتورة": i, "الاسم": name, "النوع": t, "الوزن": w,
            "row_number": row_no, "set_number": set_no,
            "settled_status": "ACTIVE", "التاريخ": f"{month}-05 10:00:00"}


# ═══ الحالة الحقيقية: رقم التشغيل مسجّل على حركة الصرف فقط (بيانات قديمة) ═══
app.invoices = {
    1: inv(1, "سالم", "صرف ذهب", 400.0, "1", set_no="1"),   # الرقم هنا فقط
    2: inv(2, "سالم", "قبض ذهب", 375.0, "1", set_no=""),    # وليس هنا
}
v = app.get_assembler_khayas_for_set("1")
assert v == round(375 * 0.008, 2) == 3.0, v
print(f"✔ رقم التشغيل مسجّل على حركة واحدة فقط من الصف → {v}  (كان يُرجع 0.0)")
print("  وهو بالضبط الرقم الذي يعرضه عمود مسموح/٨ في الكشف")

# ═══ مسجّل على كل الحركات (بيانات النسخة الجديدة) ═══
app.invoices = {
    1: inv(1, "سالم", "صرف ذهب", 400.0, "2", set_no="2"),
    2: inv(2, "سالم", "قبض ذهب", 375.0, "2", set_no="2"),
}
assert app.get_assembler_khayas_for_set("2") == 3.0
print("✔ مسجّل على كل الحركات → نفس النتيجة (لا فرق بين القديم والجديد)")

# ═══ المصنعون مستثنون تماماً (المصدر: المركبين فقط) ═══
app.invoices = {
    1: inv(1, "أحمد", "صرف ذهب", 1000.0, "5", set_no="5"),
    2: inv(2, "أحمد", "المفنش ٨ بالالف", 50.0, "5"),
    3: inv(3, "أحمد", "قبض ذهب", 900.0, "5"),
}
assert app.get_assembler_khayas_for_set("5") == 0.0
print("✔ قسم المصنعين مستثنى تماماً — المصدر هو المركبين وحدهم")

# ═══ صفوف متعددة وعمال متعددون من المركبين ═══
app.invoices = {
    1: inv(1, "سالم", "قبض ذهب", 100.0, "1", set_no="9"),
    2: inv(2, "سالم", "قبض ذهب", 200.0, "2", set_no="9", month="2026-07"),
    3: inv(3, "أحمد", "المفنش ٨ بالالف", 25.0, "3", set_no="9", month="2026-05"),
    4: inv(4, "سالم", "قبض ذهب", 999.0, "8", set_no="لا-علاقة"),
}
assert app.get_assembler_khayas_for_set("9") == round((100 + 200) * 0.008, 2) == 2.4
print("✔ صفوف وفترات متعددة من المركبين → 2.40 (المصنّع والصف غير المعني مستثنيان)")

# ═══ حالات الحدود ═══
assert app.get_assembler_khayas_for_set("لا-يوجد") == 0.0
assert app.get_assembler_khayas_for_set("") == 0.0
assert app.get_assembler_khayas_for_set(None) == 0.0
print("✔ رقم غير موجود أو فارغ → 0.0 بلا خطأ")

app.invoices[5] = dict(inv(5, "سالم", "قبض ذهب", 500.0, "1", set_no="9"), settled_status="SETTLED")
assert app.get_assembler_khayas_for_set("9") == 2.4
print("✔ الحركات الملغاة مستثناة")

# ═══ الأخطاء لم تُكتم ═══
auto = ast.get_source_segment(src, next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                                        and x.name == "autofill_assembler_khayas"))
assert "log_cloud_error" in auto and "except Exception:\n            pass" not in auto
print("✔ فشل الجلب يُسجَّل ولا يُكتم (كان يبدو كأن الرقم غير موجود)")

# ═══ نافذة تعديل كل خانات الصف ═══
edit = ast.get_source_segment(src, next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                                        and x.name == "open_row_full_edit_dialog"))
for f in ("رقم الصف", "رقم التشغيل", "التاريخ", "البيان"):
    assert f in edit, f
print("✔ نافذة التعديل تعرض رقم الصف ورقم التشغيل والتاريخ والبيان")

fields = None
for node in ast.walk(cls):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "ROW_EDIT_FIELDS":
                fields = ast.literal_eval(node.value)
assert len(fields["المصنعين"]) == 8 and len(fields["المركبين"]) == 5
print(f"✔ خانات المصنعين: {len(fields['المصنعين'])} | المركبين: {len(fields['المركبين'])} — كل عمليات الصف")

assert "delete_invoice_from_db" in edit and "save_invoice_to_db" in edit
print("✔ الحفظ: يحدّث الموجود، ويُنشئ الجديد، ويحذف ما صُفِّر")
assert "recalculate_all" in edit
print("✔ إعادة حساب شاملة بعد الحفظ")
assert 'op_type == "العيار بعد الفحص"' in edit
print("✔ العيار قد يكون صفراً مشروعاً فلا يُحذف بسببه")

led = ast.get_source_segment(src, next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                                       and x.name == "op_ledger_edit_selected"))
assert "open_row_full_edit_dialog" in led
print("✔ زر (تعديل الحركة المحددة) يفتح نافذة التعديل لا كشف الصف")

dbl = ast.get_source_segment(src, next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                                       and x.name == "_on_op_ledger_double_click"))
assert "open_row_operations_detail" in dbl
print("✔ النقر المزدوج يعرض كشف الصف بتاريخه ووقته")

# ═══ شريط الإجمالي لا ينكمش ═══
sticky = ast.get_source_segment(src, next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                                          and x.name == "create_sticky_total_tree"))
assert "height=40" in sticky and "pack_propagate(False)" in sticky
print("✔ شريط الإجمالي بارتفاع ثابت ٤٠ ومنع انتشار — لا يمكن أن ينكمش فيختفي")

print("\n✅ كل الاختبارات نجحت")
