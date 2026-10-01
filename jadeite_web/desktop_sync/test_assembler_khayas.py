# -*- coding: utf-8 -*-
"""
اختبار خياس المركب في المبيعات: يجب أن يساوي عمود (مسموح/٨) في كشف المركبين
بمراحل التصنيع لصفوف رقم التشغيل — تماماً، في كل الفترات.

الدوال من البرنامج نفسه (لا نسخة منها)، وتُقارن بمحاكاة مستقلة للكشف: الكشف يعرض
فترة واحدة لعامل واحد، يجمّع حركاته بالصف، رقم تشغيل الصف أول رقم غير فارغ بترتيب
التاريخ، ومسموح/٨ = قبض الصف × ٨ بالألف مقرّباً.
"""
import ast, io, random, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

NEEDED = ("_SET_DIGITS", "ASSEMBLER_KHAYAS_STATUSES", "normalize_set_number", "get_assembler_khayas_for_set",
          "get_assembler_khayas_details", "assembler_khayas_index", "describe_assembler_khayas",
          "audit_sale_assembler_khayas", "autofill_assembler_khayas", "inv_period", "inv_in_period",
          "SALE_TYPES", "sale_records_to_rows")


def member_name(x):
    if isinstance(x, ast.FunctionDef):
        return x.name
    if isinstance(x, ast.Assign) and isinstance(x.targets[0], ast.Name):
        return x.targets[0].id
    return None


chunks = []
for x in cls.body:
    if member_name(x) in NEEDED:
        deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(x, "decorator_list", []))
        chunks.append(textwrap.dedent(deco + ast.get_source_segment(src, x)))
assert len(chunks) == len(NEEDED), [n for n in NEEDED if n not in {member_name(x) for x in cls.body}]

consts = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        n = node.targets[0].id
        if n.startswith("KHAYAS_MARK_") or n in ("ALLOWANCE_8", "MEMO_STATUS"):
            consts[n] = eval(compile(ast.Expression(node.value), "c", "eval"), {})
consts["SALE_READ_STATUSES"] = ("ACTIVE", "SETTLED_INOUT", consts["MEMO_STATUS"])
errors = []
consts["log_cloud_error"] = lambda msg, e: errors.append((msg, e))
exec("class S:\n" + "\n".join(textwrap.indent(c, "    ") for c in chunks), consts)
app = consts["S"]()
app.categories = {"المركبين": ["سالم", "خالد"], "المصنعين": ["أحمد"]}


def inv(i, name, t, w, row_no, set_no="", month="2026-07", day=5, status="ACTIVE"):
    return {"رقم الفاتورة": i, "الاسم": name, "النوع": t, "الوزن": w,
            "row_number": row_no, "set_number": set_no,
            "settled_status": status, "التاريخ": f"{month}-{day:02d} 10:00:00"}


def ledger_column(invoices, worker, month):
    """محاكاة مستقلة لكشف المركبين (refresh_op_ledger_table) لعامل وفترة:
    [(رقم التشغيل كما يظهر، مسموح/٨ كما يظهر)] لكل صف."""
    mine = sorted((x for x in invoices if x["الاسم"] == worker and x["settled_status"] == "ACTIVE"
                   and x["التاريخ"][:7] == month), key=lambda x: x["التاريخ"])
    rows = {}
    for x in mine:
        g = rows.setdefault(x["row_number"] or "", {"set": "", "قبض": 0.0})
        if not g["set"] and x["set_number"]:
            g["set"] = x["set_number"]
        if x["النوع"] == "قبض ذهب":
            g["قبض"] = round(g["قبض"] + x["الوزن"], 2)
    return [(g["set"], round(g["قبض"] * 0.008, 2)) for g in rows.values()]


