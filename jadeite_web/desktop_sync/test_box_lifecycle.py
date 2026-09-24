# -*- coding: utf-8 -*-
"""اختبار دورة حياة صندوق الخياس: الإنشاء، العمل عليه، ثم الحذف الكامل"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

WANT = ["invoices_by_name", "invoices_by_period", "period_invoices", "get_stage_config", "get_box_account_name", "get_all_stage_categories",
        "get_display_label", "get_box_khayas_cumulative", "count_box_transactions",
        "get_deletable_khayas_boxes", "get_all_mustarja_names"]
chunks = []
for m in cls.body:
    if isinstance(m, ast.FunctionDef) and m.name in WANT:
        code = textwrap.dedent(ast.get_source_segment(src, m))
        for d in m.decorator_list:
            code = "@" + ast.get_source_segment(src, d) + "\n" + code
        chunks.append(code)
assert len(chunks) == len(WANT), len(chunks)

ns = {}
exec("class S:\n    BOX_DISPLAY_OVERRIDES = {}\n    @staticmethod\n    def inv_period(inv):\n        p = (inv.get(\"period\") or \"\").strip()\n        return p if p else str(inv.get(\"التاريخ\", \"\"))[:7]\n    @classmethod\n    def inv_in_period(cls, inv, month):\n        return True if not month else cls.inv_period(inv) == month\n" + "\n".join(textwrap.indent(c, "    ") for c in chunks), ns)
app = ns["S"]()
app.current_display_month = "2026-08"
app.categories = {"أقسام_خياس_إضافية": ["الصب", "ورشة الحفر"]}


def inv(i, t, w, name=""):
    return {"رقم الفاتورة": i, "النوع": t, "الوزن": w, "الاسم": name,
            "settled_status": "ACTIVE", "التاريخ": "2026-08-05 10:00:00"}


# ---------- أي صندوق مضاف يدوياً يعمل كالكاستنج تماماً ----------
# (قسم الصب لم يعد يُنشأ تلقائياً؛ نضيفه هنا كصندوق مضاف للاختبار)
assert "الصب" in app.get_all_stage_categories()
madin, qabd, mustarja = app.get_stage_config("الصب")
assert (madin, qabd, mustarja) == ("صرف الصب", "قبض الصب", "مسترجع الصب")
assert app.get_box_account_name("الصب") == "الصب"
assert "مسترجع الصب" in app.get_all_mustarja_names()
print("✔ الصب: صندوق كامل بصرف وقبض ومسترجع وحساب — تماماً كالكاستنج والبوليش")

kast = app.get_stage_config("الكاستنج")
assert len(kast) == len(app.get_stage_config("الصب")) == 3
print("✔ يُعامل بنفس بنية باقي الصناديق (لا استثناء في المنطق)")

# ---------- العمل عليه ----------
app.invoices = {
    1: inv(1, "صرف الصب", 100.0, "الصب"),
    2: inv(2, "قبض الصب", 96.0, "الصب"),
    3: inv(3, "وارد ذهب (عيار 18)", 1.0, "مسترجع الصب"),
    9: inv(9, "صرف كاستنج", 50.0, "الكاستنج"),      # صندوق آخر — يجب ألا يتأثر
}
assert app.get_box_khayas_cumulative("الصب", month="") == 3.0
print(f"✔ خياس الصب يُحسب صحيحاً: {app.get_box_khayas_cumulative('الصب')} (صرف 100 − قبض 96 − مسترجع 1)")

# ---------- الحذف ----------
n = app.count_box_transactions("الصب")
assert n == 3, n
print(f"✔ عدّ الحركات المرتبطة قبل الحذف: {n} (صرف + قبض + مسترجع)")

assert app.count_box_transactions("ورشة الحفر") == 0
print("✔ صندوق بلا حركات يُعدّ صفراً — الحذف آمن")

# ---------- الصناديق الأساسية محميّة ----------
deletable = set(app.get_deletable_khayas_boxes())
assert {"الصب", "ورشة الحفر"} <= deletable
assert {"الكاستنج", "التلميع", "خياس الطقوم"} <= deletable
print(f"✔ كل الصناديق قابلة للحذف الآن ({len(deletable)} صندوق) — الأساسية والمضافة")

print("\n✅ دورة حياة صندوق الخياس سليمة")
