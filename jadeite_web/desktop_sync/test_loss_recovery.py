# -*- coding: utf-8 -*-
"""
اختبار نموذج الفاقد والمسترجع لمراحل التصنيع — يشغّل الدوال الحقيقية من البرنامج
(ومنها الحفظ الفعلي في قاعدة SQLite مؤقتة):

  لكل مرحلة (صندوق خياس) ثلاثة حسابات:
    • المرحلة نفسها ← فاقدها الحالي = الصرف − القبض، وكل فترة مستقلة بفاقدها
    • «فاقد X»      ← يستقبل الفاقد الحالي بزر الإقفال وحده، ويتراكم عبر الفترات،
                       ويقبل رصيداً افتتاحياً بقيد يومي
    • «مسترجع X»    ← يستقبل كل مسترجع (الوارد، وقبض «مسترجع» في الكاستنج،
                       ومسترجع الأشجار) — لا يُقفل شيئاً ولا يمسّ الفاقد الحالي
  شاشة الخسائر لكل صندوق: الفاقد الحالي، فاقد X، مسترجع X، الصافي = الفاقد − المسترجع.
"""
import ast, calendar, datetime, io, os, shutil, sqlite3, sys, tempfile, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
lines = src.split("\n")
tree = ast.parse(src)
APP = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def method_src(name):
    node = next(m for m in APP.body if isinstance(m, ast.FunctionDef) and m.name == name)
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])
    return textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))


def attr_src(name):
    node = next(m for m in APP.body if isinstance(m, ast.Assign)
                and any(getattr(t, "id", None) == name for t in m.targets))
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


def module_value(name):
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == name for t in n.targets))
    return ast.literal_eval(node.value)


seg = method_src
M6, M7, M8, M9 = "2026-06", "2026-07", "2026-08", "2026-09"
CAST, CAST_BOX, CAST_LOSS, CAST_REC = "الكاستنج", "الكاستنج", "فاقد الكاستنج", "مسترجع كاستنج"
LOSSES = "حساب الخسائر"

METHODS = [
    # الحسابات والأسماء
    "get_khayas_box_categories", "get_box_recovery_name", "get_box_loss_account", "get_all_loss_accounts",
    "get_stage_config", "get_display_label", "get_box_account_name", "get_all_stage_categories",
    "get_all_mustarja_names", "get_inbound_account_options", "get_supplier_name_values", "check_name_exists",
    "get_account_statement_options", "get_journal_entry_account_options",
    # الأرقام
    "journal_partner_index", "journal_partner", "get_box_loss_total", "get_box_recovered_total",
    "get_box_loss_summary", "get_current_unclosed_khayas", "get_box_khayas_cumulative",
    "get_box_closed_total", "get_stage_totals_for_month", "get_treasury_type_sets", "treasury_bucket",
    # الفهارس والفترات والحفظ
    "invoices_by_name", "invoices_by_period", "period_invoices", "inv_period", "inv_in_period",
    "period_closing_datetime", "mark_backup_dirty", "save_invoice_to_db",
    # الإقفال والبيانات القديمة
    "close_khayas_box", "close_split_khayas_box", "_post_closing_entry", "neutralize_auto_recovery_closings",
    # الوارد والقيد اليومي
    "submit_inbound", "submit_journal_entry",
    # الكاستنج
    "get_cast_operation", "_read_weight", "submit_casting_op", "submit_casting_loss_op",
    "submit_casting_recovery_op", "collect_stage_ops_rows", "render_stage_ops_table",
    "is_row_recovery", "is_recovery_op", "row_sort_key",
    # كشف الحساب والتراجع عن الإقفال
    "is_debit_nature_account", "get_account_ledger_rows", "_account_ledger_rows_all",
    "get_box_closing_entries",
]
ATTRS = ["BOX_DISPLAY_OVERRIDES", "RECOVERY_IN_TYPES", "JOURNAL_TYPES", "LOSS_PARENT_ACCOUNT",
         "AUTO_RECOVERY_CLOSE_NOTE", "INBOUND_TYPES", "INBOUND_DEFAULT_ACCOUNT", "OPENING_ACCOUNT",
         "CAST_OPERATIONS", "CAST_MODE_FIELDS", "MADIN_DAEN_ACCOUNTS"]

