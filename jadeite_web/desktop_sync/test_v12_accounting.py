# -*- coding: utf-8 -*-
"""اختبارات محاسبية: خياس المركب، فصل خياس المصنعين/المركبين، ربح/خسارة الطقم"""
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
assert len(set(marks.values())) == len(marks), marks
print(f"✔ علامات التمييز فريدة: {marks}")

# ---------- ١) معادلة الصافي مع خياس المركب ----------
fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "sale_net_weight")
ns = {}
exec(ast.get_source_segment(src, fn), ns)
net = ns["sale_net_weight"]

row = {"ذهب": 100.0, "فصوص": 20.0, "أحجار بعد الخصم": 6.0,
       "خياس": 1.5, "خياس البوليش": 0.5, "خياس المركب": 2.0}
assert net(row) == round(20 + 6 - 1.5 - 0.5 - 2.0, 2) == 22.0
print(f"✔ الصافي = (الفصوص + الأحجار بعد الخصم) − الخياسات الثلاثة = {net(row)}")

# ---------- ٢) خياس المركب من مراحل التصنيع ----------
chunks = []
for name in ("get_assembler_khayas_for_set",):
    m = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name)
    chunks.append(textwrap.dedent(ast.get_source_segment(src, m)))
raji_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "raji_ayar")
ns2 = {"RAJI_PURITY": 750.0, "ALLOWANCE_8": 0.008}
exec(ast.get_source_segment(src, raji_fn), ns2)
exec("class S:\n" + "\n".join(textwrap.indent(c, "    ") for c in chunks), ns2)
app = ns2["S"]()
app.current_display_month = "2026-08"
app.categories = {"المركبين": ["سالم", "خالد"], "المصنعين": ["أحمد"]}


def inv(i, name, t, w, set_no="T-1", month="2026-08"):
    return {"رقم الفاتورة": i, "الاسم": name, "النوع": t, "الوزن": w,
            "set_number": set_no, "settled_status": "ACTIVE",
            "التاريخ": f"{month}-05 10:00:00"}


app.invoices = {
    1: inv(1, "سالم", "صرف ذهب", 100.0),
    2: inv(2, "سالم", "قبض ذهب", 97.0),
    3: inv(3, "خالد", "صرف ذهب", 50.0),
    4: inv(4, "خالد", "قبض ذهب", 48.5),
    # عامل من قسم آخر بنفس رقم التشغيل — يجب ألا يُحتسب
    5: inv(5, "أحمد", "صرف ذهب", 999.0),
    # رقم تشغيل مختلف — يجب ألا يُحتسب
    6: inv(6, "سالم", "صرف ذهب", 777.0, set_no="T-9"),
}

# المصدر الآن عمود (مسموح/٨) = القبض × ٨ بالألف
v = app.get_assembler_khayas_for_set("T-1")
assert v == round(97 * 0.008 + 48.5 * 0.008, 2), v
print(f"✔ خياس المركب لرقم التشغيل T-1 = {v} (مجموع مسموح/٨ لكل عمال المركبين)")
assert app.get_assembler_khayas_for_set("") == 0.0
assert app.get_assembler_khayas_for_set("لا-يوجد") == 0.0
print("✔ عمال المصنعين وأرقام التشغيل الأخرى مستثناة تماماً")

# ---------- ٣) فصل خياس المصنعين/المركبين ----------
m = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == "get_section_khayas_split")
ns3 = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(ast.get_source_segment(src, m)), "    ") + """
    def calculate_single_ledger(self, n, cat, target_month=None, include_settled=False):
        return self._ledgers[n]
""", ns3)
app3 = ns3["S"]()
app3.categories = {"المصنعين": ["أ", "ب", "ج"]}
app3._ledgers = {
    "أ": {"مسموح 8": 0.4, "مسموح 4": 0.12, "الخياس": -3.0},   # عجز
    "ب": {"مسموح 8": 0.2, "مسموح 4": 0.08, "الخياس": 5.0},    # فائض
    "ج": {"مسموح 8": 0.1, "مسموح 4": 0.00, "الخياس": -1.5},   # عجز
}
allow, workers, returned, total = app3.get_section_khayas_split("المصنعين")
assert allow == round(0.4 + 0.12 + 0.2 + 0.08 + 0.1, 2) == 0.9, allow
assert workers == 4.5, workers      # 3.0 + 1.5 (العجز)
assert returned == 5.0, returned    # الرصيد الموجب
# المعادلة المعتمدة: خياس العمال + فاقد (٨/٤) − راجع العمال
assert total == round(4.5 + 0.9 - 5.0, 2) == 0.4, total
print(f"✔ خياس العمال = {workers} | فاقد (٨/٤) = {allow} | راجع العمال = {returned}")
print(f"✔ الخياس الفعلي = {workers} + {allow} − {returned} = {total}")

print("\n✅ كل الاختبارات المحاسبية للدفعة الثانية عشرة نجحت")
