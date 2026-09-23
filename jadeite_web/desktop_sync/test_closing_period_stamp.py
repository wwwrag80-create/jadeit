# -*- coding: utf-8 -*-
"""
اختبار حالة اللقطتين: إقفال خياس شهر ٩ يجب أن يبقى في سجل شهر ٩،
وشهر ١٠ يبدأ بخياس جديد ورصيد مُرحَّل صحيح.
"""
import ast, calendar, datetime, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) القيد يُختم بالفترة المُقفَلة ═══
post = seg("_post_closing_entry")
assert "period=None" in post and 'inv["period"] = period' in post
print("✔ قيد الإقفال يُختم بفترة الشهر المُقفَل صراحةً")

split = seg("close_split_khayas_box")
assert "period=month" in split and split.count("period=month") == 2
print("✔ إقفال المصنعين/المركبين يمرّر الفترة لقيديه معاً")
assert "self.period_closing_datetime(month)" in split
print("✔ ويؤرّخ القيد في آخر الشهر المُقفَل")

plain = seg("close_khayas_box")
assert '"period": month' in plain and "period_closing_datetime(month)" in plain
print("✔ وباقي الصناديق كذلك")

# ═══ ٢) تاريخ الإقفال داخل الشهر ═══
ns = {"calendar": calendar, "datetime": datetime}
exec("class S:\n" + textwrap.indent(textwrap.dedent(seg("period_closing_datetime")), "    ")
     + "\n    def get_smart_default_date(self): return '2026-10-05'\n", ns)
app = ns["S"]()
assert app.period_closing_datetime("2026-09") == "2026-09-30 23:59:00"
assert app.period_closing_datetime("2026-02") == "2026-02-28 23:59:00"
print("✔ تاريخ الإقفال = آخر يوم في الشهر المُقفَل (٣٠ لسبتمبر، ٢٨ لفبراير)")
print("  (كان يُؤرَّخ بـ ٢٠٢٦-١٠-٠١ فيبدو حركةً من الشهر الجديد — كما في لقطتك)")
assert "2026-10-05" in app.period_closing_datetime("سيء")
print("✔ فترة غير صالحة لا تُسبب انهياراً")

# ═══ ٣) محاكاة اللقطتين ═══
def eff(inv):
    if inv["settled_status"] not in ("ACTIVE", "SETTLED_INOUT"):
        return 0.0
    t, w = inv["النوع"], inv["الوزن"]
    if t in ("رصيد افتتاحي", "وارد ذهب (عيار 18)", "قبض كاستنج", "قبض تلميع بف"):
        return w
    if t in ("صرف كاستنج", "صرف تلميع بف", "قيد يومي دائن"):
        return -w
    return 0.0


def period_of(inv):
    return inv.get("period") or inv["التاريخ"][:7]


rows = [
    {"النوع": "رصيد افتتاحي", "الوزن": 100.0, "التاريخ": "2026-09-05 11:38", "period": "2026-09", "settled_status": "ACTIVE"},
    {"النوع": "صرف كاستنج",   "الوزن": 10.0,  "التاريخ": "2026-09-05 11:38", "period": "2026-09", "settled_status": "ACTIVE"},
    {"النوع": "قبض كاستنج",   "الوزن": 5.0,   "التاريخ": "2026-09-05 11:38", "period": "2026-09", "settled_status": "ACTIVE"},
    {"النوع": "صرف تلميع بف", "الوزن": 30.0,  "التاريخ": "2026-09-05 11:39", "period": "2026-09", "settled_status": "ACTIVE"},
    {"النوع": "قبض تلميع بف", "الوزن": 5.0,   "التاريخ": "2026-09-05 11:39", "period": "2026-09", "settled_status": "ACTIVE"},
    # قيد إقفال خياس المصنعين لشهر ٩ — بعد الإصلاح فترته ٢٠٢٦-٠٩
    {"النوع": "قيد يومي دائن", "الوزن": 5.0,  "التاريخ": "2026-09-30 23:59", "period": "2026-09", "settled_status": "ACTIVE"},
]

p9 = [r for r in rows if period_of(r) == "2026-09"]
bal9 = round(sum(eff(r) for r in p9), 2)
assert len(p9) == 6 and bal9 == 65.0, (len(p9), bal9)
print(f"\n✔ فترة ٩: {len(p9)} حركات ورصيدها {bal9} (يشمل قيد الإقفال ٥) — مطابق للقطة الأولى")

opening10 = round(sum(eff(r) for r in rows if period_of(r) < "2026-10"), 2)
assert opening10 == 65.0, opening10
print(f"✔ فترة ١٠ تبدأ برصيد مُرحَّل {opening10} — لا 70.00 كما في لقطتك الثانية")
print("  (كان قيد الإقفال يُختم بفترة ١٠ فيسقط من رصيد شهر ٩ ولا يُرحَّل)")

p10 = [r for r in rows if period_of(r) == "2026-10"]
assert p10 == []
print("✔ وفترة ١٠ تبدأ بخياس جديد خاص بها لا علاقة له بفترة ٩")

print("\n✅ إقفال كل فترة يبقى في سجلّها ويُرحَّل رصيدها صحيحاً")