EXTRA = '''
def check_edit_permission(self): return True
def recalculate_all(self): self.recalcs += 1
def refresh_losses_tab(self): pass
def refresh_casting_table(self): pass
def register_operation_period(self, d): pass
def save_name_to_db(self, name, cat): pass
def print_single_inout_operation(self, i): pass
def print_single_journal_entry(self, ref): pass
def after(self, ms, fn=None): pass
def get_smart_default_date(self): return "2026-09-01"
def get_actual_section_khayas(self, cat, target_month=None, **k): return self._live.get((cat, target_month), 0.0)
def get_section_khayas_parts(self, cat, target_month=None): return self._parts[(cat, target_month)]
def get_sales_ops_khayas_total(self, month=None): return 0.0
def negative_color_enabled(self, section): return False
def reuse_or_create_tree(self, frame, cols, height=11, sticky_total=False):
    self._tree, self._total = FakeTree(cols), FakeTree(cols)
    return self._tree, self._total, False
def apply_column_labels(self, tree, key): pass
def fit_columns_to_content(self, tree, key, **k): pass
def enable_column_rename(self, tree, key, on_renamed=None): pass
'''

msgs, texts = [], []          # عناوين الرسائل ونصوصها بالترتيب


class FakeBox:
    @staticmethod
    def askyesno(title, *a, **k):
        msgs.append(title)
        texts.append(a[0] if a else "")
        return title not in ("طباعة", "اسم غير مسجّل")

    @staticmethod
    def showinfo(title, *a, **k):
        msgs.append(title)
        texts.append(a[0] if a else "")

    showwarning = showerror = showinfo


class W:
    """خانة إدخال بديلة (Entry/ComboBox/Label)"""
    def __init__(self, v=""):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v

    def delete(self, *a):
        self.v = ""

    def insert(self, _i, v):
        self.v = str(v) + self.v

    def configure(self, **k):
        if "text" in k:
            self.v = k["text"]

    def focus(self):
        pass

    focus_set = focus


class FakeTree:
    def __init__(self, cols):
        self.cols, self.rows = cols, []

    def insert(self, _parent, _where, values=(), tags=()):
        self.rows.append(dict(zip(self.cols, values)))
        return f"I{len(self.rows)}"

    def get_children(self):
        return [f"I{i + 1}" for i in range(len(self.rows))]

    def tag_configure(self, *a, **k):
        pass

    column = bind = see = tag_configure


errors = []
ns = {"messagebox": FakeBox, "datetime": datetime, "calendar": calendar, "sqlite3": sqlite3,
      "MEMO_STATUS": module_value("MEMO_STATUS"), "COUNTED_STATUSES": module_value("COUNTED_STATUSES"),
      "IS_ADMIN_BUILD": False, "log_cloud_error": lambda *a, **k: errors.append(a),
      "en": lambda v: f"{v:.2f}", "FakeTree": FakeTree}
body = "\n".join(textwrap.indent(attr_src(a), "    ") for a in ATTRS)
body += "\n" + "\n".join(textwrap.indent(method_src(m), "    ") for m in METHODS)
exec("class App:\n" + body + "\n" + textwrap.indent(EXTRA, "    "), ns)
App = ns["App"]

TMP = tempfile.mkdtemp(prefix="loss_recovery_")
SCHEMA = """CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
            weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
            trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '',
            manual_no TEXT DEFAULT '', period TEXT DEFAULT '')"""


def new_app(admin=False):
    ns["IS_ADMIN_BUILD"] = admin
    app = App()
    app.categories = {"المصنعين": [], "المركبين": [], "الموردين": [], "أقسام_خياس_إضافية": ["صب داخلي"]}
    app.current_display_month = M9
    app.invoice_counter = 1000
    app.invoices = {}
    app.recalcs = 0
    app._live, app._parts = {}, {}
    app.lbl_op_status, app.lbl_je_status = W(), W()
    app.db_path = os.path.join(TMP, f"db{len(os.listdir(TMP))}.sqlite")
    with sqlite3.connect(app.db_path) as conn:
        conn.execute(SCHEMA)
    return app


def add(app, name, t, w, period, note="", row="", ref="", date=None):
    """حركة خام بمسار الحفظ الحقيقي (للبيانات القديمة والحركات المباشرة)"""
    app.invoice_counter += 1
    i = app.invoice_counter
    inv = {"رقم الفاتورة": i, "التاريخ": date or f"{period}-10 10:00:00", "الاسم": name, "النوع": t,
           "الوزن": w, "البيان": note, "settled_status": "ACTIVE", "trees_count": 0.0, "قبل": 0.0,
           "بعد": 0.0, "row_number": row, "set_number": ref, "period": period}
    app.invoices[i] = inv
    app.save_invoice_to_db(i, inv)
    return i


