# -*- coding: utf-8 -*-
"""اختبار: الذهب عند المصنعين/المركبين = ذهب/صافي، وصفر بعد الإقفال"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

WANT = ["invoices_by_name", "invoices_by_period", "period_invoices", "calculate_single_ledger", "get_section_excess_loss", "get_gold_at_section",
        "get_current_unclosed_khayas", "get_actual_section_khayas", "get_section_khayas_split", "get_box_closed_total",
        "get_box_khayas_cumulative", "get_sales_ops_khayas_total", "get_sale_invoice_groups", "get_stage_config", "get_box_account_name",
        "get_all_stage_categories", "get_display_label"]
chunks = []
for m in cls.body:
    if isinstance(m, ast.FunctionDef) and m.name in WANT:
        code = textwrap.dedent(ast.get_source_segment(src, m))
        for d in m.decorator_list:
            code = "@" + ast.get_source_segment(src, d) + "\n" + code
        chunks.append(code)
assert len(chunks) == len(WANT), len(chunks)

ns = {"ALLOWANCE_8": 0.008, "ALLOWANCE_4": 0.004,
      "SALE_READ_STATUSES": ("ACTIVE", "SETTLED_INOUT", "MEMO"),
      "KHAYAS_MARK_NET": 9.0, "KHAYAS_MARK_POLISH": 7.0,
      "KHAYAS_MARK_ASSEMBLER": 5.0, "KHAYAS_MARK_FINAL": 0.0,
      "log_cloud_error": lambda *a, **k: None}
exec("class S:\n    BOX_DISPLAY_OVERRIDES = {}\n    SALE_TYPES = (\"مبيعات ذهب\", \"مبيعات ذهب مع الماس\", \"مبيعات فصوص وأحجار\", \"مبيعات الماس\")\n    @staticmethod\n    def inv_period(inv):\n        p = (inv.get(\"period\") or \"\").strip()\n        return p if p else str(inv.get(\"التاريخ\", \"\"))[:7]\n    @classmethod\n    def inv_in_period(cls, inv, month):\n        return True if not month else cls.inv_period(inv) == month\n" + "\n".join(textwrap.indent(c, "    ") for c in chunks), ns)
app = ns["S"]()
app.current_display_month = "2026-08"
app.categories = {"المصنعين": ["أحمد"], "المركبين": ["سالم"], "أقسام_خياس_إضافية": []}


def inv(i, name, t, w, status="ACTIVE"):
    return {"رقم الفاتورة": i, "الاسم": name, "النوع": t, "الوزن": w,
            "settled_status": status, "التاريخ": "2026-08-05 10:00:00", "قبل": 0, "بعد": 0}


# مصنّع: صرف ١٠٠٠، قبض ٩٠٠، مفنش٨ = ٥٠، مفنش٤ = ٣٠
app.invoices = {
    1: inv(1, "أحمد", "صرف ذهب", 1000.0),
    2: inv(2, "أحمد", "قبض ذهب", 900.0),
    3: inv(3, "أحمد", "المفنش ٨ بالالف", 50.0),
    4: inv(4, "أحمد", "المفنش ٤ بالالف", 30.0),
    5: inv(5, "سالم", "صرف ذهب", 500.0),
    6: inv(6, "سالم", "قبض ذهب", 480.0),
}

led = app.calculate_single_ledger("أحمد", "المصنعين")
assert led["ذهب/باقي"] == round(1000 - 900 - 50 - 30, 2) == 20.0
assert led["مسموح 8"] == round(50 * 0.008, 2) == 0.4
assert led["مسموح 4"] == round(30 * 0.004, 2) == 0.12
assert led["ذهب/صافي"] == round(20 - 0.4 - 0.12, 2) == 19.48
print(f"✔ حساب ذهب/صافي للمصنّع سليم: {led['ذهب/صافي']} جم")

assert app.get_section_excess_loss("المصنعين") == 19.48
assert app.get_gold_at_section("المصنعين") == 19.48
print("✔ الذهب عند المصنعين = إجمالي ذهب/صافي (قبل الإقفال)")

led_m = app.calculate_single_ledger("سالم", "المركبين")
assert led_m["ذهب/باقي"] == 20.0
assert led_m["مسموح 8"] == round(480 * 0.008, 2) == 3.84
assert led_m["ذهب/صافي"] == round(20 - 3.84, 2) == 16.16
assert app.get_gold_at_section("المركبين") == 16.16
print(f"✔ الذهب عند المركبين = {app.get_gold_at_section('المركبين')} جم")

# ---------- بعد الإقفال ----------
live = app.get_actual_section_khayas("المصنعين")
app.invoices[10] = inv(10, "صندوق خياس المصنعين", "قيد يومي دائن", live)
app.invoices[11] = inv(11, "حساب الخسائر", "قيد يومي مدين", live)
assert app.get_current_unclosed_khayas("المصنعين") <= 0.005
assert app.get_gold_at_section("المصنعين") == 0.0
print("✔ بعد إقفال خياس المصنعين: الذهب عندهم = 0.00 (رُحّل للخسائر)")

assert app.get_gold_at_section("المركبين") == 16.16
print("✔ إقفال المصنعين لم يؤثر على المركبين")

# ---------- الشريط البارز والجدول لم يتغيّرا ----------
assert app.calculate_single_ledger("أحمد", "المصنعين")["ذهب/صافي"] == 19.48
print("✔ الجدول والشريط البارز يبقيان يعرضان الأرقام التفصيلية كما هي")

print("\nكل الاختبارات نجحت ✅")
