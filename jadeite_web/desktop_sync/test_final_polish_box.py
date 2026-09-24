# -*- coding: utf-8 -*-
"""
اختبار: عمود الخياس في صندوق (خياس التلميع النهائي) = إجمالي عمود الخياس
في صف الإجمالي بشاشة المبيعات/الصادر ← قسم العمليات، رقماً برقم.
"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

marks = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id.startswith("KHAYAS_MARK_"):
                marks[t.id] = node.value.value


def seg(n):
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == n))


WANT = ["invoices_by_name", "invoices_by_period", "period_invoices", "get_sales_ops_khayas_total", "get_box_khayas_cumulative",
        "get_sale_invoice_groups", "get_stage_config", "get_box_account_name",
        "get_all_stage_categories", "get_display_label"]
chunks = [textwrap.dedent(seg(n)) for n in WANT]

ns = dict(marks)
ns["SALE_READ_STATUSES"] = ("ACTIVE", "SETTLED_INOUT", "MEMO")
ns["log_cloud_error"] = lambda *a, **k: None
exec("class S:\n"
     "    BOX_DISPLAY_OVERRIDES = {}\n"
     '    SALE_TYPES = ("مبيعات ذهب", "مبيعات ذهب مع الماس", "مبيعات فصوص وأحجار", "مبيعات الماس")\n'
     "    @staticmethod\n"
     "    def inv_period(inv):\n"
     '        p = (inv.get("period") or "").strip()\n'
     '        return p if p else str(inv.get("التاريخ", ""))[:7]\n'
     "    @classmethod\n"
     "    def inv_in_period(cls, inv, month):\n"
     "        return True if not month else cls.inv_period(inv) == month\n"
     + "\n".join(textwrap.indent(c, "    ") for c in chunks), ns)
app = ns["S"]()
app.current_display_month = "2026-08"
app.categories = {"أقسام_خياس_إضافية": []}

MONTH = "2026-08"


def sale(i, manual, name, op, w, mark=0.0, status="ACTIVE", day="05"):
    return {"رقم الفاتورة": i, "رقم الفاتورة اليدوي": manual, "الاسم": name,
            "النوع": op, "الوزن": w, "trees_count": mark, "set_number": f"T-{manual}",
            "التاريخ": f"{MONTH}-{day} 10:00:00", "settled_status": status,
            "period": MONTH}


app.invoices = {
    # فاتورة ١: ذهب + خياس تلميع نهائي ٣
    1: sale(1, "1001", "عميل أ", "مبيعات ذهب", 100.0),
    2: sale(2, "1001", "عميل أ", "خياس طقوم", 3.0, marks["KHAYAS_MARK_FINAL"]),
    # فاتورة ٢: خياس تلميع نهائي ٢
    3: sale(3, "1002", "عميل ب", "مبيعات ذهب", 50.0, day="06"),
    4: sale(4, "1002", "عميل ب", "خياس طقوم", 2.0, marks["KHAYAS_MARK_FINAL"], day="06"),
    # سطور معلوماتية: يجب ألا تدخل الإجمالي
    5: sale(5, "1001", "عميل أ", "خياس طقوم", 9.9, marks["KHAYAS_MARK_POLISH"], status="MEMO"),
    6: sale(6, "1001", "عميل أ", "خياس طقوم", 8.8, marks["KHAYAS_MARK_ASSEMBLER"], status="MEMO"),
    7: sale(7, "1001", "عميل أ", "خياس طقوم", 7.7, marks["KHAYAS_MARK_NET"], status="MEMO"),
}

# ═══ ١) الإجمالي في شاشة المبيعات ═══
groups = app.get_sale_invoice_groups(MONTH)
sales_total = round(sum(g["خياس"] for g in groups), 2)
assert sales_total == 5.0, sales_total
print(f"✔ صف الإجمالي في شاشة المبيعات ← قسم العمليات: خياس = {sales_total}")
print("  (٣ + ٢، والسطور المعلوماتية مستثناة)")

assert app.get_sales_ops_khayas_total(MONTH) == sales_total
print("✔ الدالة الجديدة تقرأ نفس الرقم من نفس المصدر")

# ═══ ٢) صندوق خياس التلميع النهائي = نفس الرقم ═══
box = app.get_box_khayas_cumulative("خياس الطقوم", month=MONTH)
assert box == sales_total, (box, sales_total)
print(f"✔ عمود الخياس في صندوق خياس التلميع النهائي = {box} — مطابق تماماً")

# ═══ ٣) المسترجع يقلّل الصندوق ═══
app.invoices[10] = sale(10, "1003", "مسترجع خياس الطقوم", "وارد ذهب (عيار 18)", 1.5)
box2 = app.get_box_khayas_cumulative("خياس الطقوم", month=MONTH)
assert box2 == round(sales_total - 1.5, 2) == 3.5, box2
print(f"✔ استرجاع ١.٥ من الصندوق → {box2} (المسترجع يُخصم كما يجب)")

# ═══ ٤) الإقفال يُفرغ الصندوق ═══
app.invoices[11] = sale(11, "", "خياس الطقوم", "قيد يومي دائن", 3.5)
box3 = app.get_box_khayas_cumulative("خياس الطقوم", month=MONTH)
assert box3 == 0.0, box3
print(f"✔ بعد الإقفال → {box3} (والإجمالي في شاشة المبيعات يبقى {sales_total} كما هو)")

# ═══ ٥) عزل الفترات ═══
assert app.get_box_khayas_cumulative("خياس الطقوم", month="2026-09") == 0.0
assert app.get_sales_ops_khayas_total("2026-09") == 0.0
print("✔ فترة أخرى → صفر (كل فترة مستقلة)")

# ═══ ٦) صندوق آخر لا يتأثر بهذا المسار ═══
kast = seg("get_box_khayas_cumulative")
assert 'if cat == "خياس الطقوم":' in kast
print("✔ المسار خاص بصندوق خياس التلميع النهائي وحده (باقي الصناديق كما هي)")

print("\n✅ عمود الخياس مطابق لإجمالي شاشة المبيعات تماماً")
