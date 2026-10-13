# -*- coding: utf-8 -*-
"""
1.74: «تتبع رقم التشغيل» في مراحل التصنيع، وخياس البوليش في المبيعات، وسند رقم التشغيل المحمّل، وعملية «صب وتحليل».

  • بعد البوليش  = صرف رقم التشغيل في قسم المركبين — من صفّه نفسه كما في كشف المركبين (لا غيره).
  • قبل البوليش  = يُكتب يدوياً لكل رقم (إعداد يُرفع مع النسخة، وخطوة تراجع).
  • خياس البوليش = قبل − بعد ← خانة «خياس البوليش» في المبيعات، والنافذة تحتها، وقالب رقم التشغيل.
  • القالب: ٠٫٠٤٪ = قبل البوليش؛ البوليش والتركيب (صرف/قبض المركبين)؛ الوزن بعد؛ السلسال؛ الإجمالي؛ بوليش 2.
  • الكاستنج: «المسترجع» صار «صب وتحليل» برقم صف، وسند صرف وحده وسند قبض وحده (كلٌّ في صفحته).
لا شيء من التتبع حركةٌ أو خياس: الخزينة والصناديق لا تتأثر.
"""
import ast, io, os, sqlite3, sys, tempfile, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node_of(name):
    return next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))


def member(name):
    node = node_of(name)
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(node, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, node))


def module_value(name):
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name)
    return eval(compile(ast.Expression(node.value), name, "eval"), {"MEMO_STATUS": "MEMO"})


MEMBERS = ("_SET_DIGITS", "ASSEMBLER_KHAYAS_STATUSES", "SALE_TYPES", "POLISH_BEFORE_PREFIX", "CAST_RETURN_NAME",
           "CAST_RETURN_OLD_NAMES", "migrate_analysis_name",
           "CAST_ANALYSIS", "BOX_DISPLAY_OVERRIDES", "UNDO_LIMIT", "INVOICE_COLUMNS",
           "normalize_set_number", "inv_period", "inv_in_period", "assembler_set_index", "polish_before_map",
           "set_polish_before", "set_tracking_values", "sale_polish_by_set", "set_track_sale_status",
           "set_number_sort_key", "set_track_rows", "set_voucher_sections", "polish_hint_values",
           "autofill_polish_khayas", "get_setting", "set_setting", "push_undo", "_close_undo_step",
           "apply_undo_step", "undo_step_label", "invoice_from_row", "is_recovery_op", "get_display_label",
           "analysis_voucher_fields", "set_track_row_values", "set_track_row_tags")
ns = {"sqlite3": sqlite3, "log_cloud_error": lambda *a: None, "SALE_READ_STATUSES": ("ACTIVE", "SETTLED_INOUT", "MEMO"),
      "IS_ADMIN_BUILD": False,
      "KHAYAS_MARK_POLISH": module_value("KHAYAS_MARK_POLISH")}
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)


class App(ns["Base"]):
    def __init__(self, path):
        self.db_path, self.invoices, self.invoice_counter = path, {}, 0
        self.categories = {"المركبين": ["سالم", "خالد"], "المصنعين": ["أحمد"]}
        self.current_display_month = "2026-09"
        self.locked, self.blocked = False, 0

    def mark_backup_dirty(self): self._inv_version = getattr(self, "_inv_version", 0) + 1
    def check_edit_permission(self, silent=False): return not self.locked
    def view_only_blocked(self, silent=False): self.blocked += 1; return True
    def update_undo_buttons(self): pass
    def after_idle(self, fn): pass
    def revive_deleted_accounts(self, names): pass

    def add(self, name, t, w, row="", set_no="", period="2026-09", day="10", status="ACTIVE", **extra):
        self.invoice_counter += 1
        self.invoices[self.invoice_counter] = dict({
            "رقم الفاتورة": self.invoice_counter, "التاريخ": f"{period}-{day} 10:{self.invoice_counter:02d}:00",
            "الاسم": name, "النوع": t, "الوزن": w, "البيان": "", "settled_status": status, "trees_count": 0.0,
            "قبل": 0.0, "بعد": 0.0, "set_number": set_no, "row_number": row, "period": period}, **extra)
        self.mark_backup_dirty()
        return self.invoice_counter


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "t.db")
with sqlite3.connect(path) as c:
    c.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT)")
    c.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT, "
              "weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT, trees_count REAL, "
              "set_number TEXT, row_number TEXT, manual_no TEXT, period TEXT, sale_kind TEXT)")
