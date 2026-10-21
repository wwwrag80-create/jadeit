# -*- coding: utf-8 -*-
"""
نقل صف إلى رقم صف مستخدم ممنوع (1.71): صفوف الأقسام تُجمع برقم الصف، فكان تعديل رقم الصف ١١ إلى ١٠
يدمج الصفّين — تختلط بياناتهما ويختفي الصف ١١. الآن يُمنع النقل في كل الأقسام (الكاستنج والتلميع وبوليش 1
والأقسام المضافة) وفي المصنعين والمركبين ونقل الصف لعامل آخر، والأرقام الهندية كالعربية.
"""
import ast, io, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    return textwrap.dedent(ast.get_source_segment(src, node))


MEMBERS = ("_DATE_DIGITS", "TREE_RETURN_NAME", "norm_row_no", "stage_row_extra", "stage_row_number_taken",
           "worker_row_number_taken")
ns = {}
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)


class App(ns["Base"]):
    def __init__(self):
        self.rows = []

    def period_invoices(self, period):
        return [r for r in self.rows if r["period"] == period]

    def add(self, name, t, w, row, period="2026-10", status="ACTIVE"):
        inv = {"رقم الفاتورة": len(self.rows) + 1, "الاسم": name, "النوع": t, "الوزن": w,
               "row_number": row, "period": period, "settled_status": status}
        self.rows.append(inv)
        return inv["رقم الفاتورة"]


a = App()
S, Q = "صرف كاستنج", "قبض كاستنج"
r10 = [a.add("كاستنج", S, 20, "10"), a.add("كاستنج", Q, 18, "10")]
r11 = [a.add("كاستنج", S, 15, "11"), a.add("كاستنج", Q, 14, "11")]
a.add("كاستنج", S, 5, "12", period="2026-09")                        # فترة أخرى
a.add("كاستنج", S, 3, "13", status="ARCHIVED")                         # مؤرشف
a.add(a.TREE_RETURN_NAME, Q, 1, "14")                                  # مسترجع أشجار وحده على الصف ١٤
a.add("كاستنج", "صرف تلميع", 9, "15")                                  # قسم آخر

taken = lambda new, old="11", ids=r11, **k: a.stage_row_number_taken(new, old, "كاستنج", S, Q, "2026-10", ids, **k)
assert taken("10"), "١١ ← ١٠ (فيه بيانات) ممنوع"
assert taken("١٠"), "الأرقام الهندية كالعربية"
assert taken(" 10 ")
assert not taken("11") and not taken("") and not taken("16")
assert not taken("12") and not taken("13") and not taken("15"), "فترة أخرى أو مؤرشف أو قسم آخر لا يمنع"
assert not taken("14") and taken("14", recover_name="مسترجع"), "مسترجع الأشجار يُلحق بصفه حيث يُعرض"
assert not a.stage_row_number_taken("10", "", "التلميع", S, Q, "2026-10", []), "اسم صف آخر = صف آخر"
print("✔ الأقسام: نقل الصف ١١ إلى ١٠ (أو ١٠ بالهندية) ممنوع؛ ورقم غير مستخدم، أو من فترة أخرى، أو مؤرشف، "
      "أو قسم آخر مسموح")

b = App()
w1 = [b.add("أحمد", "صرف ذهب", 10, "1"), b.add("أحمد", "قبض ذهب", 9, "1")]
w2 = [b.add("أحمد", "صرف ذهب", 7, "2")]
b.add("سالم", "صرف ذهب", 4, "3")
assert b.worker_row_number_taken("أحمد", "1", "2", "2026-10", w2)
assert not b.worker_row_number_taken("أحمد", "3", "2", "2026-10", w2), "صف ٣ لعامل آخر"
assert not b.worker_row_number_taken("أحمد", "2", "2", "2026-10", w2)
# نقل صف (أحمد ٣ ← سالم): لسالم صف ٣ ← ممنوع، ولسالم لا صف ١ ← مسموح
assert b.worker_row_number_taken("سالم", "3", "", "2026-10", [])
assert not b.worker_row_number_taken("سالم", "1", "", "2026-10", w1)
print("✔ المصنعين والمركبين: نقل صف إلى رقم صف للعامل نفسه ممنوع، ونقل صف لعامل آخر عنده الرقم نفسه ممنوع")

# ═══ الربط في النوافذ ═══
stage = member("open_stage_op_edit_dialog")
assert "self.stage_row_number_taken(new_row_no, ref_row, ref_name" in stage
assert stage.index("stage_row_number_taken") < stage.index("self.push_undo(") < stage.index("upsert(sarf_invs")
row = member("open_row_full_edit_dialog")
assert "self.worker_row_number_taken(worker_name, new_row_no, row_key, month" in row
assert row.index("worker_row_number_taken") < row.index("self.push_undo(")
assert "self.worker_row_number_taken(new_worker, gkey" in member("reassign_op_ledger_row")
print("✔ المنع قبل أي حفظ في نافذة تعديل الأقسام ونافذة المصنعين/المركبين ونقل الصف لعامل آخر")

# الخانة = ما في الجدول: مجموع حركات النوع، والحفظ يجعلها حركة واحدة
assert "shown(total(sarf_invs))" in stage and "for dup in existing_list[1:]:" in stage
# خانة الحركة (movement_slot): نوعها، والسلاسل خانة مستقلة عن قبض/٨ وإن كانت حركتها مفنش ٨ (1.84)
assert "for dup in existing_list[1:]:" in row and "by_type.setdefault(self.movement_slot(inv), []).append(inv)" in row
print("✔ صف فيه أكثر من حركة للنوع نفسه: الخانة مجموعها (كما في الجدول) والحفظ يجعلها حركة واحدة بالقيمة المكتوبة")

save = member("save_invoice_to_db")
assert "if self.invoices.get(inv_id) is not inv_data:" in save and "self.invoices[inv_id] = inv_data" in save
print("✔ الذاكرة تتبع كل حفظ (تعديل رقم التشغيل ونقل الصف كانا يحفظان نسخة فيبقى الجدول على القديم)")
print("\n✅ لا تُدمج الصفوف بالتعديل، وما يُكتب في نافذة التعديل هو ما يظهر في الجدول")