def journal(app, debit, credit, amount, month):
    """قيد يومي من شاشة القيود اليومية نفسها (submit_journal_entry)"""
    app.current_display_month = month
    app.je_from_name, app.je_to_name = W(debit), W(credit)
    app.je_date, app.je_amount = W(f"{month}-05"), W(str(amount))
    before = len(msgs)
    app.submit_journal_entry()
    assert "اسم غير مسجّل" not in msgs[before:], (debit, credit)


def cast_loss(app, month, row, sarf="", qabd="", recover="", trees="", note=""):
    app.current_display_month = month
    app.cast_op = W("فاقد")
    app.cast_date, app.cast_note, app.cast_row_num = W(f"{month}-15"), W(note), W(row)
    app.cast_sarf, app.cast_qabd, app.cast_recover, app.cast_trees = W(sarf), W(qabd), W(recover), W(trees)
    app.submit_casting_op()


def cast_recovery(app, month, sarf="", qabd="", note=""):
    app.current_display_month = month
    app.cast_op = W("مسترجع")
    app.cast_date, app.cast_note = W(f"{month}-20"), W(note)
    app.cast_sarf, app.cast_qabd = W(sarf), W(qabd)
    app.submit_casting_op()


def inbound(app, month, weight, to_account, supplier="المصنع", voucher="V1", carat="18", note=""):
    app.current_display_month = month
    app.in_date, app.in_invoice_num, app.in_supplier = W(f"{month}-12"), W(voucher), W(supplier)
    app.in_type, app.in_weight, app.in_carat, app.in_note = W("ذهب"), W(str(weight)), W(carat), W(note)
    app.in_to_account = W(to_account)
    app.submit_inbound()


def summary(app, cat, month=None):
    s = app.get_box_loss_summary(cat, month=month)
    return (s["current"], s["loss"], s["recovered"], s["net"])


def journal_legs(app):
    return [i for i in app.invoices.values() if i["النوع"] in ("قيد يومي مدين", "قيد يومي دائن")]


def balance(rows, debit_nature):
    return round(sum((r["مدين"] - r["دائن"]) if debit_nature else (r["دائن"] - r["مدين"]) for r in rows), 2)


# ═══ ١) لكل مرحلة ثلاثة حسابات ═══
a = new_app()
assert (a.get_box_account_name(CAST), a.get_box_loss_account(CAST), a.get_box_recovery_name(CAST)) == \
       (CAST_BOX, CAST_LOSS, CAST_REC)
assert (a.get_box_loss_account("صب داخلي"), a.get_box_recovery_name("صب داخلي")) == ("فاقد صب داخلي", "مسترجع صب داخلي")
assert (a.get_box_loss_account("التلميع"), a.get_box_loss_account("التلميع/البف")) == ("فاقد التلميع/البف", "فاقد البوليش")
assert (a.get_box_loss_account("المصنعين"), a.get_box_recovery_name("المصنعين")) == ("فاقد المصنعين", "مسترجع المصنعين")
losses = a.get_all_loss_accounts()
cats = a.get_khayas_box_categories()
assert len(losses) == len(set(losses)) == len(cats) == 7, losses
others = {a.get_box_account_name(c) for c in cats} | {a.get_box_recovery_name(c) for c in cats} | {LOSSES}
assert not set(losses) & others
print(f"✔ لكل مرحلة ثلاثة حسابات مستقلة: المرحلة، «فاقد X»، «مسترجع X» ({len(cats)} مراحل، ومنها المضافة)")

opts = a.get_account_statement_options()
assert set(losses) <= set(opts) and LOSSES in opts and "رصيد افتتاحي" in opts and CAST_REC in opts
assert all(a.is_debit_nature_account(n) for n in losses + [LOSSES])
assert not a.is_debit_nature_account(CAST_REC) and not a.is_debit_nature_account(CAST_BOX)
print("✔ حسابات الفاقد في كشف الحساب وخانتي القيد اليومي؛ رصيدها مدين − دائن (والمسترجع دائن − مدين)")