def ledger_value(invoices, target, workers=("سالم", "خالد")):
    """ما يجده المستخدم بالبحث يدوياً: كل كشوف المركبين في كل الفترات، صفوف الرقم المطلوب"""
    months = {x["التاريخ"][:7] for x in invoices}
    norm = consts["S"].normalize_set_number
    return round(sum(v for w in workers for m in months for s, v in ledger_column(invoices, w, m)
                     if norm(s) == norm(target)), 2)


# ═══ ١) الحالة الأساسية: رقم التشغيل على حركة الصرف فقط ═══
app.invoices = {1: inv(1, "سالم", "صرف ذهب", 400.0, "1", set_no="1"),
                2: inv(2, "سالم", "قبض ذهب", 375.0, "1")}
assert app.get_assembler_khayas_for_set("1") == 3.0 == ledger_value(app.invoices.values(), "1")
print("✔ رقم التشغيل على حركة واحدة من الصف → 3.00 (مطابق للكشف)")

# ═══ ٢) المصنعون لا يدخلون الحساب إطلاقاً ═══
app.invoices[3] = inv(3, "أحمد", "قبض ذهب", 9999.0, "1", set_no="1")
app.invoices[4] = inv(4, "أحمد", "المفنش ٨ بالالف", 500.0, "1", set_no="1")
assert app.get_assembler_khayas_for_set("1") == 3.0
print("✔ قسم المصنعين مستثنى تماماً")

# ═══ ٣) سبب الخطأ المُبلَّغ: رقم الصف نفسه في فترتين (الترقيم يبدأ من ١ كل شهر) ═══
app.invoices = {1: inv(1, "سالم", "صرف ذهب", 400.0, "1", "7003", "2026-08"),
                2: inv(2, "سالم", "قبض ذهب", 375.0, "1", "", "2026-08"),
                3: inv(3, "سالم", "صرف ذهب", 300.0, "1", "8001", "2026-09"),
                4: inv(4, "سالم", "قبض ذهب", 290.0, "1", "", "2026-09")}
assert app.get_assembler_khayas_for_set("7003") == 3.0 == ledger_value(app.invoices.values(), "7003")
assert app.get_assembler_khayas_for_set("8001") == 2.32 == ledger_value(app.invoices.values(), "8001")
print("✔ الصف ١ في أغسطس (7003) والصف ١ في سبتمبر (8001) صفّان منفصلان: 3.00 و2.32"
      " (كانا يُدمجان: 5.32 للأول وصفر للثاني)")

# ═══ ٤) أرقام هندية ومسافات: «٧٠٠٥» = «7005» ═══
app.invoices = {1: inv(1, "سالم", "صرف ذهب", 400.0, "3", "٧٠٠٥", "2026-08"),
                2: inv(2, "سالم", "قبض ذهب", 375.0, "3", "", "2026-08")}
for typed in ("7005", "٧٠٠٥", " 7005 ", "۷۰۰۵"):
    assert app.get_assembler_khayas_for_set(typed) == 3.0, typed
print("✔ رقم التشغيل بأرقام هندية أو فارسية أو بمسافات يطابق نفسه بالأرقام اللاتينية")

# ═══ ٥) الإقفال القديم (SETTLED) لا يلغي القبض، والسطور المعلوماتية مستثناة ═══
app.invoices = {1: inv(1, "سالم", "صرف ذهب", 400.0, "4", "7006", "2026-06", status="SETTLED"),
                2: inv(2, "سالم", "قبض ذهب", 375.0, "4", "", "2026-06", status="SETTLED"),
                3: inv(3, "سالم", "قبض ذهب", 900.0, "4", "", "2026-06", status="MEMO")}
assert app.get_assembler_khayas_for_set("7006") == 3.0
print("✔ صفوف قسمٍ أُقفل بالأرشفة القديمة تُحتسب (كانت تُرجع صفراً)، وسطور MEMO مستثناة")

