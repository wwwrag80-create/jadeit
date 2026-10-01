# -*- coding: utf-8 -*-
"""
فحص سلامة الحسابات (الدفعة ١٥) — محرّك الفحص من البرنامج نفسه على عالم مصغّر مضبوط:

  • عالم متّسق ← لا مخالفة، والفترة المعروضة تعود كما كانت.
  • كل خلل يُزرع يُكشف في مجموعته وبقيمه: سلسلة أرصدة الخزينة، التقرير ≠ الدفتر، صندوق ≠ كشفه،
    جدول مرحلة ≠ صندوقها، المبيعات، المواد، قيد بطرف واحد أو بطرفين مختلفين، تاريخ/فترة/وزن
    غير صالح، والذاكرة ≠ القاعدة.
  • رصيد الكشف بطبيعة الحساب (مدين/دائن) ويتجاهل سطر «رصيد أول المدة» عند طلب حركات الفترة.
"""
import ast, copy, datetime, io, os, re, sqlite3, sys, tempfile, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def member_src(name):
    x = node(name)
    return textwrap.dedent(ast.get_source_segment(src, x))


def body(name):
    return ast.get_source_segment(src, node(name))


ns = {"re": re, "os": os, "sqlite3": sqlite3, "datetime": datetime}
exec("class Base:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in
                                 ("_DATE_RE", "_PERIOD_RE", "JOURNAL_TYPES", "statement_balance",
                                  "run_integrity_checks", "integrity_report_text")), ns)

P = ["2026-08", "2026-09"]


def leg(i, name, t, w, ref, period="2026-09", dt="2026-09-03 10:00:00"):
    return {"رقم الفاتورة": i, "التاريخ": dt, "الاسم": name, "النوع": t, "الوزن": w,
            "settled_status": "ACTIVE", "set_number": ref, "period": period}


class World(ns["Base"]):
    LOSS_PARENT_ACCOUNT = "حساب الخسائر"
    TREE_RETURN_NAME = "مسترجع الأشجار"

    def __init__(self):
        self.current_display_month = "2026-09"
        self.db_path = None
        self.invoices = {
            1: leg(1, "حساب الخزينة", "قيد يومي مدين", 5.0, "JE-1"),
            2: leg(2, "رصيد افتتاحي", "قيد يومي دائن", 5.0, "JE-1"),
            3: leg(3, "عامل", "صرف ذهب", 2.0, "", period="2026-08", dt="2026-08-03 10:00:00"),
        }
        self.ledger = [{"period": "2026-08", "carry": 0.0, "closing": 100.0},
                       {"period": "2026-09", "carry": 100.0, "closing": 120.0}]
        self.report = [{"period": "2026-08", "end": 100.0}, {"period": "2026-09", "end": 120.0}]
        self.treasury_to = {"2026-08": 100.0, "2026-09": 120.0}
        self.box_current = {"2026-08": 3.0, "2026-09": 4.0}
        self.box_statement = {"2026-08": -3.0, "2026-09": -4.0}
        self.stage_table = {"2026-08": 5.0, "2026-09": 4.0}     # = الحالي + المُقفل
        self.closed = {"2026-08": 2.0, "2026-09": 0.0}
        self.sales_ops = {"2026-08": 7.0, "2026-09": 9.0}
        self.sales_statement = {"2026-08": 7.0, "2026-09": 9.0}
        self.material = {"فصوص وأحجار": 1.5, "الماس": 0.5}
        self.material_statement = {"حساب فصوص وأحجار": 1.5, "حساب الألماس": 0.5}
        self.months_seen = []

    def inv_period(self, inv):
        return inv.get("period") or str(inv.get("التاريخ", ""))[:7]

    def get_treasury_ledger(self): return copy.deepcopy(self.ledger)
    def get_monthly_report_rows(self): return copy.deepcopy(self.report)
    def get_khayas_box_categories(self): return ["المصنعين"]
    def get_all_stage_categories(self): return ["الكاستنج", "خياس الطقوم"]
    def get_display_label(self, cat): return cat
    def get_box_account_name(self, cat): return f"صندوق {cat}"
    def get_box_loss_account(self, cat): return f"فاقد {cat}"
    def get_box_loss_total(self, cat, month=None): return 6.0
    def get_box_recovery_name(self, cat): return None
    def get_current_unclosed_khayas(self, cat, month=None): return self.box_current[month]
    def get_stage_config(self, cat): return ("صرف كاستنج", "قبض كاستنج", "مسترجع")
    def stage_row_extra(self, qabd, recover): return (self.TREE_RETURN_NAME, "x", -1) if recover else None

    def collect_stage_ops_rows(self, madin, qabd, recover):
        m = self.current_display_month
        self.months_seen.append(m)
        return [("1", "x", {"مدين": self.stage_table[m] + 1.0, "دائن": 0.5, "مسترجع": 0.5})]

    def get_box_khayas_cumulative(self, cat, month=None): return self.stage_table[month] - self.closed[month]
    def get_box_closed_total(self, cat, month=None): return self.closed[month]

    def get_sale_invoice_groups(self, month):
        return [{"ذهب": self.sales_ops[month], "فصوص": 0.0, "أحجار بعد الخصم": 0.0, "الماس": 0.0}]

    def get_material_balance(self, mat): return self.material[mat]
    def get_journal_entry_account_options(self): return ["حساب الخزينة", "رصيد افتتاحي"]

    def statement_balance(self, account, from_m="", to_m="", period_rows_only=False):
        if account == "حساب الخزينة":
            return self.treasury_to[to_m]
        if account.startswith("صندوق"):
            return self.box_statement[from_m]
        if account in ("فاقد المصنعين", "حساب الخسائر"):
            return 6.0
        if account == "المبيعات":
            return self.sales_statement[from_m]
        return self.material_statement[account]


