# -*- coding: utf-8 -*-
"""
اختبار خياس المركب: يجب أن يطابق عمود (مسموح/٨) في كشف مراحل التصنيع تماماً.
يحاكي الاختبار منطق الكشف نفسه ثم يقارن النتيجتين رقماً برقم.
"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
m = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == "get_assembler_khayas_for_set")
ns = {"ALLOWANCE_8": 0.008}
exec("class S:\n" + textwrap.indent(textwrap.dedent(ast.get_source_segment(src, m)), "    "), ns)
app = ns["S"]()
app.current_display_month = "2026-08"
app.categories = {"المركبين": ["سالم", "خالد"], "المصنعين": ["أحمد"]}


def inv(i, name, t, w, row_no, set_no="", month="2026-07"):
    return {"رقم الفاتورة": i, "الاسم": name, "النوع": t, "الوزن": w,
            "row_number": row_no, "set_number": set_no,
            "settled_status": "ACTIVE", "التاريخ": f"{month}-05 10:00:00"}


def ledger_allow8(invoices, worker, target_set):
    """محاكاة مستقلة لعمود مسموح/٨ في الكشف (تجميع بالصف، أول رقم تشغيل)"""
    groups = {}
    for x in invoices:
        if x["الاسم"] != worker or x["settled_status"] != "ACTIVE":
            continue
        g = groups.setdefault(x["row_number"], {"set": "", "قبض": 0.0})
        if not g["set"] and x["set_number"]:
            g["set"] = x["set_number"]
        if x["النوع"] == "قبض ذهب":
            g["قبض"] += x["الوزن"]
    return round(sum(g["قبض"] for g in groups.values() if g["set"] == target_set) * 0.008, 2)


# ═══ ١) الحالة الأساسية: رقم التشغيل على حركة الصرف فقط ═══
app.invoices = {
    1: inv(1, "سالم", "صرف ذهب", 400.0, "1", set_no="1"),
    2: inv(2, "سالم", "قبض ذهب", 375.0, "1"),
}
v = app.get_assembler_khayas_for_set("1")
assert v == 3.0, v
assert v == ledger_allow8(app.invoices.values(), "سالم", "1")
print(f"✔ رقم التشغيل على حركة واحدة من الصف → {v} (مطابق للكشف)")

# ═══ ٢) المصنعون لا يدخلون الحساب إطلاقاً ═══
app.invoices[3] = inv(3, "أحمد", "قبض ذهب", 9999.0, "1", set_no="1")
app.invoices[4] = inv(4, "أحمد", "المفنش ٨ بالالف", 500.0, "1", set_no="1")
assert app.get_assembler_khayas_for_set("1") == 3.0
print("✔ قسم المصنعين مستثنى تماماً (كان يُضاف فيعطي رقماً خاطئاً)")

# ═══ ٣) صف يحمل رقم تشغيل مختلف لا يُحتسب ═══
app.invoices[5] = inv(5, "سالم", "صرف ذهب", 200.0, "2", set_no="99")
app.invoices[6] = inv(6, "سالم", "قبض ذهب", 190.0, "2")
assert app.get_assembler_khayas_for_set("1") == 3.0
assert app.get_assembler_khayas_for_set("99") == round(190 * 0.008, 2) == 1.52
print("✔ كل صف يُحسب برقم تشغيله وحده — لا خلط بين الصفوف")

# ═══ ٤) عدة عمال وعدة فترات على نفس رقم التشغيل ═══
app.invoices[7] = inv(7, "خالد", "صرف ذهب", 100.0, "5", set_no="1", month="2026-05")
app.invoices[8] = inv(8, "خالد", "قبض ذهب", 95.0, "5", month="2026-05")
assert app.get_assembler_khayas_for_set("1") == round((375 + 95) * 0.008, 2) == 3.76
print("✔ عدة عمال وفترات على نفس الرقم → تُجمع (3.76)")

# ═══ ٥) صف بلا رقم تشغيل لا يُنسب لأي رقم ═══
app.invoices[9] = inv(9, "سالم", "قبض ذهب", 500.0, "7")
assert app.get_assembler_khayas_for_set("1") == 3.76
print("✔ صف بلا رقم تشغيل لا يُنسب لأي رقم")

# ═══ ٦) المطابقة مع الكشف على كل أرقام التشغيل ═══
for target in ("1", "99", "لا-يوجد"):
    mine = app.get_assembler_khayas_for_set(target)
    theirs = round(sum(ledger_allow8(app.invoices.values(), w, target)
                       for w in ("سالم", "خالد")), 2)
    assert mine == theirs, (target, mine, theirs)
print("✔ النتيجة تطابق محاكاة الكشف على كل أرقام التشغيل المختبَرة")

# ═══ ٧) حالات الحدود ═══
assert app.get_assembler_khayas_for_set("") == 0.0
assert app.get_assembler_khayas_for_set(None) == 0.0
assert app.get_assembler_khayas_for_set("  1  ") == 3.76   # مسافات زائدة
print("✔ الفراغات الزائدة تُقلَّم، والقيم الفارغة → 0.0")

app.invoices[10] = dict(inv(10, "سالم", "قبض ذهب", 800.0, "1"), settled_status="SETTLED")
assert app.get_assembler_khayas_for_set("1") == 3.76
print("✔ الحركات الملغاة مستثناة")

app.categories = {"المركبين": [], "المصنعين": ["أحمد"]}
assert app.get_assembler_khayas_for_set("1") == 0.0
print("✔ لا مركبين مسجّلين → 0.0 بلا خطأ")

print("\n✅ خياس المركب يطابق عمود مسموح/٨ في كشف المركبين تماماً")