a = App(path)

# ═══ ١) بعد البوليش = صرف الرقم في المركبين، من صفّه نفسه ═══
# سالم الصف ١ (فترة ٩): رقمه 7001 (أول رقم غير فارغ)، صرفه 40 + 2، وقبضه 38.5 — حركة الصرف الثانية بلا رقم
a.add("سالم", "صرف ذهب", 40.0, row="1", set_no="7001", day="02")
a.add("سالم", "صرف ذهب", 2.0, row="1", day="03")
a.add("سالم", "قبض ذهب", 38.5, row="1", day="05")
# خالد الصف ١ (الرقم نفسه ١ لعامل آخر): رقمه ٧٠٠٢ بأرقام هندية
a.add("خالد", "صرف ذهب", 25.0, row="1", set_no="٧٠٠٢")
# المصنعون بالرقم نفسه 7001: لا يدخلون (المركبون وحدهم)
a.add("أحمد", "صرف ذهب", 99.0, row="4", set_no="7001")
# رقم في فترتين (صف في ٨ مقفل بالأرشفة، وصف في ٩): يُجمع من صفّيه وتُذكر صفوفه
a.add("سالم", "صرف ذهب", 10.0, row="3", set_no="7003", period="2026-08", status="SETTLED")
a.add("سالم", "صرف ذهب", 5.0, row="2", set_no="7003")
# سطر معلوماتي وحركة محذوفة لا يدخلان
a.add("سالم", "صرف ذهب", 7.0, row="9", set_no="7009", status="MEMO")
a.add("سالم", "صرف ذهب", 7.0, row="8", set_no="7008", status="DELETED")

idx = a.assembler_set_index()
assert set(idx) == {"7001", "7002", "7003"}, set(idx)
assert (idx["7001"]["sarf"], idx["7001"]["qabd"]) == (42.0, 38.5)
assert idx["7001"]["rows"] == [{"name": "سالم", "period": "2026-09", "row": "1", "sarf": 42.0, "qabd": 38.5}]
assert idx["7002"]["sarf"] == 25.0 and idx["7002"]["rows"][0]["name"] == "خالد"
assert idx["7003"]["sarf"] == 15.0 and [r["period"] for r in idx["7003"]["rows"]] == ["2026-08", "2026-09"]
assert set(a.assembler_set_index("2026-08")) == {"7003"}
print("✔ بعد البوليش = صرف الرقم في المركبين من صفّه نفسه (أول رقم في الصف، كل حركات صرفه): 7001 = 42")
print("✔ المصنعون بالرقم نفسه لا يدخلون، والأرقام الهندية كاللاتينية، والمقفل يبقى، والمعلوماتي والمحذوف لا")
print("✔ رقمٌ في صفّين (فترتين) يُجمع منهما وتُذكر صفوفه ليُرى ويُراجع")

# الفهرس محفوظ حتى تتغيّر الحركات
assert a.assembler_set_index() is idx
a.add("سالم", "قبض ذهب", 4.5, row="2")                      # قبض للصف ٢ (رقمه 7003) بلا رقم
idx = a.assembler_set_index()
assert idx["7003"]["qabd"] == 4.5
print("✔ الفهرس يُبنى مرة ويُعاد بناؤه عند أي حركة جديدة (قبض صف ٧٠٠٣ بلا رقم يُنسب لصفه)")

# ═══ ٢) قبل البوليش: يُحفظ ويُعدَّل ويُمسح، وكل تغيير خطوة تراجع ═══
assert a.set_tracking_values("7001")["polish_before"] is None
assert a.set_polish_before("7001", 42.75) is True
v = a.set_tracking_values("٧٠٠١")
assert (v["polish_before"], v["polish_after"], v["polish_khayas"]) == (42.75, 42.0, 0.75), v
assert (v["asm_before"], v["asm_after"], v["asm_khayas"]) == (42.0, 38.5, 3.5) and v["names"] == ["سالم"]
with sqlite3.connect(path) as c:
    assert c.execute("SELECT value FROM settings WHERE key = 'polish_before:7001'").fetchone()[0] == "42.75"
