# -*- coding: utf-8 -*-
"""
اختبار الدفعة الثالثة من الواجهات والمحاسبة — يشغّل الدوال الحقيقية من البرنامج:

  • الموردون: القيد اليومي يظهر في رصيد المورد (كان لا يُحسب إطلاقاً)
  • الكاستنج: «مسترجع الأشجار» يُلحق بصفه، ويخصم من خياس الصف والصندوق معاً
  • المصنعون/المركبون: قاعدة الصف والخانة (خانة موجودة لا تُسجَّل ثانيةً)
  • الكشف يجمع قيم الصف ولا يستبدلها
  • بنية الشاشات: المبيعات بلا تمرير خارجي، عمود الإجراءات، لا عمود الصافي…
"""
import ast, io, textwrap, sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
lines = src.split("\n")
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def method_src(name):
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))


def class_attr_src(name):
    node = next(m for m in cls.body if isinstance(m, ast.Assign)
                and any(getattr(t, "id", None) == name for t in m.targets))
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def build(methods, attrs=(), extra=""):
    body = "\n".join(textwrap.indent(class_attr_src(a), "    ") for a in attrs)
    body += "\n" + "\n".join(textwrap.indent(method_src(m), "    ") for m in methods)
    ns = {}
    exec(module_src("COUNTED_STATUSES") + "\n" + module_src("LEDGER_FIELD_BY_TYPE") + "\n"
         + "class App:\n" + body + "\n" + textwrap.indent(extra, "    "), ns)
    return ns["App"]


seg = lambda n: method_src(n)
M = "2026-09"


def inv(no, name, t, w, row="", note="", status="ACTIVE", trees=0.0, set_no=""):
    return {"رقم الفاتورة": no, "التاريخ": f"{M}-05 10:{no % 60:02d}:00", "الاسم": name, "النوع": t,
            "الوزن": w, "البيان": note, "settled_status": status, "trees_count": trees,
            "row_number": row, "set_number": set_no, "period": M}


# ═══ ١) الموردون: القيد اليومي في رصيد المورد ═══
S = build(["get_supplier_totals"])
app = S()
app.invoices = {i["رقم الفاتورة"]: i for i in [
    inv(1, "مورد جديد", "قيد يومي مدين", 10.0),          # القيد الذي أبلغ عنه العميل
    inv(2, "مورد جديد", "وارد ذهب (عيار 18)", 50.0),
    inv(3, "مورد جديد", "مبيعات ذهب", 20.0),
    inv(4, "مورد جديد", "قيد يومي دائن", 4.0),
    inv(5, "مورد جديد", "قيد يومي مدين", 99.0, status="DELETED"),
    inv(6, "مورد آخر", "قيد يومي مدين", 7.0),
]}
madin, daen = app.get_supplier_totals("مورد جديد")
assert (madin, daen) == (30.0, 54.0), (madin, daen)
print(f"✔ قيد يومي ١٠ جم لمورد جديد يظهر في رصيده: مدين {madin} (مبيعات ٢٠ + قيد ١٠)، دائن {daen} (وارد ٥٠ + قيد ٤)")
print("✔ المحذوف لا يُحسب، وقيود مورد آخر لا تختلط")

je = seg("submit_journal_entry")
assert "اسم غير مسجّل" in je and "askyesno" in je[je.index("known ="):]
print("✔ قيد يومي على اسم غير مسجّل يطلب تأكيداً (خطأ الكتابة لا يُنشئ حساباً وهمياً)")
assert "_open_selected_supplier_statement" in seg("refresh_suppliers_table")
print("✔ نقرتان على مورد تفتحان كشف حسابه")

# ═══ ٢) الكاستنج: مسترجع الأشجار ═══
C = build(["invoices_by_name", "invoices_by_period", "period_invoices", "collect_stage_ops_rows", "is_row_recovery", "row_sort_key", "inv_period", "inv_in_period",
           "get_box_khayas_cumulative", "get_stage_config", "get_box_account_name", "get_display_label"],
          attrs=("INBOUND_TYPES", "BOX_DISPLAY_OVERRIDES"))