# ═══ ٢) الكاستنج: عمليتا «فاقد» و«مسترجع» — مثال فترة ٨ ═══
cast_loss(a, M8, "1", sarf="100", qabd="95", recover="1", trees="4", note="شجرة")
cast_recovery(a, M8, sarf="10", qabd="8", note="غبار الفرن")
a.current_display_month = M9
m8 = [i for i in a.invoices.values() if i["period"] == M8]
assert sorted((i["الاسم"], i["النوع"], i["الوزن"], i["row_number"]) for i in m8) == sorted([
    ("كاستنج", "صرف كاستنج", 100.0, "1"), ("كاستنج", "قبض كاستنج", 95.0, "1"),
    (CAST_REC, "وارد ذهب (عيار 18)", 1.0, "1"),                  # مسترجع الأشجار للصف
    (CAST_REC, "صرف كاستنج", 10.0, ""), (CAST_REC, "وارد ذهب (عيار 18)", 8.0, "")])
assert not journal_legs(a), "لا قيد إقفال يُنشأ من الترحيل"
print("✔ «مسترجع»: الصرف صرفٌ للكاستنج، والقبض وارد باسم «مسترجع كاستنج» — بلا رقم صف وبلا أي إقفال")

assert summary(a, CAST, M8) == (15.0, 0.0, 9.0, -9.0), summary(a, CAST, M8)
print("✔ الفاقد الحالي لفترة ٨ = صرف 100 + صرف مسترجع 10 − قبض 95 = 15 (المسترجع 9 لا يُطرح منه)")

sets = a.get_treasury_type_sets()
treasury = round(sum(a.treasury_bucket(i, sets)[1] for i in m8), 2)
assert treasury == -6.0, treasury
print("✔ الخزينة: خرج 110 وعاد 95 + 9 مسترجع = −6 (وهو الصافي بعد الإقفال: 15 − 9)")

# الجدول: «فاقد» يعرض كل العمليات، و«مسترجع» عملياته وحدها
a.current_display_month = M8
rows = a.collect_stage_ops_rows("صرف كاستنج", "قبض كاستنج", CAST_REC)
assert [g["op"] for _r, _n, g in rows] == ["فاقد", "مسترجع", "مسترجع"]
assert (rows[0][2]["مدين"], rows[0][2]["دائن"], rows[0][2]["مسترجع"]) == (100.0, 95.0, 1.0)
assert sorted((g["مدين"], g["مسترجع"]) for _r, _n, g in rows[1:]) == [(0.0, 8.0), (10.0, 0.0)]
tot = W()
a.render_stage_ops_table(None, "صرف كاستنج", "قبض كاستنج", with_trees=True, recover_name=CAST_REC,
                         op_filter="فاقد", section=CAST, totals_label=tot)
data = [r for r in a._tree.rows if r["الصف"] != "إجمالي الشهر"]
assert [r["العملية"] for r in data] == ["فاقد", "مسترجع", "مسترجع"], [r["العملية"] for r in data]
assert "صرف: 110.00" in tot.v and "قبض: 95.00" in tot.v and "الخياس: 15.00" in tot.v and "المسترجع: 9.00" in tot.v, tot.v
a.render_stage_ops_table(None, "صرف كاستنج", "قبض كاستنج", with_trees=True, recover_name=CAST_REC,
                         op_filter="مسترجع", section=CAST, totals_label=tot)
data = [r for r in a._tree.rows if r["الصف"] != "إجمالي الشهر"]
assert [r["العملية"] for r in data] == ["مسترجع", "مسترجع"] and all(r["الصف"] == "-" for r in data)
assert "صرف: 10.00" in tot.v and "المسترجع: 8.00" in tot.v, tot.v
print("✔ الجدول: «فاقد» يعرض كل العمليات (الصرف 110 بما فيه صرف المسترجع)، و«مسترجع» عملياته وحدها")

# ═══ ٣) الإقفال بالزر وحده ← حساب «فاقد الكاستنج» ═══
a.current_display_month = M9
before = len(a.invoices)
a.close_khayas_box(CAST, month=M8)
legs = journal_legs(a)
assert len(a.invoices) == before + 2 and len(legs) == 2
dr = next(x for x in legs if x["النوع"] == "قيد يومي مدين")
cr = next(x for x in legs if x["النوع"] == "قيد يومي دائن")
assert (dr["الاسم"], cr["الاسم"], dr["الوزن"]) == (CAST_LOSS, CAST_BOX, 15.0)
assert dr["period"] == cr["period"] == M8 and dr["التاريخ"] == "2026-08-31 23:59:00"
assert dr["set_number"] == cr["set_number"] and a.journal_partner(dr) is cr
assert summary(a, CAST, M8) == (0.0, 15.0, 9.0, 6.0), summary(a, CAST, M8)
print("✔ زر الإقفال: مدين «فاقد الكاستنج» 15 / دائن «الكاستنج» 15، بفترة ٨ وآخر يوم فيها")
print("✔ بعده: الفاقد الحالي 0 | فاقد الكاستنج 15 | المسترجع 9 | الصافي 6")