step = a._undo_stack[-1]
assert a.undo_step_label(step) == "قبل البوليش (7001)" and step["settings"] == {"polish_before:7001": None}
a._close_undo_step(step)
assert a.set_polish_before("7001", 43.0) is True
a._close_undo_step(a._undo_stack[-1])
assert a.set_tracking_values("7001")["polish_khayas"] == 1.0
a.apply_undo_step(a._undo_stack.pop())
assert a.set_tracking_values("7001")["polish_before"] == 42.75, "التراجع يعيد القيمة السابقة"
a.apply_undo_step(a._undo_stack.pop())
assert a.set_tracking_values("7001")["polish_before"] is None, "والتراجع الثاني يمسحها كما كانت"
a.set_polish_before("7001", 42.75)
a.set_polish_before("7002", 25.4)
assert a.set_polish_before("7002", None) and a.set_tracking_values("7002")["polish_before"] is None
a.set_polish_before("7002", 25.4)
print("✔ قبل البوليش يُحفظ في الإعدادات (يُرفع مع النسخة)، ويُعدَّل ويُمسح، وكل تغيير خطوة تراجع تعيد السابقة")
print("✔ خياس البوليش = قبل − بعد: 42.75 − 42.00 = 0.75؛ والتركيب: صرف 42.00 − قبض 38.50 = 3.50")

# القفل: تسجيل أول مرة مسموح، وتغيير قيمة مسجّلة يخضع لقفل التعديل؛ ووضع العرض يمنع كل شيء
a.locked = True
assert a.set_polish_before("7003", 15.3) is True
assert a.set_polish_before("7003", 16.0) is False and a.set_tracking_values("7003")["polish_before"] == 15.3
a.locked = False
a.view_only = True
assert a.set_polish_before("7001", 50.0) is False and a.blocked == 1
assert a.set_tracking_values("7001")["polish_before"] == 42.75
a.view_only = False
print("✔ قفل التعديل يمنع تغيير قيمة مسجّلة (لا تسجيلها أول مرة)، وحساب العميل في برنامج المدير لا يكتب شيئاً")

# لا قيمة ← None (خانة فارغة، لا صفر مضلّل)
v = a.set_tracking_values("9999")
assert all(v[k] is None for k in ("polish_before", "polish_after", "polish_khayas", "asm_before", "asm_after"))
v = a.set_tracking_values("7002")
assert v["asm_after"] is None and v["asm_khayas"] is None and v["polish_khayas"] == 0.4
print("✔ رقم بلا قيمة (أو بلا قبض بعد) ← خانة فارغة لا صفر")

# ═══ ٣) لوحة التتبع: أرقام الفترة أو كل الفترات، والبحث، وحال الرقم في المبيعات ═══
rows = a.set_track_rows()
assert [r["set_number"] for r in rows] == ["7001", "7002", "7003"]
assert [r["set_number"] for r in a.set_track_rows(query="٢")] == ["7002"]
a.current_display_month = "2026-08"
assert [r["set_number"] for r in a.set_track_rows()] == ["7003"]
assert [r["set_number"] for r in a.set_track_rows(scope_all=True)] == ["7001", "7002", "7003"]
a.current_display_month = "2026-09"
# بيع 7001 بخياس بوليش 0.75 (مطابق)، و7002 بخياس 0.30 (يخالف التتبع 0.40)
for set_no, polish in (("7001", 0.75), ("7002", 0.3)):
    a.add("المصنع", "مبيعات ذهب", 30.0, set_no=set_no)
    a.add("المصنع", "خياس طقوم", polish, set_no=set_no, status="MEMO", trees_count=ns["KHAYAS_MARK_POLISH"])
