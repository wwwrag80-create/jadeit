# -*- coding: utf-8 -*-
"""اختبار شاشة ربح/خسارة الطقم: نسب الاسترجاع، الربح، وفصل الخسارة"""
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

WANT = ["get_recovery_pct", "set_recovery_pct", "get_sets_profit_rows",
        "get_sets_profit_totals", "get_set_khayas_breakdown", "get_sets_net_rows",
        "get_sets_gems_stones"]
chunks = []
for m in cls.body:
    if isinstance(m, ast.FunctionDef) and m.name in WANT:
        chunks.append(textwrap.dedent(ast.get_source_segment(src, m)))
assert len(chunks) == len(WANT), len(chunks)

ns = dict(marks)
ns["SALE_READ_STATUSES"] = ("ACTIVE", "SETTLED_INOUT", "MEMO")
exec("class S:\n    RECOVERY_KEYS = ((\'تلميع\',\'خياس التلميع النهائي\'),(\'بوليش\',\'خياس البوليش\'),(\'مركب\',\'خياس المركب\'))\n    RECOVERY_DEFAULT = 0.0\n    @staticmethod\n    def inv_period(inv):\n        p = (inv.get(\"period\") or \"\").strip()\n        return p if p else str(inv.get(\"التاريخ\", \"\"))[:7]\n    @classmethod\n    def inv_in_period(cls, inv, month):\n        return True if not month else cls.inv_period(inv) == month\n" + "\n".join(textwrap.indent(c, "    ") for c in chunks) + """
    def __init__(self): self._s = {}
    def get_setting(self, k, d=None): return self._s.get(k, d)
    def set_setting(self, k, v): self._s[k] = str(v)
""", ns)
app = ns["S"]()


def mk(i, set_no, w, mark, month="2026-08"):
    return {"رقم الفاتورة": i, "النوع": "خياس طقوم", "الوزن": w, "trees_count": mark,
            "set_number": set_no, "التاريخ": f"{month}-05 10:00:00",
            "settled_status": "MEMO" if mark != marks["KHAYAS_MARK_FINAL"] else "ACTIVE"}


app.invoices = {
    1: mk(1, "T-1", 10.0, marks["KHAYAS_MARK_FINAL"]),
    2: mk(2, "T-1",  4.0, marks["KHAYAS_MARK_POLISH"]),
    3: mk(3, "T-1",  2.0, marks["KHAYAS_MARK_ASSEMBLER"]),
    4: mk(4, "T-2",  5.0, marks["KHAYAS_MARK_FINAL"]),
    5: mk(5, "T-3",  8.0, marks["KHAYAS_MARK_FINAL"]),
    # سطر الصافي يجب ألا يدخل في هذه الشاشة
    9: mk(9, "T-1", 99.0, marks["KHAYAS_MARK_NET"]),
}

# مبيعات فصوص وأحجار لكل طقم (تدخل عمود فصوص/أحجار)
def gem(i, set_no, w, is_stone, month="2026-08"):
    return {"رقم الفاتورة": i, "النوع": "مبيعات فصوص وأحجار", "الوزن": w,
            "trees_count": 3 if is_stone else 0, "set_number": set_no,
            "التاريخ": f"{month}-05 10:00:00", "settled_status": "ACTIVE"}

app.invoices[30] = gem(30, "T-1", 20.0, False)   # فصوص
app.invoices[31] = gem(31, "T-1", 6.0, True)     # أحجار بعد الخصم
app.invoices[32] = gem(32, "T-2", 5.0, False)

# ---------- النسبة الافتراضية صفر ----------
assert app.get_recovery_pct("تلميع") == 0.0
rows = app.get_sets_profit_rows("2026-08")
t1 = next(r for r in rows if r["رقم التشغيل"] == "T-1")
assert t1["إجمالي"] == 16.0 and t1["المسترجع"] == 0.0
assert t1["صافي/خياس"] == 16.0, t1
assert t1["فصوص/أحجار"] == 26.0, t1
assert t1["الربح"] == round(26.0 - 16.0, 2) == 10.0, t1
print("✔ فصوص/أحجار = الفصوص + الأحجار بعد الخصم = 26.0")
print("✔ صافي/خياس = إجمالي الخياس − المسترجع = 16.0")
print("✔ الربح = فصوص/أحجار − صافي/خياس = 10.0")
assert t1["تلميع"] == 10.0 and t1["بوليش"] == 4.0 and t1["مركب"] == 2.0
print("✔ الخياسات الثلاثة مفصولة صحيحاً (سطر الصافي 99 لم يدخل)")