# ═══ ٦) عدة عمال وفترات على الرقم نفسه: مجموع قيم العمود كما تظهر ═══
app.invoices = {1: inv(1, "سالم", "صرف ذهب", 100.0, "1", "T-1", "2026-08"),
                2: inv(2, "سالم", "قبض ذهب", 97.0, "1", "", "2026-08"),
                3: inv(3, "خالد", "صرف ذهب", 50.0, "5", "T-1", "2026-07"),
                4: inv(4, "خالد", "قبض ذهب", 48.5, "5", "", "2026-07")}
v, matches = app.get_assembler_khayas_details("T-1")
assert v == 1.17 == ledger_value(app.invoices.values(), "T-1"), v       # 0.78 + 0.39
assert {(m["name"], m["period"], m["row"], m["allow8"]) for m in matches} == {
    ("سالم", "2026-08", "1", 0.78), ("خالد", "2026-07", "5", 0.39)}
print("✔ عدة عمال وفترات: مجموع قيم عمود مسموح/٨ كما تظهر (0.78 + 0.39 = 1.17) مع مصدر كل قيمة")

# ═══ ٧) أول رقم تشغيل بترتيب التاريخ لا بترتيب الإدخال ═══
app.invoices = {9: inv(9, "سالم", "صرف ذهب", 100.0, "2", "A", "2026-08", day=3),
                5: inv(5, "سالم", "قبض ذهب", 50.0, "2", "B", "2026-08", day=9)}
assert app.get_assembler_khayas_for_set("A") == 0.4 and app.get_assembler_khayas_for_set("B") == 0.0
print("✔ رقم تشغيل الصف = أول رقم بالتاريخ (كما يعرضه الكشف)")

# ═══ ٨) مقارنة عشوائية واسعة مع محاكاة الكشف ═══
rnd = random.Random(1312)
for trial in range(300):
    invs, n = {}, 0
    for _ in range(rnd.randint(5, 40)):
        n += 1
        invs[n] = inv(n, rnd.choice(["سالم", "خالد", "أحمد"]), rnd.choice(["صرف ذهب", "قبض ذهب", "قبض ذهب", "الليز"]),
                      round(rnd.uniform(1, 400), 2), str(rnd.randint(1, 4)),
                      rnd.choice(["", "", "100", "200", "300", "١٠٠"]),
                      rnd.choice(["2026-06", "2026-07", "2026-08"]), day=rnd.randint(1, 28))
    app.invoices = invs
    for target in ("100", "200", "300", "999"):
        mine, theirs = app.get_assembler_khayas_for_set(target), ledger_value(invs.values(), target)
        assert mine == theirs, (trial, target, mine, theirs)
print("✔ ٣٠٠ حالة عشوائية (صفوف تتكرّر بين الفترات، أرقام هندية، مصنعون): البحث = الكشف في كل رقم")

# ═══ ٩) سطر المصدر ═══
app.invoices = {1: inv(1, "سالم", "صرف ذهب", 400.0, "1", "7003", "2026-08"),
                2: inv(2, "سالم", "قبض ذهب", 375.0, "1", "", "2026-08")}
txt = app.describe_assembler_khayas("7003")
for part in ("7003", "3.00", "سالم", "الصف 1", "2026-08", "375.00"):
    assert part in txt, (part, txt)
assert "غير موجود" in app.describe_assembler_khayas("9999")
assert app.describe_assembler_khayas("") == ""
print(f"✔ سطر المصدر: «{txt}»")

# ═══ ١٠) تدقيق الفواتير المرحّلة ═══
M = consts


def sale(i, set_no, khayas_asm, manual="S-1", date="2026-09-01 10:00:00"):
    base = {"الاسم": "زبون", "رقم الفاتورة اليدوي": manual, "التاريخ": date, "settled_status": "ACTIVE",
            "set_number": set_no, "row_number": "1", "قبل": 0.0}
    return [dict(base, **{"رقم الفاتورة": i, "النوع": "مبيعات ذهب", "الوزن": 10.0, "trees_count": 0.0}),
            dict(base, **{"رقم الفاتورة": i + 1, "النوع": "خياس طقوم", "الوزن": khayas_asm,
                          "trees_count": M["KHAYAS_MARK_ASSEMBLER"], "settled_status": "MEMO"})]