by = {r["set_number"]: r for r in a.set_track_rows()}
assert (by["7001"]["sale_text"], by["7001"]["sale_mismatch"]) == ("✔ 0.75", False)
assert (by["7002"]["sale_text"], by["7002"]["sale_mismatch"]) == ("⚠️ 0.30", True)
assert (by["7003"]["sale_text"], by["7003"]["sale_mismatch"]) == ("لم يُبع", False)
vals = a.set_track_row_values(by["7003"])
assert vals[:4] == ("7003", "15.00", "15.3", "0.30") and "⚠️ في أكثر من صف" in vals[4]
assert a.set_track_row_tags(by["7002"]) == ("warn_tag",) and a.set_track_row_tags(by["7001"]) == ()
print("✔ اللوحة: أرقام المركبين للفترة المعروضة أو لكل الفترات، والبحث بالرقم (والهندي)، ومرتبة رقمياً")
print("✔ «في المبيعات»: ✔ مطابق، ⚠️ مختلف عن التتبع (يُلوَّن)، «لم يُبع» — ورقم في أكثر من صف يُنبَّه عليه")

# ═══ ٤) المبيعات: خانة «خياس البوليش» من التتبع، والنافذة تحتها ═══
class Entry:
    def __init__(self, t=""): self.t = t
    def get(self): return self.t
    def delete(self, *a): self.t = ""
    def insert(self, i, s): self.t = s + self.t


a.sale_set_number, a.sale_khayas_polish = Entry("7001"), Entry("")
assert a.autofill_polish_khayas() == 0.75 and a.sale_khayas_polish.get() == "0.75"
a.sale_khayas_polish.t = "0.7"                          # تعديل يدوي على الرقم نفسه لا يُمسح
a.autofill_polish_khayas()
assert a.sale_khayas_polish.get() == "0.7"
a.sale_set_number.t = "9999"                            # رقم آخر بلا قيمة ← الخانة فارغة (لا يبقى رقم السابق)
a.autofill_polish_khayas()
assert a.sale_khayas_polish.get() == ""
a.set_polish_before("7002", 24.0)                       # قبل أقل من بعد ← لا يُكتب خياس سالب
a.sale_set_number.t = "7002"
a.autofill_polish_khayas()
assert a.sale_khayas_polish.get() == ""
a.set_polish_before("7002", 25.4)
print("✔ المبيعات: رقم التشغيل يملأ «خياس البوليش» من التتبع؛ التعديل اليدوي يبقى؛ رقمٌ آخر يمسح قيمة السابق؛ "
      "والسالب لا يُكتب")

assert a.polish_hint_values("") == (None, None, "اكتب رقم التشغيل أولاً")
assert a.polish_hint_values("7001", "0.75") == (42.75, 42.0, "")
assert "يختلف" in a.polish_hint_values("7001", "0.5")[2]
assert a.polish_hint_values("9999")[2].startswith("رقم التشغيل 9999 غير موجود")
a.add("سالم", "صرف ذهب", 12.0, row="5", set_no="7005")
assert a.polish_hint_values("7005") == (None, 12.0, "لا «قبل البوليش» لهذا الرقم — سجّله في «تتبع رقم التشغيل»")
print("✔ النافذة تحت «خياس البوليش»: قبل 42.75 وبعد 42.00، وتنبيه إن نقص «قبل» أو خالف المكتوبُ التتبعَ")

# ═══ ٥) سند رقم التشغيل محمّلاً ═══
sale = {"set_number": "7001", "gold": 35.25, "gems": 2.5, "stones": 3.0, "stones_discount": "0.90", "diamond": 0.4,
        "khayas": 0.6, "invoice_no": 12, "name": "المصنع", "date": "2026-09-10 10:00:00", "kind": ""}