def fails(w):
    res, notes = w.run_integrity_checks()
    return {g: v[1] for g, v in res.items() if v[1]}, res, notes


w = World()
bad, res, notes = fails(w)
assert not bad, bad
assert set(res) == {"الخزينة", "صناديق الخياس ↔ كشوفها", "حسابات الفاقد والمسترجع", "جداول المراحل ↔ صناديقها",
                    "المبيعات", "المواد", "القيود اليومية", "سلامة الحركات"}, set(res)
assert w.current_display_month == "2026-09" and w.months_seen == P
assert res["سلامة الحركات"][0] == 3 and res["القيود اليومية"][0] == 1
print("✔ عالم متّسق: لا مخالفة في ٨ مجموعات، وكل فترة تُفحص ثم تعود الفترة المعروضة")


def expect(mutate, group, needle):
    w = World()
    mutate(w)
    bad, _res, _n = fails(w)
    assert group in bad and any(needle in d for d in bad[group]), (group, needle, bad)
    assert w.current_display_month == "2026-09"
    return bad[group]


expect(lambda w: w.ledger[1].update(carry=90.0), "الخزينة", "رصيد أول الفترة 90.00")
expect(lambda w: w.report[0].update(end=99.0), "الخزينة", "التقرير الشهري 99.00")
expect(lambda w: w.treasury_to.update({"2026-09": 121.0}), "الخزينة", "كشف «حساب الخزينة» 121.00")
print("✔ الخزينة: سلسلة الأرصدة والتقرير الشهري وكشف الخزينة كلٌّ يُكشف بقيمه")

expect(lambda w: w.box_statement.update({"2026-08": -2.0}), "صناديق الخياس ↔ كشوفها", "2026-08")
expect(lambda w: setattr(w, "get_box_khayas_cumulative",
                         lambda cat, month=None: World.get_box_khayas_cumulative(w, cat, month) + 0.5),
       "جداول المراحل ↔ صناديقها", "إجمالي الجدول")
expect(lambda w: setattr(w, "get_box_loss_total", lambda cat, month=None: 6.5), "حسابات الفاقد والمسترجع",
       "شاشة الخسائر 6.50")
print("✔ الصناديق: الفاقد الحالي ↔ كشف الصندوق، وجدول المرحلة ↔ صندوقها، وحساب الفاقد ↔ كشفه")

expect(lambda w: w.sales_statement.update({"2026-09": 8.0}), "المبيعات", "2026-09")
expect(lambda w: w.material_statement.update({"حساب الألماس": 0.4}), "المواد", "الماس")
print("✔ المبيعات والمواد تُطابَق بكشوفها")