for x in sale(100, "7003", 5.32, manual="S-1") + sale(200, "7003", 3.0, manual="S-2") + sale(300, "", 0.0, manual="S-3"):
    app.invoices[x["رقم الفاتورة"]] = x
found, checked = app.audit_sale_assembler_khayas()
assert checked == 2, checked
assert len(found) == 1 and found[0]["key"][0] == "S-1", found
assert found[0]["stored"] == 5.32 and found[0]["correct"] == 3.0 and found[0]["matches"][0]["name"] == "سالم"
print("✔ التدقيق: فاتورة S-1 (5.32 مسجّلة، الصحيح 3.00) تظهر، وS-2 المطابقة لا تظهر، والسطر بلا رقم لا يُفحص")


# ═══ ١١) الجلب التلقائي في شاشة المبيعات ═══
class Entry:
    def __init__(self, text=""):
        self.text = text

    def get(self):
        return self.text

    def delete(self, a, b=None):
        self.text = ""

    def insert(self, i, s):
        self.text = s + self.text


app.invoices = {1: inv(1, "سالم", "صرف ذهب", 400.0, "1", "7003", "2026-08"),
                2: inv(2, "سالم", "قبض ذهب", 375.0, "1", "", "2026-08")}
shown = []
app.show_assembler_source = shown.append
app.sale_set_number, app.sale_khayas_assembler = Entry("7003"), Entry("")
app.autofill_assembler_khayas()
assert app.sale_khayas_assembler.get() == "3" and "سالم" in shown[-1], shown
app.sale_khayas_assembler.text = "2.9"                 # تعديل يدوي
app.autofill_assembler_khayas()                        # المرور على الخانة بالأسهم/Enter
assert app.sale_khayas_assembler.get() == "2.9"
print("✔ الجلب يملأ الخانة ويُظهر المصدر، والمرور على الخانة لا يمسح تعديلاً يدوياً")
app.sale_set_number.text = "9999"
app.autofill_assembler_khayas()
assert app.sale_khayas_assembler.get() == "" and "غير موجود" in shown[-1]
app.sale_set_number.text = "7003"
app.autofill_assembler_khayas()
assert app.sale_khayas_assembler.get() == "3"
print("✔ تغيير الرقم يعيد الجلب: رقم غير موجود → فارغة مع سبب ظاهر، والعودة للرقم → 3")
assert not errors, errors

# ═══ ١٢) الواجهة: سطر المصدر، ونافذة تعديل الفاتورة، وزر التدقيق ═══
def body(name):
    return ast.get_source_segment(src, next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name))


ed = body("open_sale_invoice_editor")
assert 'entries["set_number"].bind("<FocusOut>", fetch_assembler' in ed and "check_loaded_assembler(r)" in ed
sales = body("build_sales_tab")
assert "lbl_assembler_source" in sales
assert 'bind("<KeyRelease>", self.schedule_assembler_autofill' in sales      # بعد توقّف الكتابة
assert 'bind("<FocusOut>", self.autofill_assembler_khayas' in sales         # وفوراً عند المغادرة
assert "open_assembler_khayas_audit" in body("build_sales_ops_ui")
assert "show_assembler_source(\"\")" in body("stage_sale_row")
print("✔ نافذة تعديل الفاتورة تجلب عند تغيير الرقم وتنبّه عند تحميل سطر مخالف، وزر التدقيق في «العمليات»")

app.categories = {"المركبين": [], "المصنعين": ["أحمد"]}
assert app.get_assembler_khayas_for_set("7003") == 0.0
assert app.get_assembler_khayas_for_set(None) == 0.0
print("✔ لا مركبين مسجّلين أو رقم فارغ → 0.0 بلا خطأ")

print("\n✅ خياس المركب يطابق عمود مسموح/٨ في كشف المركبين تماماً، في كل الفترات")