sec = a.set_voucher_sections(sale)
assert sec["mfg"] == (None, 42.75, None), "خانة ٠٫٠٤٪ = قبل البوليش"
assert sec["polish"] == (42.75, 42.0, 0.75) and sec["assembly"] == (42.0, 38.5, 3.5)
assert (sec["gems"], sec["stones"], sec["diamond"], sec["stones_pct"]) == (2.5, 3.0, 0.4, 30.0)
assert sec["weight_after"] == 44.4, "الوزن بعد = المركب بعد 38.5 + الماس 0.4 + الأحجار 3 + الفصوص 2.5"
assert sec["total"] == 41.75, "الوزن الإجمالي = قبل بوليش 2 = 0.6 + 35.25 + 2.5 + 3 + 0.4"
assert sec["chain"] == -2.65, "السلسال = الإجمالي − الوزن بعد"
assert sec["polish2"] == (41.75, 41.15, 0.6), "بوليش 2 = نافذة «قبل/بعد» نفسها"
assert (sec["net"], sec["stones_discount"], sec["bound"]) == (35.25, 0.9, 39.05)
assert (sec["assemblers"], sec["kind"], sec["name"], sec["date"]) == ("سالم", "الماس", "المصنع", "2026-09-10")
blank = a.set_voucher_sections({"set_number": "7003", "invoice_no": None})
assert blank["polish"] == (15.3, 15.0, 0.3) and blank["assembly"] == (15.0, 4.5, 10.5)
assert all(blank[k] is None for k in ("gems", "stones", "diamond", "weight_after", "chain", "total", "net", "bound"))
assert blank["polish2"] == (None, None, None) and blank["kind"] == blank["name"] == ""
print("✔ سند رقم التشغيل: ٠٫٠٤٪ = قبل البوليش 42.75؛ البوليش 42.75/42.00/0.75؛ التركيب 42.00/38.50/3.50")
print("✔ الوزن بعد 44.40 = المركب بعد + الماس + الأحجار + الفصوص؛ الإجمالي 41.75 = قبل بوليش 2؛ "
      "السلسال = الفرق؛ بوليش 2 = 41.75/41.15/0.60؛ المقيد 39.05")
print("✔ رقمٌ لم يُبع بعد: البوليش والتركيب من التتبع، وخانات البيع فارغة (لا أصفار مضلّلة)")

# ═══ ٦) الكاستنج: «صب وتحليل» وسنداه ═══
assert a.CAST_RETURN_NAME == "صب وتحليل" and a.CAST_ANALYSIS == "صب وتحليل"
assert a.CAST_RETURN_OLD_NAMES == ("مسترجع الفاقد", "تحليل الكاستنج")
assert a.is_recovery_op({"الاسم": "صب وتحليل", "row_number": "3"}, "صرف كاستنج", "مسترجع كاستنج")
assert a.is_recovery_op({"الاسم": "صب وتحليل", "row_number": ""}, "صرف كاستنج", "مسترجع كاستنج")
# الاسم القديم «مسترجع الفاقد» يتحوّل (في الذاكرة والقاعدة)، والوزن والنوع والصف كما هي
old1 = a.add("مسترجع الفاقد", "صرف كاستنج", 6.0)
old2 = a.add("تحليل الكاستنج", "قبض كاستنج", 5.5, row="4")                    # اسم 1.74
other = a.add("مسترجع الفاقد", "وارد ذهب (عيار 18)", 1.0)          # ليس من الكاستنج: لا يُمسّ
with sqlite3.connect(path) as c:
    for i in (old1, old2, other):
        inv_ = a.invoices[i]
        c.execute("INSERT INTO invoices (invoice_id, date_time, name, op_type, weight, row_number) VALUES (?,?,?,?,?,?)",
                  (i, inv_["التاريخ"], inv_["الاسم"], inv_["النوع"], inv_["الوزن"], inv_["row_number"]))
assert a.migrate_analysis_name() == 2 and a.migrate_analysis_name() == 0
assert [(a.invoices[i]["الاسم"], a.invoices[i]["الوزن"], a.invoices[i]["row_number"]) for i in (old1, old2)] == \
    [("صب وتحليل", 6.0, ""), ("صب وتحليل", 5.5, "4")]
assert a.invoices[other]["الاسم"] == "مسترجع الفاقد"
with sqlite3.connect(path) as c:
    assert c.execute("SELECT name FROM invoices WHERE invoice_id = ?", (old2,)).fetchone()[0] == "صب وتحليل"
    assert c.execute("SELECT name FROM invoices WHERE invoice_id = ?", (other,)).fetchone()[0] == "مسترجع الفاقد"
print("✔ الحركات القديمة («مسترجع الفاقد» و«تحليل الكاستنج») تأخذ اسمها الجديد «صب وتحليل» — الاسم وحده، "
      "والأوزان كما هي")
assert not a.is_recovery_op({"الاسم": "كاستنج", "row_number": "3"}, "صرف كاستنج", "مسترجع كاستنج")
iss = {"رقم الفاتورة": 51, "النوع": "صرف كاستنج", "الوزن": 10.0, "التاريخ": "2026-09-20 09:00:00",
       "row_number": "3", "البيان": "عينة الفرن", "period": "2026-09"}