before = len(a.invoices)
a.close_khayas_box(CAST, month=M8)
assert len(a.invoices) == before and msgs[-1] == "لا يوجد خياس"
print("✔ لا إقفال مرتين لفترة واحدة")

# ═══ ٤) كل فترة مستقلة، والوارد إلى حساب المسترجع لا يُقفل شيئاً ═══
cast_loss(a, M9, "1", sarf="50", qabd="48")
a.current_display_month = M9
assert summary(a, CAST, M9) == (2.0, 15.0, 9.0, 6.0), summary(a, CAST, M9)
assert a.get_current_unclosed_khayas(CAST, month=M8) == 0.0
print("✔ فترة ٩ تبدأ بفاقدها وحدها (2)، وفاقد الكاستنج يبقى 15 من فترة ٨")

legs_before = len(journal_legs(a))
inbound(a, M9, 3, CAST_REC, supplier="المصنع", note="بودرة")
rec = a.invoices[a.invoice_counter]
assert (rec["الاسم"], rec["النوع"], rec["الوزن"], rec["البيان"]) == (CAST_REC, "وارد ذهب (عيار 18)", 3.0, "بودرة — من المصنع")
assert len(journal_legs(a)) == legs_before, "الوارد إلى المسترجع لا يُنشئ قيد إقفال"
assert summary(a, CAST, M9) == (2.0, 15.0, 12.0, 3.0), summary(a, CAST, M9)
confirm = texts[len(msgs) - 1 - msgs[::-1].index("تأكيد الترحيل")]
assert f"في حساب «{CAST_REC}»" in confirm and "لا يُقفل أي فاقد" in confirm, confirm
print("✔ الوارد «إلى حساب مسترجع كاستنج»: يذهب لحساب المسترجع (12) — الفاقد الحالي باقٍ 2 بلا إقفال")
assert a.treasury_bucket(rec, a.get_treasury_type_sets()) == ("inbound", 3.0)
print("✔ ويُحتسب «وارداً» دخلنا: في لوحة الوارد بالرئيسية والتقرير الشهري (لا يُنقص الخياس)")

# اسم الصندوق في خانة المورد (الطريقة القديمة) يُسجَّل مسترجعاً أيضاً — بلا إقفال
inbound(a, M9, 1, a.INBOUND_DEFAULT_ACCOUNT, supplier=CAST_BOX, voucher="V2")
assert a.invoices[a.invoice_counter]["الاسم"] == CAST_REC and len(journal_legs(a)) == legs_before
assert summary(a, CAST, M9) == (2.0, 15.0, 13.0, 2.0), summary(a, CAST, M9)
print("✔ كتابة اسم المرحلة في خانة المورد تُسجَّل في مسترجعها — ولا إقفال تلقائي إطلاقاً")

a.close_khayas_box(CAST, month=M9)
assert summary(a, CAST, M9) == (0.0, 17.0, 13.0, 4.0), summary(a, CAST, M9)
print("✔ إقفال فترة ٩ بالزر: فاقد الكاستنج يتراكم 15 + 2 = 17، والصافي 17 − 13 = 4")

# ترتيب العمليات لا يغيّر النتيجة: المسترجع قبل الإقفال أو بعده
b = new_app()
inbound(b, M8, 4, CAST_REC)                                 # المسترجع أولاً
cast_loss(b, M8, "1", sarf="100", qabd="95", recover="1")
cast_recovery(b, M8, sarf="10", qabd="8")
cast_loss(b, M9, "1", sarf="50", qabd="48")
b.current_display_month = M9
b.close_khayas_box(CAST, month=M8)
b.close_khayas_box(CAST, month=M9)
assert summary(b, CAST, M9) == summary(a, CAST, M9), (summary(b, CAST, M9), summary(a, CAST, M9))
print("✔ المسترجع قبل الإقفال أو بعده: النتيجة نفسها (لا ازدواج ولا نقص)")

# ═══ ٥) رصيد افتتاحي لحساب الفاقد وحساب المسترجع ═══
journal(a, CAST_LOSS, "رصيد افتتاحي", 20, M9)
journal(a, "رصيد افتتاحي", CAST_REC, 4, M9)
assert summary(a, CAST, M9) == (0.0, 37.0, 17.0, 20.0), summary(a, CAST, M9)
print("✔ رصيد افتتاحي بقيد يومي: مدين «فاقد الكاستنج» 20 ← الفاقد 37، ودائن «مسترجع كاستنج» 4 ← المسترجع 17")