# ---------- نسبة لكل نوع على حدة ----------
app.set_recovery_pct("تلميع", 90)
app.set_recovery_pct("بوليش", 50)
app.set_recovery_pct("مركب", 25)
assert app.get_recovery_pct("تلميع") == 90.0

rows = app.get_sets_profit_rows("2026-08")
t1 = next(r for r in rows if r["رقم التشغيل"] == "T-1")
expected_rec = round(10 * 0.90 + 4 * 0.50 + 2 * 0.25, 2)
assert expected_rec == 11.5, expected_rec
assert t1["المسترجع"] == 11.5, t1
assert t1["صافي/خياس"] == 4.5, t1
assert t1["الربح"] == round(26.0 - 4.5, 2) == 21.5, t1
print(f"✔ المسترجع لكل نوع بنسبته: (10×90% + 4×50% + 2×25%) = {t1['المسترجع']}")
print(f"✔ صافي/خياس = 16.0 − 11.5 = {t1['صافي/خياس']}")
print(f"✔ الربح = 26.0 − 4.5 = {t1['الربح']}")

# مثال المستخدم: خياس تلميع ٥ بنسبة ٩٠٪ → مسترجع ٤.٥
t2 = next(r for r in rows if r["رقم التشغيل"] == "T-2")
assert t2["المسترجع"] == 4.5 and t2["صافي/خياس"] == 0.5
print("✔ مثالك: خياس تلميع 5 بنسبة 90% → مسترجع 4.5")

# ---------- الخسارة: طقم بلا فصوص/أحجار كافية لتغطية خياسه ----------
app.set_recovery_pct("تلميع", 0)   # لا استرجاع → صافي/خياس = 8.0 للطقم T-3
rows = app.get_sets_profit_rows("2026-08")
t3 = next(r for r in rows if r["رقم التشغيل"] == "T-3")
assert t3["فصوص/أحجار"] == 0.0 and t3["صافي/خياس"] == 8.0
assert t3["خسارة"] == 8.0 and t3["الربح"] == 0.0, t3
print(f"✔ الطقم الخاسر (فصوص/أحجار 0 مقابل خياس 8): خسارة {t3['خسارة']} ويخرج من عمود الربح")

t1b = next(r for r in rows if r["رقم التشغيل"] == "T-1")
assert t1b["خسارة"] == 0.0 and t1b["الربح"] > 0
print(f"✔ الطقم الرابح يبقى في عمود الربح ({t1b['الربح']})")

# ---------- الإجماليات ----------
tot = app.get_sets_profit_totals("2026-08")
assert tot["عدد"] == 3
assert tot["الربح"] == round(sum(r["الربح"] for r in rows), 2)
assert tot["خسارة"] == round(sum(r["خسارة"] for r in rows), 2)
print(f"✔ الإجماليات: {tot['عدد']} أطقم | ربح {tot['الربح']} | خسارة {tot['خسارة']}")
print("✔ الربح والخسارة لا يتقاصّان (كل منهما في عموده)")

# ---------- النسبة محفوظة وتُقيَّد بين 0 و100 ----------
app.set_recovery_pct("بوليش", 500)
assert app.get_recovery_pct("بوليش") == 100.0   # لا يمكن استرجاع أكثر من الخياس نفسه
app.set_recovery_pct("بوليش", -20)
assert app.get_recovery_pct("بوليش") == 0.0
app.set_recovery_pct("بوليش", "نص")
assert app.get_recovery_pct("بوليش") == 0.0
print("✔ النسبة تُقيَّد بين 0 و100 والقيم غير الرقمية تُتجاهل بلا خطأ")

# ---------- شهر بلا أطقم ----------
assert app.get_sets_profit_totals("2026-01")["عدد"] == 0
print("✔ شهر بلا أطقم يرجع صفراً بلا خطأ")

# ---------- الشاشة لا تؤثر على الخزينة ----------
prof = ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                        and m.name == "get_sets_profit_rows"))
assert "save_invoice_to_db" not in prof and "delete_invoice" not in prof
print("✔ الشاشة عرض فقط — لا تكتب أي حركة محاسبية")

print("\n✅ كل اختبارات ربح/خسارة الطقم نجحت")