title, sub, info, weight, note = a.analysis_voucher_fields(iss)
assert (title, weight, note) == ("سند صرف", 10.0, "عينة الفرن") and sub.startswith("صب وتحليل — قسم")
assert info == [("رقم السند:", "51"), ("التاريخ:", "2026-09-20"), ("رقم الصف:", "3"), ("الفترة:", "2026-09")]
title, sub, _info, weight, _n = a.analysis_voucher_fields(dict(iss, **{"النوع": "قبض كاستنج", "الوزن": 9.8}))
assert (title, weight) == ("سند قبض", 9.8) and sub.startswith("صب وتحليل")
pv = member("print_analysis_voucher")
assert "self.draw_analysis_voucher(c, inv)" in pv and pv.count("c.showPage()") == 1, "سند واحد في صفحته وملفه"
assert "self.print_analysis_voucher(i)" in member("print_analysis_vouchers")
cast_ui = member("build_casting_ui")
assert '"🖨️ معاينة الصرف", lambda: self.preview_selected_analysis("صرف كاستنج")' in cast_ui
assert '"🖨️ معاينة القبض", lambda: self.preview_selected_analysis("قبض كاستنج")' in cast_ui
cast = member("submit_casting_recovery_op")
assert 'messagebox.showwarning("رقم الصف مطلوب"' in cast and '"row_number": row_num' in cast
assert 'askyesno("طباعة السند"' in cast and "self.print_analysis_vouchers(posted)" in cast
assert cast.index("self.recalculate_all()") < cast.index('askyesno("طباعة السند"')
collect = member("collect_stage_ops_rows")
assert 'and grouped[k]["op"] == "فاقد"' in collect, "مسترجع الأشجار يُلحق بصف الفاقد لا بصف تحليل برقمه"
print("✔ «صب وتحليل» برقم صف (إلزامي) — صرفه وقبضه صفٌّ واحد — والسند بعد الترحيل: «سند صرف» وحده و«سند قبض» وحده، "
      "كلٌّ في صفحته، وزرّا «معاينة الصرف» و«معاينة القبض»")

# ═══ ٧) الواجهة: اللوحة في شريط الأقسام، والكتابة في الجدول، والربط بالمبيعات وبالقالب ═══
assert 'stage_defs.append((self.SET_TRACK_KEY, f"🔎 {self.SET_TRACK_KEY}"))' in member("refresh_stage_buttons")
assert "elif stage == self.SET_TRACK_KEY:" in member("switch_op_stage")
assert "self.refresh_set_track_table()" in member("refresh_current_stage")
ui = member("build_set_track_ui")
for key in ('("<Return>", 1)', '("<KP_Enter>", 1)', '("<Down>", 1)', '("<Up>", -1)'):
    assert key in ui, key
assert 'if not getattr(self, "view_only", False):' in ui and "self.set_polish_before(key, value)" in ui
assert '"<FocusOut>", lambda e: commit(interactive=False)' in ui and "tree.configure(yscrollcommand=on_scroll)" in ui
assert "self.attach_polish_hint(self.sale_khayas_polish, tab, self.sale_set_number)" in member("build_sales_tab")
editor = member("open_sale_invoice_editor")
assert 'self.attach_polish_hint(entries["خياس البوليش"], win, entries["set_number"])' in editor
assert "خياس البوليش المسجّل" in editor and 'self.set_tracking_values(set_no)["polish_khayas"]' in editor
assert "self.autofill_polish_khayas(key)" in member("autofill_assembler_khayas")
assert "self.set_tracking_values(" in member("set_voucher_sections")
print("✔ لوحة «🔎 تتبع رقم التشغيل» في شريط الأقسام؛ «قبل البوليش» يُكتب في خانته (Enter/↓ للتالي و↑ للسابق)، "
      "ولا كتابة في حساب العميل لدى المدير")
print("✔ المبيعات ونافذة تعديل الفاتورة تجلبان خياس البوليش وتنبّهان إن خالف المسجّلُ التتبعَ؛ والقالب منه")
print("\n✅ تتبع رقم التشغيل وخياس البوليش والقالب والتحليل — كل رقم بقيمه الصحيحة")
