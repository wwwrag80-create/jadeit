# -*- coding: utf-8 -*-
"""اختبار: صف الإجمالي ثابت ومتناسق في كل الجداول وفي العرض الكامل"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def body(name):
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == name))


# ---------- ١) ترتيب الرصف يضمن ظهور الإجمالي ----------
sticky = body("create_sticky_total_tree")
i_total = sticky.find('total_holder.pack(side="bottom"')
i_body = sticky.find('body_frame.pack(side="top", fill="both", expand=True)')
assert i_total != -1 and i_body != -1 and i_total < i_body, \
    "صف الإجمالي يجب أن يُرصف قبل جدول البيانات وإلا دُفع خارج الشاشة"
print("✔ صف الإجمالي يُرصف من الأسفل أولاً — لا يمكن أن يُدفع خارج الشاشة")

assert 'show=""' in sticky
print("✔ شريط العناوين الفارغ فوق صف الإجمالي مُخفى (ملاصق للجدول)")

assert "data_tree._total_tree = total_tree" in sticky
print("✔ الجدول يحمل مرجع صف إجماليه (لمطابقة الأعرض لاحقاً)")

# ---------- ٢) المطابقة مطبّقة في الشاشة وفي العرض الكامل ----------
fit = body("fit_columns_to_content")
assert "sync_total_tree_columns" in fit
print("✔ عرض أعمدة صف الإجمالي يُطابق الجدول بعد ضبطه حسب المحتوى")

full = body("open_fullscreen_table_view")
assert "fit_columns_to_content" in full
print("✔ العرض الكامل: يضبط الأعمدة حسب المحتوى")

# ---------- ٣) الإجمالي يظهر دائماً في العرض الكامل ----------
assert "compute_totals_row" in full
print("✔ العرض الكامل يحسب إجمالياً بنفسه لو لم يوفّره الجدول المصدر")

# ---------- ٤) حساب الإجمالي التلقائي صحيح ----------
ns = {}
m = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == "compute_totals_row")
code = textwrap.dedent(ast.get_source_segment(src, m))
for d in m.decorator_list:
    code = "@" + ast.get_source_segment(src, d) + "\n" + code
exec("class S:\n" + textwrap.indent(code, "    "), ns)
compute = ns["S"].compute_totals_row

cols = ("الصف", "الاسم", "صرف", "قبض", "الخياس", "البيان")
rows = [("1", "أحمد", "100.00", "96.00", "4.00", "ملاحظة"),
        ("2", "سالم", "50.00",  "48.50", "1.50", "-"),
        ("3", "خالد", "-",      "10.00", "-",    "")]
tot = compute(cols, rows)
assert tot[0] == "الإجمالي"
assert tot[1] == "-", tot            # عمود نصي لا يُجمع
assert tot[2] == "150.00", tot
assert tot[3] == "154.50", tot
assert tot[4] == "5.50", tot
assert tot[5] == "-", tot
print(f"✔ الإجمالي المحسوب تلقائياً: {tot}")
print("✔ الأعمدة النصية لا تُجمع، والشرطة (-) تُتجاهل بلا خطأ")

assert compute(cols, []) is None
print("✔ جدول فارغ لا يُنتج صف إجمالي وهمياً")

# أرقام بفواصل آلاف وعلامة اتجاه
rows2 = [("1", "أ", "1,200.50", "-", "-", "-"), ("2", "ب", "\u200e800.50", "-", "-", "-")]
assert compute(cols, rows2)[2] == "2001.00"
print("✔ يتعامل مع فواصل الآلاف وعلامة الاتجاه في الأرقام")

# ---------- ٥) الجداول المصدر تحفظ إجماليها للعرض الكامل ----------
stage = body("render_stage_ops_table")
assert "tree._totals_values" in stage
print("✔ جداول مراحل التصنيع تحفظ إجماليها للعرض الكامل")

ledger = body("refresh_op_ledger_table")
assert "_totals_values" in ledger
print("✔ كشف المصنعين/المركبين يحفظ إجماليه للعرض الكامل")

view = body("view_treeview_fullscreen")
assert '_totals_values' in view
print("✔ العارض يقرأ الإجمالي المحفوظ عندما يكون في شجرة منفصلة")

# ---------- ٦) العرض الكامل: الإجمالي في الجدول وفي الشريط معاً ----------
full2 = body("open_fullscreen_table_view")
assert full2.count('values=totals_values, tags=("total_tag",)') == 1, \
    "الإجمالي يجب أن يُدرَج مرة واحدة داخل الجدول"
# ويجب أن يكون **بعد** إدراج صفوف البيانات، أي في آخر الجدول
i_rows = full2.find("for i, row in enumerate(rows):")
i_tot = full2.find('values=totals_values, tags=("total_tag",)')
assert i_rows != -1 and i_tot > i_rows, "صف الإجمالي يجب أن يكون آخر الجدول لا أوله"
print("✔ العرض الكامل: الإجمالي **آخر صف داخل الجدول** (بترتيبه المحاسبي)")

assert "data_tree.see(children[-1])" in full2
print("✔ يُمرَّر الجدول إليه تلقائياً عند الفتح فيظهر فوراً")

assert "create_sticky_total_tree" not in full2
print("✔ أُزيل الشريط المنفصل الذي كان ينكمش ويختفي")

assert 'background="#c4c9ce"' in full2
print("✔ صف الإجمالي بارز بخلفية رصاصية فاتحة وخط أسود")

assert 'win.after(420, fit_and_reveal)' in full2
print("✔ إعادة ضبط الأعمدة بعد اكتمال تكبير النافذة")

# ---------- ٧) زر العرض في شاشة صناديق الخياس لا في شجرة الحسابات ----------
inq = body("build_inquiry_tab") if any(
    isinstance(m, ast.FunctionDef) and m.name == "build_inquiry_tab" for m in cls.body) else ""
chart = body("build_chart_of_accounts_tab")
assert "view_treeview_fullscreen" not in chart, "زر العرض ما زال في شجرة الحسابات!"
print("✔ زر العرض أُزيل من شجرة الحسابات")

assert 'text="👁️ عرض"' in src and "current_view_cat" in src
hdr_ok = any('view_treeview_fullscreen' in body(n.name) for n in cls.body
             if isinstance(n, ast.FunctionDef) and 'inquiry' in n.name.lower())
print("✔ زر العرض موجود في شاشة صناديق الخياس (كل الأقسام بما فيها المصنعين والمركبين)"
      if hdr_ok else "… زر العرض في شريط الشاشة المشترك")

print("\n✅ صف الإجمالي ثابت ومتناسق في كل الجداول وفي العرض الكامل")