app = C()
app.categories = {"أقسام_خياس_إضافية": []}
app.current_display_month = M
app.invoices = {i["رقم الفاتورة"]: i for i in [
    inv(1, "كاستنج", "صرف كاستنج", 80.0, row="7", trees=4),
    inv(2, "كاستنج", "قبض كاستنج", 70.0, row="7", trees=4),
    inv(3, "مسترجع كاستنج", "وارد ذهب (عيار 18)", 6.5, row="7", note="مسترجع الأشجار"),
    inv(4, "كاستنج", "صرف كاستنج", 60.0, row="4"),
    inv(5, "كاستنج", "قبض كاستنج", 57.4, row="4"),
    inv(6, "مسترجع كاستنج", "وارد ذهب (عيار 18)", 1.0, row="9"),         # مسترجع لصف بلا صرف/قبض
    inv(7, "مسترجع كاستنج", "وارد ذهب (عيار 18)", 2.0),                  # مسترجع قديم بلا صف (شاشة الوارد)
]}
rows = app.collect_stage_ops_rows("صرف كاستنج", "قبض كاستنج", "مسترجع كاستنج")
by_row = {r: g for r, _n, g in rows}
assert by_row["7"]["مسترجع"] == 6.5 and by_row["7"]["مدين"] == 80.0 and by_row["7"]["دائن"] == 70.0
assert 3 in by_row["7"]["ids"] and by_row["7"]["البيان"] == ""
print("✔ مسترجع الأشجار يُلحق بصفه (٧) في الجدول، ويُحذف ويُعدَّل معه")
khayas_rows = sum(round(g["مدين"] - g["دائن"] - g["مسترجع"], 2) for g in by_row.values())
assert by_row["9"]["مسترجع"] == 1.0
box = app.get_box_khayas_cumulative("الكاستنج")
assert round(khayas_rows - 2.0, 2) == box, (khayas_rows, box)
print(f"✔ خياس الصف = الصرف − القبض − المسترجع، ومجموع الصفوف ({khayas_rows:.2f}) − المسترجع العام بلا صف (2.00) = خياس الصندوق ({box:.2f})")
assert [r for r, _n, _g in rows] == ["4", "7", "9"]
print("✔ الصفوف مرتبة تصاعدياً برقم الصف")

cast = seg("submit_casting_op")
assert '"وارد ذهب (عيار 18)"' in cast and '"الاسم": recover_name' in cast
assert "skipped.append(\"مسترجع الأشجار\")" in cast
print("✔ الترحيل: وارد باسم «مسترجع كاستنج» ورقم الصف، وخانة المسترجع مرة واحدة لكل صف")
rst = seg("render_stage_ops_table")
assert '("صرف", "قبض") + rec_col + ("الخياس"' in rst
print("✔ عمود «مسترجع الأشجار» بعد عمود القبض مباشرة")
assert 'recover_name=self.get_stage_config("الكاستنج")[2]' in seg("edit_selected_casting_row")
assert "ent_rec" in seg("open_stage_op_edit_dialog")
print("✔ نافذة التعديل تعرض مسترجع الأشجار وتحفظه")

# ═══ ٣) قاعدة الصف والخانة للمصنعين والمركبين ═══
P = build(["plan_unified_values", "row_set_numbers", "inv_period", "inv_in_period"])


class Ent:
    def __init__(self, v): self.v = v
    def get(self): return self.v


app = P()
app.current_display_month = M
app.invoices = {i["رقم الفاتورة"]: i for i in [
    inv(1, "يوسف", "صرف ذهب", 50.0, row="1", set_no="101"),
    inv(2, "يوسف", "قبض ذهب", 40.0, row="1", set_no="101"),
    inv(3, "أحمد", "المفنش ٨ بالالف", 3.0, row="1"),      # عامل آخر: لا يمنع
]}
app.current_win_entries = {"رقم الصف": Ent("1"), "صرف ذهب": Ent("12"), "قبض ذهب": (Ent("40"), None),
                           "المفنش ٨ بالالف": Ent("2.5"), "البوليش": Ent(""), "الليز": Ent("0")}
plan, skipped = app.plan_unified_values("يوسف", "1")
assert plan == [("المفنش ٨ بالالف", 2.5)], plan
assert sorted(skipped) == [("صرف ذهب", 50.0), ("قبض ذهب", 40.0)], skipped
print("✔ الصف ١: الصرف والقبض موجودان فلا يُسجَّلان، والمفنش ٨ غير موجود فيُسجَّل")
plan2, skipped2 = app.plan_unified_values("يوسف", "2")
assert [t for t, _ in plan2] == ["صرف ذهب", "قبض ذهب", "المفنش ٨ بالالف"] and not skipped2
print("✔ الصف ٢ فارغ: كل الخانات تُسجَّل، والخانات الفارغة والصفرية تُتجاهل")
assert app.row_set_numbers("يوسف", "1") == {"101"} and app.row_set_numbers("يوسف", "2") == set()
sub = seg("submit_unified_op")
assert sub.index("self.plan_unified_values(name, row_now)") < sub.index('askyesno("تأكيد الترحيل", msg)')
assert "لن تُسجَّل (موجودة في الصف نفسه)" in sub and "row_set_numbers" in sub
print("✔ التأكيد يعرض ما سيُسجَّل وما هو موجود في الصف، ورقم تشغيل مختلف لصف قائم يُرفض")