journal(a, "فاقد صب داخلي", "رصيد افتتاحي", 30, M9)
assert summary(a, "صب داخلي", M9) == (0.0, 30.0, 0.0, 30.0)
print("✔ مرحلة بلا أي حركة: رصيدها الافتتاحي في «فاقد صب داخلي» يظهر في شاشة الخسائر (30)")

# قيد بين المرحلة وحساب آخر (غير الفاقد) تسوية لفاقدها الحالي لا إقفال
journal(a, "حساب الخزينة", CAST_BOX, 2, M9)
assert summary(a, CAST, M9) == (-2.0, 37.0, 17.0, 20.0), summary(a, CAST, M9)
print("✔ قيد بين المرحلة والخزينة يسوّي فاقدها الحالي ولا يُحسب إقفالاً في «فاقد الكاستنج»")
closings = sorted(e["amount"] for e in a.get_box_closing_entries(CAST))
assert closings == [2.0, 15.0], closings
print("✔ «تراجع عن الإقفال» يعرض الإقفالين وحدهما (15 و2) — لا قيد الخزينة ولا الرصيد الافتتاحي")
a.invoices[a.invoice_counter]["settled_status"] = a.invoices[a.invoice_counter - 1]["settled_status"] = "MEMO"
a._inv_version = getattr(a, "_inv_version", 0) + 1

# ═══ ٦) الإقفالات القديمة على «حساب الخسائر» تُحسب في فاقد المرحلة ═══
add(a, "كاستنج", "صرف كاستنج", 5.0, M7)
ref = f"JE-{a.invoice_counter + 1}"
add(a, LOSSES, "قيد يومي مدين", 5.0, M7, "إقفال خياس", ref=ref)
add(a, CAST_BOX, "قيد يومي دائن", 5.0, M7, "إقفال خياس", ref=ref)
assert a.get_current_unclosed_khayas(CAST, month=M7) == 0.0
assert summary(a, CAST, M9) == (0.0, 42.0, 17.0, 25.0), summary(a, CAST, M9)
assert sorted(e["amount"] for e in a.get_box_closing_entries(CAST)) == [2.0, 5.0, 15.0]
print("✔ إقفال سابق لإنشاء حسابات الفاقد (على «حساب الخسائر») يُحسب في «فاقد الكاستنج» (42) ويمكن التراجع عنه")

# ═══ ٧) كشوف الحسابات تطابق شاشة الخسائر ═══
rows = a.get_account_ledger_rows(CAST_LOSS, "", "")
assert balance(rows, True) == a.get_box_loss_total(CAST) == 42.0, balance(rows, True)
assert any(r["الاسم"] == CAST_BOX and r["period"] == M7 for r in rows), "الإقفال القديم يظهر في كشف الفاقد"
rows9 = a.get_account_ledger_rows(CAST_LOSS, M9, M9)
assert rows9[0].get("is_opening") and rows9[0]["مدين"] == 20.0, rows9[0]      # 15 (فترة ٨) + 5 (فترة ٧)
assert balance(rows9, True) == 42.0
print("✔ كشف «فاقد الكاستنج» = 42 (مع الإقفال القديم)، ورصيد أول مدة فترة ٩ = إقفالات ما قبلها (20)")

rows = a.get_account_ledger_rows(CAST_REC, "", "")
assert balance(rows, False) == a.get_box_recovered_total(CAST) == 17.0, balance(rows, False)
print("✔ كشف «مسترجع كاستنج» = 17 = قسم المسترجع في شاشة الخسائر")

rows = a.get_account_ledger_rows(LOSSES, "", "")
total_losses = round(sum(a.get_box_loss_total(c) for c in a.get_khayas_box_categories()), 2)
assert balance(rows, True) == total_losses == 72.0, (balance(rows, True), total_losses)
print("✔ «حساب الخسائر» = إجمالي فاقد كل المراحل (42 + 30 = 72) في كشفه")

rows = a.get_account_ledger_rows(CAST_BOX, M8, M8)
assert any(r["البيان"] == "غبار الفرن" and r["مدين"] == 10.0 for r in rows)
assert balance(rows, False) == 0.0          # فترة ٨ مقفلة بالكامل
print("✔ كشف «الكاستنج» لفترة ٨ يعرض صرف المسترجع مع صرفه، ورصيده صفر بعد الإقفال")

