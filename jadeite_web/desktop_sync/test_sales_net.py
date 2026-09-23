# -*- coding: utf-8 -*-
"""اختبار محاسبي: صافي الطقم، فصل خياس البوليش، وعمودا الصافي/الخسارة"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)

# ---------- ١) معادلة الصافي ----------
fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "sale_net_weight")
ns = {}
exec(ast.get_source_segment(src, fn), ns)
net = ns["sale_net_weight"]

row = {"ذهب": 100.0, "فصوص": 20.0, "أحجار": 50.0, "أحجار بعد الخصم": 6.0,
       "الماس": 3.0, "خياس": 1.5, "خياس البوليش": 0.5}
assert net(row) == round(20 + 6 - 1.5 - 0.5, 2) == 24.0
print(f"✔ الصافي = (الفصوص + الأحجار بعد الخصم) − خياس التلميع − خياس البوليش = {net(row)}")

# الذهب والأحجار الخام والماس خارج المعادلة (تحقق صريح)
r2 = dict(row); r2["ذهب"] = 999.0; r2["أحجار"] = 999.0; r2["الماس"] = 999.0
assert net(r2) == net(row)
print("✔ الذهب والأحجار الخام والماس لا تؤثر على الصافي إطلاقاً")

assert net({}) == 0.0
assert net({"ذهب": "غير رقم"}) == 0.0
print("✔ القيم الناقصة أو غير الرقمية لا تُسبب خطأ")

# صافي سالب ممكن (خسارة)
# الخسارة تحدث عندما تتجاوز الخياسات قيمة الفصوص والأحجار
r3 = {"ذهب": 10.0, "فصوص": 1.0, "أحجار بعد الخصم": 2.0, "خياس": 4.0, "خياس البوليش": 2.0}
assert net(r3) == -3.0
print(f"✔ الصافي قد يكون سالباً (خسارة): {net(r3)}")

# ---------- ٢) علامات التمييز فريدة ----------
marks = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id.startswith("KHAYAS_MARK_"):
                marks[t.id] = node.value.value
assert len(set(marks.values())) == len(marks), marks
assert marks["KHAYAS_MARK_FINAL"] == 0.0
print(f"✔ علامات تمييز الخياس فريدة ولا تتعارض: {marks}")

# العلامة الافتراضية = 0.0 فتبقى بيانات العملاء القديمة مقروءة كخياس تلميع نهائي
print("✔ العلامة الافتراضية 0.0 — بيانات العملاء القديمة تُقرأ كخياس تلميع نهائي بلا ترحيل")

# ---------- ٣) فصل الصافي إلى صافي/خسارة ----------
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
chunks = []
for name in ("get_sets_net_rows", "get_sets_net_totals"):
    m = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name)
    chunks.append(textwrap.dedent(ast.get_source_segment(src, m)))

ns2 = {"KHAYAS_MARK_NET": marks["KHAYAS_MARK_NET"],
       "SALE_READ_STATUSES": ("ACTIVE", "SETTLED_INOUT", "MEMO")}
exec("class S:\n    @staticmethod\n    def inv_period(inv):\n        p = (inv.get(\"period\") or \"\").strip()\n        return p if p else str(inv.get(\"التاريخ\", \"\"))[:7]\n    @classmethod\n    def inv_in_period(cls, inv, month):\n        return True if not month else cls.inv_period(inv) == month\n" + "\n".join(textwrap.indent(c, "    ") for c in chunks), ns)