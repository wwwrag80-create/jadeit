# -*- coding: utf-8 -*-
"""1.73: تعديل فاتورة المبيعات المرحّلة — السطور برقم الصف ١، ٢، ٣…، وسطر محذوف يعود برقمه ومكانه، وآخر تعديل
في الخانات يُحفظ مع الفاتورة، وتوقيتها لا يتغيّر؛ ولمحة «قبل/بعد» تحت خانة خياس بوليش 2."""
import ast, io, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(node, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, node))


ns = {}
exec("class A:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in (
    "_SET_DIGITS", "normalize_set_number", "sale_row_order", "next_free_sale_row_number")), ns)
A = ns["A"]
rows = [{"row_number": "3"}, {"row_number": "١"}, {"row_number": ""}, {"row_number": "2"}]
assert [r["row_number"] for r in sorted(rows, key=A.sale_row_order)] == ["١", "2", "3", ""]
assert A.next_free_sale_row_number([{"row_number": "1"}, {"row_number": "3"}]) == "2"
assert A.next_free_sale_row_number([{"row_number": "1"}, {"row_number": "٢"}]) == "3"
assert A.next_free_sale_row_number([]) == "1"
print("✔ ترتيب السطور برقم الصف (والهندي كاللاتيني)، وأصغر رقم شاغر لسطر جديد أو معاد")

ed = member("open_sale_invoice_editor")
assert "if has_pending() and not save_row():" in ed and ed.index("has_pending() and not save_row()") < ed.index("push_undo(")
assert "edit_rows.sort(key=self.sale_row_order)" in ed and ed.count("edit_rows.sort(key=self.sale_row_order)") == 2
assert 'new_full_dt = f"{new_date[:10]} {old_time}"' in ed and "if new_date == old_date[:10] else" not in ed
assert 'entries["row_number"].insert(0, self.next_free_sale_row_number(edit_rows))' in ed
assert "self.attach_polish2_hint(entries[\"خياس\"], win," in ed
assert "return sorted((rows[s] for s in order), key=self.sale_row_order)" in member("sale_records_to_rows")
assert 'row_key = set_num or ("#", inv.get("row_number", "") or "")' in member("sale_records_to_rows")
assert "SALE_READ_STATUSES" in member("get_invoice_group_data")
print("✔ آخر تعديل يُحفظ قبل إعادة كتابة الفاتورة، والترتيب عند كل حفظ، والتوقيت ثابت، والمعاينة من الحركات المقروءة")

hint = member("attach_polish2_hint")
assert "after = round(sum(num(e) for e in parts), 2)" in hint and "round(after + num(khayas_entry), 2)" in hint
assert "self.attach_before_after_hint(khayas_entry, host," in hint
generic = member("attach_before_after_hint")
assert '"<FocusIn>", show' in generic and '"<FocusOut>", hide' in generic
assert "self.attach_polish2_hint(self.sale_khayas, tab," in member("build_sales_tab")
print("✔ تحت «خياس بوليش 2»: قبل = الخياس + الذهب + الفصوص + الأحجار + الماس، وبعد = الذهب + الفصوص + الأحجار + الماس")
# «الأحجار بعد الخصم» تُحسب تلقائياً مع تعديل «الأحجار»: بنسبة السطر نفسه، وإلا النسبة الحالية
ns2 = {}
exec("class D:\n" + textwrap.indent(member("sale_discount_ratio"), "    "), ns2)


class Pct:
    def __init__(self, v): self.v = v
    def get(self): return self.v


d = ns2["D"]()
d.get_discount_percentages = lambda: ["30", "25"]
d.get_last_discount_percentage = lambda: "30"
d.sale_discount_pct = Pct("25%")
assert d.sale_discount_ratio({"أحجار": 3.0, "أحجار بعد الخصم": 0.9}) == 0.30
assert d.sale_discount_ratio({"أحجار": 2.03, "أحجار بعد الخصم": 0.61}) == 0.30, "تقريب لأقرب نسبة معروفة"
assert d.sale_discount_ratio({"أحجار": 4.0, "أحجار بعد الخصم": 0.8}) == 0.20, "نسبة خاصة بالسطر تبقى كما هي"
assert d.sale_discount_ratio({"أحجار": 0, "أحجار بعد الخصم": 0}) == 0.25, "سطر جديد: النسبة المختارة في المبيعات"
d.sale_discount_pct = Pct("abc")
assert d.sale_discount_ratio() == 0.30, "وإلا آخر نسبة مستخدمة"
ed = member("open_sale_invoice_editor")
assert 'entries["أحجار"].bind("<KeyRelease>", on_stones, add="+")' in ed
assert "round(raw * disc_state['ratio'], 2)" in ed and "set_disc_ratio(r)" in ed and ed.count("set_disc_ratio()") >= 2
assert 'if text == disc_state["last"]:' in ed
print("✔ تعديل الأحجار في الفاتورة المرحّلة يحسب «الأحجار بعد الخصم» تلقائياً بنسبة السطر (30% ← 2.03 × 30% …) "
      "أو النسبة الحالية لسطر جديد، والتنقّل بالأسهم لا يمسح خصماً عُدّل يدوياً")
print("\n✅ تعديل فواتير المبيعات الصادرة سليم")