# ═══ ٨) إلغاء «الإقفال التلقائي عند الوارد» في البيانات السابقة ═══
def legacy(app, month, sarf, qabd, recovered, remainder):
    """بيانات بالشكل الذي كان يسجّله الإصدار السابق: وارد مسترجع + قيد «مسترجع» يليه مباشرة"""
    add(app, "كاستنج", "صرف كاستنج", sarf, month)
    add(app, "كاستنج", "قبض كاستنج", qabd, month)
    dt = f"{month}-12 09:30:00"
    inv_id = add(app, CAST_REC, "وارد ذهب (عيار 18)", recovered, month, date=dt)
    ref = f"JE-{inv_id + 1}"
    debit, credit = (LOSSES, CAST_BOX) if remainder > 0 else (CAST_BOX, LOSSES)
    add(app, debit, "قيد يومي مدين", abs(remainder), month, "مسترجع", ref=ref, date=dt)
    add(app, credit, "قيد يومي دائن", abs(remainder), month, "مسترجع", ref=ref, date=dt)
    return inv_id


for admin in (False, True):
    c = new_app(admin=admin)
    legacy(c, M6, 10.0, 7.0, 1.0, 2.0)                 # فاقد 3: مسترجع 1 وأُقفل الباقي 2 تلقائياً
    legacy(c, M7, 10.0, 7.0, 5.0, -2.0)                # مسترجع 5 أكبر من الفاقد 3: قيد معاكس 2
    # لا يُمسّ: إقفال بالزر، وقيد بالبيان «مسترجع» بعد وارد عادي (لا مسترجع)،
    # وقيد يدوي (بيانه فارغ كما تسجّله شاشة القيود) بعد وارد مسترجع مباشرة
    add(c, "كاستنج", "صرف كاستنج", 4.0, M8)
    c.close_khayas_box(CAST, month=M8)
    for supplier, w, note, day in (("المصنع", 1.0, "مسترجع", 12), (CAST_REC, 0.5, "", 13)):
        dt = f"{M8}-{day} 09:30:00"
        first = add(c, supplier, "وارد ذهب (عيار 18)", 2.0 if supplier == "المصنع" else 1.0, M8, date=dt)
        ref = f"JE-{first + 1}"
        add(c, LOSSES, "قيد يومي مدين", w, M8, note, ref=ref, date=dt)
        add(c, CAST_BOX, "قيد يومي دائن", w, M8, note, ref=ref, date=dt)
    old = summary(c, CAST, M6)
    assert old == (1.0, 5.5, 7.0, -1.5), old            # فاقد ٦ الحالي 3 − 2 أُقفل تلقائياً
    assert c.get_current_unclosed_khayas(CAST, month=M7) == 5.0       # 3 + قيد معاكس 2

    fixed = c.neutralize_auto_recovery_closings()
    assert fixed == 2, fixed
    memo = [i for i in c.invoices.values() if i["settled_status"] == "MEMO"]
    assert len(memo) == 4 and all(i["البيان"] == c.AUTO_RECOVERY_CLOSE_NOTE for i in memo)
    assert summary(c, CAST, M6) == (3.0, 5.5, 7.0, -1.5), summary(c, CAST, M6)
    assert c.get_current_unclosed_khayas(CAST, month=M7) == 3.0
    assert c.get_current_unclosed_khayas(CAST, month=M8) == -1.5      # القيدان اليدويان باقيان كما هما
    with sqlite3.connect(c.db_path) as conn:
        stored = conn.execute("SELECT COUNT(*) FROM invoices WHERE settled_status = 'MEMO'").fetchone()[0]
    assert stored == (0 if admin else 4), (admin, stored)
    assert c.neutralize_auto_recovery_closings() == 0
    assert not errors, errors
print("✔ الإقفالات التلقائية القديمة (بالاتجاهين) تُلغى: تبقى محفوظة سطوراً معلوماتية (MEMO) بسببها")
print("✔ فيعود فاقد تلك الفترات كاملاً ليُقفل بالزر؛ والقيود اليدوية وإقفالات الزر لا تُمسّ")
print("✔ نسخة العميل تحفظ الإلغاء في قاعدتها (فيُرفع للسحابة)، والمدير في الذاكرة فقط؛ وتكراره لا يغيّر شيئاً")