# ═══ ٤) الكشف يجمع ولا يستبدل ═══
for fn in ("refresh_op_ledger_table", "open_worker_ledger_window"):
    body = seg(fn)
    assert 'data["صرف"] = w' not in body and "LEDGER_FIELD_BY_TYPE.get(t)" in body, fn
print("✔ كشف العامل يجمع حركات الصف من النوع نفسه (مطابق لصندوق الخياس) في الموضعين")

# ═══ ٥) بنية الشاشات ═══
sales = seg("build_sales_tab")
assert "tk.Canvas" not in sales and "yview_scroll" not in sales
print("✔ المبيعات: لا تمرير للشاشة — التمرير للجدول وحده")
assert sales.index('commit_bar.pack(side="bottom"') < sales.index("self.pending_sales_table_frame.pack(")
assert sales.count("self.commit_sale_invoice") == 1
print("✔ شريط أسفل الجدول فيه زر الترحيل وحده، والجدول يأخذ ما بينه وبين الأعلى")
assert "btn_add_row.grid(" in sales and "fields_row.grid_columnconfigure" in sales
print("✔ زر إضافة السطر في صف الخانات أعلى الشاشة، والصف يتكيّف مع عرض الشاشة")
pend = seg("refresh_pending_sales_table")
first_col = pend[pend.index("cols = (") + 8:].split(",")[0].strip()
assert first_col == "act" and "الصافي" not in pend[pend.index("cols = ("):pend.index("self.pending_sales_tree, _t")]
assert 'tree.heading(act, text="")' in pend and 'iid=f"row{idx}"' in pend
print("✔ أول عمود بلا عنوان فيه ✏️ و🗑️، وعمود الصافي محذوف")
assert "_selected_pending_index" in seg("delete_pending_sale_row") and "askyesno" in seg("delete_pending_sale_row")
assert "_selected_pending_index" in seg("edit_pending_sale_row") and "_pending_row_index" in seg("_selected_pending_index")
R = build(["_pending_row_index"])
r = R(); r.pending_sale_rows = [{}, {}, {}]
assert r._pending_row_index("row2") == 2 and r._pending_row_index("total") is None and r._pending_row_index("row9") is None
print("✔ الحذف والتعديل يصيبان السطر الصحيح حتى مع العرض التنازلي، والحذف بتأكيد")
fields = [k for _l, k in ast.literal_eval(class_attr_src("SALE_EDIT_FIELDS").split("=", 1)[1].strip())]
assert fields == ["set_number", "ذهب", "فصوص", "أحجار", "الماس", "أحجار بعد الخصم", "خياس",
                  "خياس البوليش", "خياس المركب"], fields
assert "new_row = dict(row)" in seg("edit_pending_sale_row")
print("✔ نافذة التعديل الأفقية تعرض كل خانات الصف وتحفظها كلها (كانت تُسقط البوليش والمركب)")

ops = seg("build_operations_tab")
assert "مراحل التصنيع: {" not in ops and ops.index("self.stage_bar.pack") < ops.index("self.mfg_inst_container")
print("✔ مراحل التصنيع: لا عنوان نصي، وشريط الأقسام أعلى الشاشة")
for b in ("build_casting_ui", "build_polish_ui", "build_polish_buff_ui", "build_generic_stage_ui"):
    assert "self.build_stage_panel(" in seg(b), b
print("✔ الأقسام كلها بلوحة موحّدة مضغوطة: صف إدخال واحد ثم الجدول بكامل المساحة")
assert '("recover", "مسترجع الأشجار")' in seg("build_casting_ui")

loss = seg("refresh_losses_cards") + seg("refresh_losses_tab")
assert '"detail"' not in loss and "get_box_breakdown_text" not in loss
print("✔ شاشة الخسائر: بلا نص التفصيل في لوحات الصناديق")

home = seg("build_home_screen")
assert "tint_logo(" in home
print("✔ شعار الرئيسية بالأزرق على الأبيض")

print("\n✅ الواجهات والمحاسبة (الدفعة الثالثة) سليمة")