expect(lambda w: w.invoices.pop(2), "القيود اليومية", "JE-1: 1 طرف مدين و0 طرف دائن")
expect(lambda w: w.invoices[2].update({"الوزن": 4.0}), "القيود اليومية", "JE-1: المدين 5.00")
expect(lambda w: w.invoices[2].update({"period": "2026-08"}), "القيود اليومية", "(2026-08)")
print("✔ القيود: طرف ناقص، وطرفان بوزنين مختلفين، وطرفان في فترتين — كلها تُكشف")

expect(lambda w: w.invoices[3].update({"التاريخ": "03/08/2026"}), "سلامة الحركات", "تاريخ غير صالح")
expect(lambda w: w.invoices[3].update({"period": "2026-13"}), "سلامة الحركات", "فترة غير صالحة")
expect(lambda w: w.invoices[3].update({"الوزن": -1.0}), "سلامة الحركات", "وزن غير صالح")
print("✔ الحركة بتاريخ أو فترة أو وزن غير صالح تُكشف برقمها")

# الذاكرة = القاعدة
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "i.db")
with sqlite3.connect(path) as c:
    c.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, name TEXT, op_type TEXT, weight REAL, "
              "settled_status TEXT)")
    for inv in World().invoices.values():
        c.execute("INSERT INTO invoices VALUES (?,?,?,?,?)", (inv["رقم الفاتورة"], inv["الاسم"], inv["النوع"],
                                                              inv["الوزن"], inv["settled_status"]))
w = World(); w.db_path = path
bad, res, _n = fails(w)
assert not bad and res["الذاكرة = القاعدة"][0] == 2
w.invoices[3]["الوزن"] = 2.5
bad, _r, _n = fails(w)
assert any("1 حركة تختلف" in d for d in bad["الذاكرة = القاعدة"]), bad
w = World(); w.db_path = path
w.invoices[9] = leg(9, "عامل", "صرف ذهب", 1.0, "")
bad, _r, _n = fails(w)
assert any("في الشاشات لا في القاعدة: 1" in d for d in bad["الذاكرة = القاعدة"]), bad
print("✔ الذاكرة = القاعدة: حركة معدّلة في الشاشات فقط أو غير محفوظة تُكشف")

# ملاحظات: قيد بلا رقم واسم غير مسجّل
w = World()
w.invoices[4] = leg(4, "حساب غريب", "قيد يومي مدين", 1.0, "")
_bad, _r, notes = fails(w)
assert any("1 طرف قيد يومي بلا رقم قيد" in n for n in notes) and any("حساب غريب" in n for n in notes), notes
print("✔ القيود القديمة بلا رقم والأسماء غير المسجّلة تظهر ملاحظاتٍ لا أخطاء")

# الفترة تعود حتى لو فشل فحص في منتصفه
w = World()
w.get_box_khayas_cumulative = lambda cat, month=None: 1 / 0
try:
    w.run_integrity_checks()
except ZeroDivisionError:
    pass
assert w.current_display_month == "2026-09"
print("✔ الفترة المعروضة تعود كما كانت حتى لو تعذّر إكمال الفحص")

# رصيد الكشف بطبيعة الحساب
st = {"re": re}
exec("class S:\n" + textwrap.indent(member_src("statement_balance"), "    "), st)
s_ = st["S"]()
s_.get_account_ledger_rows = lambda acc, f, t: [{"مدين": 10.0, "دائن": 0.0, "is_opening": True},
                                                 {"مدين": 2.0, "دائن": 5.0}]
s_.is_debit_nature_account = lambda acc: acc == "حساب الخزينة"
assert s_.statement_balance("حساب الخزينة") == 7.0 and s_.statement_balance("المبيعات") == -7.0
assert s_.statement_balance("حساب الخزينة", period_rows_only=True) == -3.0
print("✔ رصيد الكشف بطبيعة الحساب، وسطر «رصيد أول المدة» يُستبعد عند طلب حركات الفترة")

txt = World().integrity_report_text(*World().run_integrity_checks(), seconds=1.2)
assert "✅ كل الحسابات متطابقة" in txt and "(1.2 ث)" in txt
win = body("open_integrity_check_window")
assert "self.run_integrity_checks()" in win and "clipboard_append" in win
assert "self.open_integrity_check_window" in body("build_home_screen")
print("✔ نافذة الفحص: ملخص ثم جدول المجموعات ثم التفصيل، مع إعادة الفحص ونسخ التقرير، من الرئيسية")

print("\n✅ فحص سلامة الحسابات سليم")