# ═══ ٩) المصنعون والمركبون: المسترجع لا يُخصم من الخياس الحالي ═══
d = new_app()
d._live[("المصنعين", M8)] = 12.0
d._parts[("المصنعين", M8)] = (20.0, 5.0, 3.0, 12.0)
inbound(d, M8, 2, "مسترجع المصنعين")
d.current_display_month = M9
assert summary(d, "المصنعين", M8) == (12.0, 0.0, 2.0, -2.0), summary(d, "المصنعين", M8)
d.close_khayas_box("المصنعين", month=M8)
legs = journal_legs(d)
assert {x["الاسم"] for x in legs} == {"فاقد المصنعين", "صندوق خياس المصنعين"} and all(x["period"] == M8 for x in legs)
assert summary(d, "المصنعين", M8) == (0.0, 12.0, 2.0, 10.0), summary(d, "المصنعين", M8)
print("✔ المصنعون: الخياس 12 يبقى كما هو مع المسترجع 2، والإقفال بقيديه يُرحَّل إلى «فاقد المصنعين» (الصافي 10)")

# بقايا الكسور لا تُعرض «-0.00»: صرف 0.3 وقبض 0.1 + 0.2 (= 0.30000000000000004)
z = new_app()
for w_, t_ in ((0.3, "صرف كاستنج"), (0.1, "قبض كاستنج"), (0.2, "قبض كاستنج")):
    add(z, "كاستنج", t_, w_, M9)
assert all(f"{v:.2f}" == "0.00" for v in z.get_box_loss_summary(CAST, month=M9).values()), \
    z.get_box_loss_summary(CAST, month=M9)
print("✔ الفاقد الحالي بعد الإقفال يُعرض 0.00 لا «-0.00» (بقايا الكسور العشرية)")

# ═══ ١٠) الواجهة ═══
e = new_app()
e.cast_op = W("مسترجع")
assert e.get_cast_operation() == "مسترجع"
e.cast_op = W("شيء آخر")
assert e.get_cast_operation() == "فاقد"
del e.cast_op
assert e.get_cast_operation() == "فاقد"
assert e.CAST_OPERATIONS == ("فاقد", "مسترجع") and tuple(e.CAST_MODE_FIELDS["مسترجع"]) == ("sarf", "qabd")
assert set(e.CAST_MODE_FIELDS["فاقد"]) == {"row_num", "sarf", "qabd", "recover", "trees"}
cast_ui = seg("build_casting_ui")
assert "operations=self.CAST_OPERATIONS" in cast_ui and "name_values" not in cast_ui
panel = seg("build_stage_panel")
assert 'specs.append(("op", "العملية", 2))' in panel and "CTkSegmentedButton" in panel
assert "grid_remove()" in panel and "on_operation_change(mode)" in panel
assert "op_filter=operation" in seg("refresh_casting_table")
print("✔ الكاستنج: خانة «العملية» (فاقد/مسترجع) مكان الاسم؛ «مسترجع» يُظهر الصرف والقبض وحدهما ويصفّي الجدول")

e.cast_op = W("مسترجع")
e.cast_date, e.cast_note, e.cast_sarf, e.cast_qabd = W("2026-09-02"), W(""), W("-3"), W("")
before = len(e.invoices)
e.submit_casting_op()
assert len(e.invoices) == before and msgs[-1] == "تنبيه"
e.cast_sarf = W("abc")
e.submit_casting_op()
assert len(e.invoices) == before
print("✔ «مسترجع» يرفض القيم السالبة وغير الرقمية ولا يرحّل شيئاً")

assert "قيد يومي" not in seg("submit_inbound") and LOSSES not in seg("submit_inbound")
assert "self.neutralize_auto_recovery_closings()" in seg("load_data_from_db")
cards = seg("refresh_losses_cards")
assert "loss_account, recovery_account = self.get_box_loss_account(cat), self.get_box_recovery_name(cat)" in cards
assert "account=loss_account)" in cards and "account=recovery_account)" in cards
assert '"الصافي (الفاقد − المسترجع)"' in cards
coa = seg("refresh_chart_of_accounts")
assert "add_leaf(stage, self.get_box_loss_account(cat))" in coa and "add_leaf(stage, recovery)" in coa
print("✔ شاشة الوارد لا تُنشئ أي قيد؛ ولوحات الخسائر تفتح كشف كل حساب؛ والشجرة: المرحلة ← فاقدها ومسترجعها")

shutil.rmtree(TMP, ignore_errors=True)
print("\n✅ نموذج الفاقد والمسترجع سليم")
