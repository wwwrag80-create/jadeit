# -*- coding: utf-8 -*-
"""اختبار محاسبي: الرصيد الحالي = الخزينة + كل الذهب في الصناديق"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

WANT = ["get_total_gold_balance", "get_gold_balance_breakdown", "get_box_khayas_cumulative", "get_sales_ops_khayas_total", "get_sale_invoice_groups",
        "get_all_stage_categories", "get_stage_config", "get_box_account_name", "get_display_label",
        "get_gold_at_section", "get_section_excess_loss", "get_current_unclosed_khayas",
        "get_box_closed_total", "calculate_single_ledger", "get_actual_section_khayas", "get_section_khayas_split"]
chunks = []
for m in cls.body:
    if isinstance(m, ast.FunctionDef) and m.name in WANT:
        code = textwrap.dedent(ast.get_source_segment(src, m))
        for d in m.decorator_list:
            code = "@" + ast.get_source_segment(src, d) + "\n" + code
        chunks.append(code)
assert len(chunks) == len(WANT), [c.split("(")[0] for c in chunks]

ns = {"ALLOWANCE_8": 0.008, "ALLOWANCE_4": 0.004,
      "SALE_READ_STATUSES": ("ACTIVE", "SETTLED_INOUT", "MEMO"),
      "KHAYAS_MARK_NET": 9.0, "KHAYAS_MARK_POLISH": 7.0,
      "KHAYAS_MARK_ASSEMBLER": 5.0, "KHAYAS_MARK_FINAL": 0.0,
      "log_cloud_error": lambda *a, **k: None}
exec("class S:\n    BOX_DISPLAY_OVERRIDES = {}\n    SALE_TYPES = (\"مبيعات ذهب\", \"مبيعات ذهب مع الماس\", \"مبيعات فصوص وأحجار\", \"مبيعات الماس\")\n    @staticmethod\n    def inv_period(inv):\n        p = (inv.get(\"period\") or \"\").strip()\n        return p if p else str(inv.get(\"التاريخ\", \"\"))[:7]\n    @classmethod\n    def inv_in_period(cls, inv, month):\n        return True if not month else cls.inv_period(inv) == month\n" + "\n".join(textwrap.indent(c, "    ") for c in chunks), ns)
app = ns["S"]()
app.current_display_month = "2026-08"
app.categories = {"المصنعين": ["أحمد"], "المركبين": ["سالم"],
                  "أقسام_خياس_إضافية": ["ورشة التركيب"]}   # قسم مضاف حديثاً


def inv(i, t, w, name="", status="ACTIVE", manual=""):
    return {"رقم الفاتورة": i, "النوع": t, "الوزن": w, "الاسم": name,
            "settled_status": status, "التاريخ": "2026-08-05 10:00:00",
            "رقم الفاتورة اليدوي": manual, "trees_count": 0.0, "period": "2026-08"}


# ---------- السيناريو ----------
# الخزينة ٥٠٠ (بعد خصم ما خرج للورش)
app.current_treasury_balance = 500.0

app.invoices = {
    # مصنّع: فاقد كلي ١٢ ومسموح صفر (لا مفنش) ← ذهب/صافي ١٢
    100: inv(100, "صرف ذهب", 1000.0, "أحمد"),
    101: inv(101, "قبض ذهب", 988.0, "أحمد"),
    # مركّب: فاقد كلي ٣ ومسموح على القبض
    102: inv(102, "صرف ذهب", 300.0, "سالم"),
    103: inv(103, "قبض ذهب", 297.0, "سالم"),
    1: inv(1, "صرف كاستنج", 100.0),
    2: inv(2, "قبض كاستنج", 96.0),          # خياس الكاستنج = ٤
    3: inv(3, "صرف تلميع", 50.0),
    4: inv(4, "قبض تلميع", 48.5),           # خياس التلميع = ١.٥
    5: inv(5, "صرف تلميع بف", 20.0),
    6: inv(6, "قبض تلميع بف", 20.0),        # صفر
    7: inv(7, "خياس طقوم", 2.5, name="عميل", manual="9001"),   # خياس التلميع النهائي = ٢.٥
    70: inv(70, "مبيعات ذهب", 40.0, name="عميل", manual="9001"),
    8: inv(8, "صرف ورشة التركيب", 30.0),
    9: inv(9, "قبض ورشة التركيب", 29.0),    # القسم المضاف = ١
}

boxes = {c: app.get_box_khayas_cumulative(c, month="") for c in app.get_all_stage_categories()}
assert boxes["الكاستنج"] == 4.0, boxes
assert boxes["التلميع"] == 1.5, boxes
assert boxes["التلميع/البف"] == 0.0, boxes
assert boxes["خياس الطقوم"] == 2.5, boxes
assert boxes["ورشة التركيب"] == 1.0, boxes
print("✔ خياس كل صندوق يُحسب صحيحاً:", {k: v for k, v in boxes.items() if v})

# المعتمد الآن: الخياس الفعلي للمصنعين والمركبين (لا الذهب عند القسم)
total = app.get_total_gold_balance()
mfg = app.get_current_unclosed_khayas("المصنعين")
mer = app.get_current_unclosed_khayas("المركبين")
expected = 500.0 + mfg + mer + 4.0 + 1.5 + 0.0 + 2.5 + 1.0
assert total == round(expected, 2), (total, expected)
print(f"✔ الرصيد الحالي = {total} جم (خزينة 500 + خياس المصنعين {mfg} + خياس المركبين {mer} + صناديق 9.0)")

# ---------- القسم المضاف حديثاً يدخل تلقائياً ----------
app.categories["أقسام_خياس_إضافية"].append("ورشة الحفر")
app.invoices[10] = inv(10, "صرف ورشة الحفر", 40.0)
app.invoices[11] = inv(11, "قبض ورشة الحفر", 37.0)
assert app.get_total_gold_balance() == round(total + 3.0, 2)
print("✔ أي صندوق يُضاف مستقبلاً يدخل في الحساب تلقائياً بلا تعديل كود")

# ---------- المسترجع يقلّل رصيد الصندوق ----------
app.invoices[12] = inv(12, "وارد ذهب (عيار 18)", 2.0, name="مسترجع كاستنج")
assert app.get_box_khayas_cumulative("الكاستنج", month="") == 2.0
print("✔ استرجاع ذهب من صندوق يقلّل رصيده (٤ ← ٢)")

# ---------- الإقفال يُخرج الخياس من الرصيد (يصبح خسارة فعلية) ----------
before = app.get_total_gold_balance()
app.invoices[13] = inv(13, "قيد يومي دائن", 2.0, name="الكاستنج")     # إقفال
app.invoices[14] = inv(14, "قيد يومي مدين", 2.0, name="حساب الخسائر")
after = app.get_total_gold_balance()
assert app.get_box_khayas_cumulative("الكاستنج", month="") == 0.0
assert after == round(before - 2.0, 2), (before, after)
print("✔ إقفال الصندوق يُخرج خياسه من الرصيد الحالي (أصبح فاقداً فعلياً)")

# ---------- الحركات الملغاة لا تُحتسب ----------
app.invoices[15] = inv(15, "صرف تلميع", 999.0, status="SETTLED")
assert app.get_box_khayas_cumulative("التلميع", month="") == 1.5
print("✔ الحركات غير النشطة لا تدخل في الحساب")

# ---------- التفصيل يطابق الإجمالي ----------
parts = app.get_gold_balance_breakdown()
assert round(sum(v for _, v in parts), 2) == app.get_total_gold_balance()
print(f"✔ تفصيل الرصيد ({len(parts)} بند) يطابق الإجمالي تماماً")

print("\nكل الاختبارات المحاسبية نجحت ✅")
