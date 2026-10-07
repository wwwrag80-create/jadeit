# -*- coding: utf-8 -*-
"""
اختبار نموذج الفاقد والمسترجع لمراحل التصنيع — يشغّل الدوال الحقيقية من البرنامج
(ومنها الحفظ الفعلي في قاعدة SQLite مؤقتة):

  لكل مرحلة (صندوق خياس) ثلاثة حسابات:
    • المرحلة نفسها ← فاقدها الحالي = الصرف − القبض، وكل فترة مستقلة بفاقدها.
                       و«المسترجع» في شاشة الكاستنج (عملية «مسترجع» ومسترجع الأشجار)
                       رجوعٌ من هذا الفاقد نفسه: صرفه يزيده وقبضه يُخصم منه
    • «فاقد X»      ← يستقبل الفاقد الحالي بزر الإقفال وحده، ويتراكم عبر الفترات،
                       ويقبل رصيداً افتتاحياً بقيد يومي
    • «مسترجع X»    ← يستقبل الوارد إليه من شاشة الوارد — لا يُقفل شيئاً ولا يمسّ
                       الفاقد الحالي
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
    "get_box_loss_summary", "get_current_unclosed_khayas", "get_box_khayas_cumulative", "get_recorded_periods",
    # شاشة الخسائر: «من/إلى» بالقوائم (فترة، أو نطاق، أو «الكل»)
    "losses_period_options", "selected_losses_range", "set_losses_range", "losses_show_all",
    "reset_losses_period", "losses_close_period", "losses_statement_range", "losses_period_breakdown",
    "combo_range", "set_combo_range", "periods_in_range", "range_covers_all", "range_scope_label",
    "get_box_closed_total", "get_stage_totals_for_month", "get_treasury_type_sets", "treasury_bucket",
    # الفهارس والفترات والحفظ
    "invoices_by_name", "invoices_by_period", "period_invoices", "inv_period", "inv_in_period",
    "period_closing_datetime", "mark_backup_dirty", "save_invoice_to_db", "_undo_note_row", "invoice_from_row",
    # الإقفال والبيانات القديمة
    "close_khayas_box", "close_split_khayas_box", "_post_closing_entry", "neutralize_auto_recovery_closings",
    "migrate_casting_returns", "migrate_polish2_names",
    # الوارد والقيد اليومي
    "submit_inbound", "submit_journal_entry",
    # الكاستنج
    "get_cast_operation", "_read_weight", "submit_casting_op", "submit_casting_loss_op",
    "submit_casting_recovery_op", "collect_stage_ops_rows", "render_stage_ops_table",
    "is_row_recovery", "is_recovery_op", "row_sort_key", "stage_row_extra",
    # بوليش ١ (الليزر) والتلميع — بلا خانة اسم، وأسماء الحسابات الثابتة
    "submit_polish_buff_op", "submit_polish_op", "stage_row_taken", "get_account_label", "migrate_row_extras", "read_entry_date",
    # كشف الحساب والتراجع عن الإقفال
    "is_debit_nature_account", "get_account_ledger_rows", "_account_ledger_rows_all",
    "get_box_closing_entries",
    # خطوات التراجع (الإقفال يفتح خطوة)
    "push_undo", "_close_undo_step", "update_undo_buttons", "undo_step_label", "can_undo",
]
ATTRS = ["_DATE_DIGITS", "BOX_DISPLAY_OVERRIDES", "RECOVERY_IN_TYPES", "JOURNAL_TYPES", "LOSS_PARENT_ACCOUNT",
         "AUTO_RECOVERY_CLOSE_NOTE", "INBOUND_TYPES", "INBOUND_DEFAULT_ACCOUNT", "OPENING_ACCOUNT",
         "CAST_OPERATIONS", "CAST_MODE_FIELDS", "MADIN_DAEN_ACCOUNTS", "CAST_RETURN_NAME", "TREE_RETURN_NAME",
         "LASER_NAME", "ACCOUNT_LABELS", "UNDO_LIMIT", "INVOICE_COLUMNS", "LOSSES_ALL",
         "POLISH2_OLD_ACCOUNTS", "POLISH2_OLD_BAYAN", "POLISH2_SALE_BAYAN", "SALE_NOTE_SEP"]

EXTRA = '''
def check_edit_permission(self): return True
def recalculate_all(self): self.recalcs += 1
def refresh_losses_tab(self): pass
def refresh_casting_table(self): pass
def refresh_polish_buff_table(self): pass
def refresh_polish_table(self): pass
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
ns = {"messagebox": FakeBox, "datetime": datetime, "calendar": calendar, "sqlite3": sqlite3, "UI_FONT": "IBM Plex Sans Arabic",
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
    """(الفاقد الحالي للفترة، ثم الفاقد والمسترجع والصافي لكل الفترات = «الكل» في شاشة الخسائر)"""
    s, t = app.get_box_loss_summary(cat, month=month), app.get_box_loss_summary(cat, month=app.LOSSES_ALL)
    return (s["current"], t["loss"], t["recovered"], t["net"])


def period_summary(app, cat, month, to_month=None):
    """البطاقة كما تظهر عند اختيار فترة أو نطاق «من/إلى» (أو «الكل»): كل الأقسام الأربعة لها"""
    s = app.get_box_loss_summary(cat, month=month, to_month=to_month)
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
    ("مسترجع الأشجار", "قبض كاستنج", 1.0, "1"),                   # مسترجع الأشجار: قبض من فاقد الصف
    ("مسترجع الفاقد", "صرف كاستنج", 10.0, ""), ("مسترجع الفاقد", "قبض كاستنج", 8.0, "")])
assert not journal_legs(a), "لا قيد إقفال يُنشأ من الترحيل"
assert not any(i["الاسم"] == CAST_REC for i in m8)
print("✔ «مسترجع» ومسترجع الأشجار: صرفٌ وقبضٌ للكاستنج نفسه — لا شيء لحساب «مسترجع كاستنج» ولا إقفال")

assert summary(a, CAST, M8) == (6.0, 0.0, 0.0, 0.0), summary(a, CAST, M8)
print("✔ الفاقد الحالي لفترة ٨ = صرف 100 + صرف مسترجع 10 − قبض 95 − مسترجع الأشجار 1 − قبض مسترجع 8 = 6")

sets = a.get_treasury_type_sets()
assert all(a.treasury_bucket(i, sets)[0] == "boxes" for i in m8)
treasury = round(sum(a.treasury_bucket(i, sets)[1] for i in m8), 2)
assert treasury == -6.0, treasury
print("✔ الخزينة: خرج 110 وعاد 104 = −6 = الفاقد الحالي (كلها حركات الكاستنج، لا «وارد»)")

# الجدول: «فاقد» يعرض كل العمليات، و«مسترجع» عملياته وحدها
a.current_display_month = M8
rows = a.collect_stage_ops_rows("صرف كاستنج", "قبض كاستنج", CAST_REC)
assert [g["op"] for _r, _n, g in rows] == ["فاقد", "مسترجع", "مسترجع"]
assert (rows[0][2]["مدين"], rows[0][2]["دائن"], rows[0][2]["مسترجع"]) == (100.0, 95.0, 1.0)
assert sorted((g["مدين"], g["دائن"]) for _r, _n, g in rows[1:]) == [(0.0, 8.0), (10.0, 0.0)]
tot = W()
a.render_stage_ops_table(None, "صرف كاستنج", "قبض كاستنج", with_trees=True, recover_name=CAST_REC,
                         op_filter="فاقد", section=CAST, totals_label=tot)
data = [r for r in a._tree.rows if r["الصف"] != "إجمالي الشهر"]
assert [r["العملية"] for r in data] == ["فاقد", "مسترجع", "مسترجع"], [r["العملية"] for r in data]
assert "صرف: 110.00" in tot.v and "قبض: 103.00" in tot.v and "مسترجع الأشجار: 1.00" in tot.v, tot.v
assert "الخياس: 6.00" in tot.v and "الصافي" not in tot.v, tot.v
assert [r["الخياس"] for r in data] == ["4.00", "10.00", "-8.00"], [r["الخياس"] for r in data]
a.render_stage_ops_table(None, "صرف كاستنج", "قبض كاستنج", with_trees=True, recover_name=CAST_REC,
                         op_filter="مسترجع", section=CAST, totals_label=tot)
data = [r for r in a._tree.rows if r["الصف"] != "إجمالي الشهر"]
assert [r["العملية"] for r in data] == ["مسترجع", "مسترجع"] and all(r["الصف"] == "-" for r in data)
assert "صرف: 10.00" in tot.v and "قبض: 8.00" in tot.v and "الخياس: 2.00" in tot.v, tot.v
print("✔ الجدول: «فاقد» يعرض كل العمليات — قبض المسترجع تحت القبض، ومسترجع الأشجار يُخصم من خياس صفه")
print("✔ و«مسترجع» يعرض عملياته وحدها")

# ═══ ٣) الإقفال بالزر وحده ← حساب «فاقد الكاستنج» ═══
a.current_display_month = M9
before = len(a.invoices)
a.close_khayas_box(CAST, month=M8)
legs = journal_legs(a)
assert len(a.invoices) == before + 2 and len(legs) == 2
dr = next(x for x in legs if x["النوع"] == "قيد يومي مدين")
cr = next(x for x in legs if x["النوع"] == "قيد يومي دائن")
assert (dr["الاسم"], cr["الاسم"], dr["الوزن"]) == (CAST_LOSS, CAST_BOX, 6.0)
assert dr["period"] == cr["period"] == M8 and dr["التاريخ"] == "2026-08-31 23:59:00"
assert dr["set_number"] == cr["set_number"] and a.journal_partner(dr) is cr
assert summary(a, CAST, M8) == (0.0, 6.0, 0.0, 6.0), summary(a, CAST, M8)
print("✔ زر الإقفال: مدين «فاقد الكاستنج» 6 / دائن «الكاستنج» 6، بفترة ٨ وآخر يوم فيها")
print("✔ بعده: الفاقد الحالي 0 | فاقد الكاستنج 6 | المسترجع 0 | الصافي 6")

before = len(a.invoices)
a.close_khayas_box(CAST, month=M8)
assert len(a.invoices) == before and msgs[-1] == "لا يوجد خياس"
print("✔ لا إقفال مرتين لفترة واحدة")

# ═══ ٤) كل فترة مستقلة، والوارد إلى حساب المسترجع لا يُقفل شيئاً ═══
cast_loss(a, M9, "1", sarf="50", qabd="48")
a.current_display_month = M9
assert summary(a, CAST, M9) == (2.0, 6.0, 0.0, 6.0), summary(a, CAST, M9)
assert a.get_current_unclosed_khayas(CAST, month=M8) == 0.0
print("✔ فترة ٩ تبدأ بفاقدها وحدها (2)، وفاقد الكاستنج يبقى 6 من فترة ٨")

legs_before = len(journal_legs(a))
inbound(a, M9, 3, CAST_REC, supplier="المصنع", note="بودرة")
rec = a.invoices[a.invoice_counter]
assert (rec["الاسم"], rec["النوع"], rec["الوزن"], rec["البيان"]) == (CAST_REC, "وارد ذهب (عيار 18)", 3.0, "بودرة — من المصنع")
assert len(journal_legs(a)) == legs_before, "الوارد إلى المسترجع لا يُنشئ قيد إقفال"
assert summary(a, CAST, M9) == (2.0, 6.0, 3.0, 3.0), summary(a, CAST, M9)
confirm = texts[len(msgs) - 1 - msgs[::-1].index("تأكيد الترحيل")]
assert f"في حساب «{CAST_REC}»" in confirm and "لا يُقفل أي فاقد" in confirm, confirm
print("✔ الوارد «إلى حساب مسترجع كاستنج» (شاشة الوارد): لحساب المسترجع (3) — الفاقد الحالي باقٍ 2 بلا إقفال")
assert a.treasury_bucket(rec, a.get_treasury_type_sets()) == ("inbound", 3.0)
print("✔ ويُحتسب «وارداً» دخلنا: في لوحة الوارد بالرئيسية والتقرير الشهري (لا يُنقص الخياس)")

# اسم الصندوق في خانة المورد (الطريقة القديمة) يُسجَّل مسترجعاً أيضاً — بلا إقفال
inbound(a, M9, 1, a.INBOUND_DEFAULT_ACCOUNT, supplier=CAST_BOX, voucher="V2")
assert a.invoices[a.invoice_counter]["الاسم"] == CAST_REC and len(journal_legs(a)) == legs_before
assert summary(a, CAST, M9) == (2.0, 6.0, 4.0, 2.0), summary(a, CAST, M9)
print("✔ كتابة اسم المرحلة في خانة المورد تُسجَّل في مسترجعها — ولا إقفال تلقائي إطلاقاً")

a.close_khayas_box(CAST, month=M9)
assert summary(a, CAST, M9) == (0.0, 8.0, 4.0, 4.0), summary(a, CAST, M9)
print("✔ إقفال فترة ٩ بالزر: فاقد الكاستنج يتراكم 6 + 2 = 8، والصافي 8 − 4 = 4")

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
assert summary(a, CAST, M9) == (0.0, 28.0, 8.0, 20.0), summary(a, CAST, M9)
print("✔ رصيد افتتاحي بقيد يومي: مدين «فاقد الكاستنج» 20 ← الفاقد 28، ودائن «مسترجع كاستنج» 4 ← المسترجع 8")

journal(a, "فاقد صب داخلي", "رصيد افتتاحي", 30, M9)
assert summary(a, "صب داخلي", M9) == (0.0, 30.0, 0.0, 30.0)
print("✔ مرحلة بلا أي حركة: رصيدها الافتتاحي في «فاقد صب داخلي» يظهر في شاشة الخسائر (30)")

# قيد بين المرحلة وحساب آخر (غير الفاقد) تسوية لفاقدها الحالي لا إقفال
journal(a, "حساب الخزينة", CAST_BOX, 2, M9)
assert summary(a, CAST, M9) == (-2.0, 28.0, 8.0, 20.0), summary(a, CAST, M9)
print("✔ قيد بين المرحلة والخزينة يسوّي فاقدها الحالي ولا يُحسب إقفالاً في «فاقد الكاستنج»")
closings = sorted(e["amount"] for e in a.get_box_closing_entries(CAST))
assert closings == [2.0, 6.0], closings
print("✔ «تراجع عن الإقفال» يعرض الإقفالين وحدهما (6 و2) — لا قيد الخزينة ولا الرصيد الافتتاحي")
a.invoices[a.invoice_counter]["settled_status"] = a.invoices[a.invoice_counter - 1]["settled_status"] = "MEMO"
a._inv_version = getattr(a, "_inv_version", 0) + 1

# ═══ ٦) الإقفالات القديمة على «حساب الخسائر» تُحسب في فاقد المرحلة ═══
add(a, "كاستنج", "صرف كاستنج", 5.0, M7)
ref = f"JE-{a.invoice_counter + 1}"
add(a, LOSSES, "قيد يومي مدين", 5.0, M7, "إقفال خياس", ref=ref)
add(a, CAST_BOX, "قيد يومي دائن", 5.0, M7, "إقفال خياس", ref=ref)
assert a.get_current_unclosed_khayas(CAST, month=M7) == 0.0
assert summary(a, CAST, M9) == (0.0, 33.0, 8.0, 25.0), summary(a, CAST, M9)
assert sorted(e["amount"] for e in a.get_box_closing_entries(CAST)) == [2.0, 5.0, 6.0]
print("✔ إقفال سابق لإنشاء حسابات الفاقد (على «حساب الخسائر») يُحسب في «فاقد الكاستنج» (33) ويمكن التراجع عنه")

# ═══ ٧) كشوف الحسابات تطابق شاشة الخسائر ═══
rows = a.get_account_ledger_rows(CAST_LOSS, "", "")
assert balance(rows, True) == a.get_box_loss_total(CAST) == 33.0, balance(rows, True)
assert any(r["الاسم"] == CAST_BOX and r["period"] == M7 for r in rows), "الإقفال القديم يظهر في كشف الفاقد"
rows9 = a.get_account_ledger_rows(CAST_LOSS, M9, M9)
assert rows9[0].get("is_opening") and rows9[0]["مدين"] == 11.0, rows9[0]      # 6 (فترة ٨) + 5 (فترة ٧)
assert balance(rows9, True) == 33.0
print("✔ كشف «فاقد الكاستنج» = 33 (مع الإقفال القديم)، ورصيد أول مدة فترة ٩ = إقفالات ما قبلها (11)")

rows = a.get_account_ledger_rows(CAST_REC, "", "")
assert balance(rows, False) == a.get_box_recovered_total(CAST) == 8.0, balance(rows, False)
print("✔ كشف «مسترجع كاستنج» = 8 (وارد شاشة الوارد والرصيد الافتتاحي فقط) = قسم المسترجع في شاشة الخسائر")

rows = a.get_account_ledger_rows(LOSSES, "", "")
total_losses = round(sum(a.get_box_loss_total(c) for c in a.get_khayas_box_categories()), 2)
assert balance(rows, True) == total_losses == 63.0, (balance(rows, True), total_losses)
print("✔ «حساب الخسائر» = إجمالي فاقد كل المراحل (33 + 30 = 63) في كشفه")

rows = a.get_account_ledger_rows(CAST_BOX, M8, M8)
assert any(r["البيان"] == "غبار الفرن" and r["مدين"] == 10.0 for r in rows)
assert any(r["البيان"] == "قبض مسترجع" and r["دائن"] == 8.0 for r in rows)
assert any(r["البيان"] == "مسترجع الأشجار" and r["دائن"] == 1.0 for r in rows)
assert balance(rows, False) == 0.0          # فترة ٨ مقفلة بالكامل
print("✔ كشف «الكاستنج» لفترة ٨ يعرض صرف المسترجع وقبضه ومسترجع الأشجار مع حركاته، ورصيده صفر بعد الإقفال")

# ═══ ٧ب) شاشة الخسائر: فترة تختارها أو «الكل» ═══
assert period_summary(a, CAST, M7) == (0.0, 5.0, 0.0, 5.0), period_summary(a, CAST, M7)
assert period_summary(a, CAST, M8) == (0.0, 6.0, 0.0, 6.0), period_summary(a, CAST, M8)
assert period_summary(a, CAST, M9) == (0.0, 22.0, 8.0, 14.0), period_summary(a, CAST, M9)
print("✔ اختيار فترة: أقسام البطاقة الأربعة لها وحدها — فترة ٧: فاقد 5 | فترة ٨: فاقد 6 | "
      "فترة ٩: فاقد 22 (إقفال 2 + افتتاحي 20) ومسترجع 8 وصافي 14")
assert period_summary(a, CAST, a.LOSSES_ALL) == (0.0, 33.0, 8.0, 25.0), period_summary(a, CAST, a.LOSSES_ALL)
by_period = [period_summary(a, CAST, m) for m in a.get_recorded_periods()]
assert round(sum(x[1] for x in by_period), 2) == 33.0 and round(sum(x[2] for x in by_period), 2) == 8.0
assert period_summary(a, CAST, a.LOSSES_ALL)[1] == a.get_box_loss_total(CAST) == balance(
    a.get_account_ledger_rows(CAST_LOSS, "", ""), True)
print("✔ «الكل»: فاقد 33 ومسترجع 8 وصافي 25 = مجموع الفترات = كشف «فاقد الكاستنج» كاملاً")

g = new_app()
cast_loss(g, M8, "1", sarf="100", qabd="94")
cast_loss(g, M9, "1", sarf="50", qabd="48")
g.current_display_month = M9
assert period_summary(g, CAST, M8)[0] == 6.0 and period_summary(g, CAST, M9)[0] == 2.0
assert period_summary(g, CAST, g.LOSSES_ALL) == (8.0, 0.0, 0.0, 0.0), period_summary(g, CAST, g.LOSSES_ALL)
print("✔ «الكل» للفاقد الحالي = غير المُقفل في كل الفترات (6 من فترة ٨ + 2 من فترة ٩ = 8)")

assert g.losses_period_options() == [M9, M8], g.losses_period_options()
g.combo_losses_from, g.combo_losses_to = W(M8), W(M8)
assert (g.selected_losses_range(), g.losses_close_period(), g.losses_statement_range()) == ((M8, M8), M8, (M8, M8))
g.combo_losses_from, g.combo_losses_to = W(M9), W(M8)             # «من» بعد «إلى» ← يُقلبان
assert (g.selected_losses_range(), g.losses_close_period(), g.losses_statement_range()) == ((M8, M9), M9, ("", ""))
assert g.range_scope_label(M8, M9) == f"أرقام كل الفترات ({M8} إلى {M9})"
g.reset_losses_period()
assert (g.combo_losses_from.v, g.combo_losses_to.v) == (M9, M9)
g.losses_show_all()
assert (g.combo_losses_from.v, g.combo_losses_to.v) == (M8, M9) and g.range_scope_label(M9, M9) == f"أرقام فترة {M9}"
print("✔ «من/إلى» قائمتان بالفترات المسجّلة (الأحدث أولاً) لا كتابة؛ «من» بعد «إلى» يُقلبان؛ «الكل» من أقدم فترة "
      "لأحدثها؛ «الفترة الحالية ↺» تعيدها")
print("✔ الكشف من البطاقة بالنطاق نفسه (و«الكل» بلا حدّ)؛ زر الإقفال يُقفل الفترة المختارة، ومع «الكل» الفترة الحالية")

# نطاق من فترة إلى فترة = مجموع فتراته، والنطاق كله = «الكل»
assert a.periods_in_range(M8, M7) == [M7, M8]
assert period_summary(a, CAST, M7, M8) == (0.0, 11.0, 0.0, 11.0), period_summary(a, CAST, M7, M8)
assert period_summary(a, CAST, M8, M9) == (0.0, 28.0, 8.0, 20.0), period_summary(a, CAST, M8, M9)
assert period_summary(a, CAST, M9, M7) == period_summary(a, CAST, M7, M9)
whole = a.get_recorded_periods()
assert period_summary(a, CAST, whole[-1], whole[0]) == period_summary(a, CAST, a.LOSSES_ALL)
a.combo_losses_from, a.combo_losses_to = W(M7), W(M8)
if not a.range_covers_all(M7, M8):
    assert a.losses_close_period() == M8 and a.losses_statement_range() == (M7, M8)
    assert a.range_scope_label(M7, M8) == f"أرقام الفترات من {M7} إلى {M8}"
print("✔ من فترة ٧ إلى ٨: فاقد 11 (5 + 6)، ومن ٨ إلى ٩: فاقد 28 ومسترجع 8 وصافي 20 — مجموع فتراته؛ والنطاق كله = «الكل»")

tab = seg("refresh_losses_tab")
assert "self.losses_period_options()" in tab and "self.selected_losses_range()" in tab and '"scope"' in tab
assert "month=from_m, to_month=to_m" in tab and "self.range_scope_label(from_m, to_m)" in tab
assert "self.losses_close_period()" in seg("refresh_losses_cards")
assert "لكل الفترات" not in seg("refresh_losses_cards")
build = seg("build_losses_tab")
assert "self.combo_losses_from = self.make_month_combo(" in build and "self.combo_losses_to = self.make_month_combo(" in build
assert "CTkEntry" not in build and "YYYY-MM" not in build and "self.losses_show_all" in build
assert 'state="readonly"' in seg("make_month_combo")
assert "self.selected_losses_range()" in seg("print_losses_screen")
print("✔ البطاقة تذكر نطاقها («أرقام فترة …» أو «من … إلى …» أو «كل الفترات»)، والطباعة بالنطاق نفسه — ولا خانة تاريخ تُكتب")

# الطباعة: تفصيل الفترات لكل صندوق
rows, total = a.losses_period_breakdown(CAST)
assert [(m, (sm["current"], sm["loss"], sm["recovered"], sm["net"])) for m, sm in rows] == [
    (M7, (0.0, 5.0, 0.0, 5.0)), (M8, (0.0, 6.0, 0.0, 6.0)), (M9, (0.0, 22.0, 8.0, 14.0))], rows
assert (total["current"], total["loss"], total["recovered"], total["net"]) == (0.0, 33.0, 8.0, 25.0)
for k in ("current", "loss", "recovered", "net"):
    assert round(sum(sm[k] for _m, sm in rows), 2) == total[k], k
rows_g, total_g = g.losses_period_breakdown(CAST)
assert [m for m, _ in rows_g] == [M8, M9] and total_g["current"] == 8.0
rows_e, total_e = a.losses_period_breakdown("التلميع")
assert rows_e == [] and all(v == 0.0 for v in total_e.values())
pr = seg("print_losses_screen")
assert "self._draw_losses_breakdown(c, y, box_defs, (from_m, to_m)" in pr
br = seg("_draw_losses_breakdown")
assert "self.losses_period_breakdown(cat, from_m, to_m)" in br and '"الإجمالي (كل الفترات)"' in br and "new_page(" in br
assert 'f"الإجمالي ({from_m} إلى {to_m})"' in br
assert "if total is not None:" in br and '"لا حركات في هذه الفترات"' in br
print("✔ الطباعة بـ«الكل»: لكل صندوق جدول بفتراته (الأقدم أولاً، بلا الفترات الخالية): الحالي والفاقد والمسترجع والصافي")
print("  وإجماليه = «الكل» = مجموع الفترات (الكاستنج: 5 + 6 + 22 = 33)، وصفحات جديدة عند الحاجة")

rng, rng_total = a.losses_period_breakdown(CAST, M7, M8)
assert [m for m, _ in rng] == [M7, M8] and (rng_total["loss"], rng_total["net"]) == (11.0, 11.0), rng_total
print("✔ الطباعة بنطاق (فترة ٧ إلى ٨): فتراته وحدها وإجماليها 11 — مطابق للبطاقة")

one, none_total = a.losses_period_breakdown(CAST, M8)
assert none_total is None and [(m, (sm["current"], sm["loss"], sm["recovered"], sm["net"])) for m, sm in one] == [
    (M8, (0.0, 6.0, 0.0, 6.0))], one
assert a.losses_period_breakdown(CAST, M8, M8) == (one, None)
assert a.losses_period_breakdown(CAST, a.LOSSES_ALL) == a.losses_period_breakdown(CAST)
print("✔ الطباعة بفترة مختارة: جدول كل صندوق بتلك الفترة وحدها (فترة ٨: فاقد 6) — بلا الفترات الأخرى ولا إجمالي")

# ═══ ٨) إلغاء «الإقفال التلقائي عند الوارد» في البيانات السابقة ═══
def legacy(app, month, sarf, qabd, recovered, remainder):
    """بيانات بالشكل الذي كان يسجّله الإصدار السابق: وارد مسترجع + قيد «مسترجع» يليه مباشرة"""
    add(app, "كاستنج", "صرف كاستنج", sarf, month)
    add(app, "كاستنج", "قبض كاستنج", qabd, month)
    dt = f"{month}-12 09:30:00"
    inv_id = add(app, CAST_REC, "وارد ذهب (عيار 18)", recovered, month, date=dt, ref=f"V-{month}")
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
        first = add(c, supplier, "وارد ذهب (عيار 18)", 2.0 if supplier == "المصنع" else 1.0, M8, date=dt,
                    ref=f"V-{day}")
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

# ═══ ٨ب) تصحيح «المسترجع» الذي سجّلته شاشة الكاستنج سابقاً باسم حساب المسترجع ═══
for admin in (False, True):
    m = new_app(admin=admin)
    add(m, "كاستنج", "صرف كاستنج", 50.0, M8, row="3")
    add(m, "كاستنج", "قبض كاستنج", 44.0, M8, row="3")
    tree_id = add(m, CAST_REC, "وارد ذهب (عيار 18)", 1.5, M8, "مسترجع الأشجار — غبار", row="3")
    op_rec = add(m, CAST_REC, "وارد ذهب (عيار 18)", 2.0, M8, "من الفرن")                # قبض «مسترجع»
    op_iss = add(m, CAST_REC, "صرف كاستنج", 0.5, M8)                                     # صرف «مسترجع»
    screen = add(m, CAST_REC, "وارد ذهب (عيار 18)", 3.0, M8, "من المصنع", ref="V-77")   # شاشة الوارد
    opening = add(m, CAST_REC, "وارد ذهب (عيار 18)", 4.0, M8, "قيد افتتاحي")
    m.invoices[opening]["trees_count"] = 1.0
    before = summary(m, CAST, M8)
    assert before == (6.5, 0.0, 10.5, -10.5), before          # الإصدار السابق: المسترجع كله للحساب
    assert m.migrate_casting_returns() == 3
    t, r, i = m.invoices[tree_id], m.invoices[op_rec], m.invoices[op_iss]
    assert (t["الاسم"], t["النوع"], t["row_number"]) == ("مسترجع الأشجار", "قبض كاستنج", "3")
    assert (r["الاسم"], r["النوع"]) == ("مسترجع الفاقد", "قبض كاستنج") and i["الاسم"] == "مسترجع الفاقد"
    assert m.invoices[screen]["الاسم"] == CAST_REC and m.invoices[screen]["النوع"] == "وارد ذهب (عيار 18)"
    assert m.invoices[opening]["الاسم"] == CAST_REC
    after = summary(m, CAST, M8)
    assert after == (3.0, 0.0, 7.0, -7.0), after              # 50 + 0.5 − 44 − 1.5 − 2 = 3؛ المسترجع 3 + 4
    m.current_display_month = M8
    rows = m.collect_stage_ops_rows("صرف كاستنج", "قبض كاستنج", CAST_REC)
    fa = next(g for _r, _n, g in rows if g["op"] == "فاقد")
    assert (fa["مدين"], fa["دائن"], fa["مسترجع"], fa["البيان"]) == (50.0, 44.0, 1.5, "غبار")
    assert sorted((g["مدين"], g["دائن"]) for _r, _n, g in rows if g["op"] == "مسترجع") == [(0.0, 2.0), (0.5, 0.0)]
    with sqlite3.connect(m.db_path) as conn:
        stored = conn.execute("SELECT name, op_type FROM invoices WHERE invoice_id = ?", (tree_id,)).fetchone()
    assert stored == (("مسترجع الأشجار", "قبض كاستنج") if not admin else (CAST_REC, "وارد ذهب (عيار 18)")), stored
    assert m.migrate_casting_returns() == 0
print("✔ ما سجّلته شاشة الكاستنج سابقاً باسم «مسترجع كاستنج» يُصحَّح تلقائياً: مسترجع الأشجار وقبض «مسترجع»")
print("  قبضٌ من الفاقد الحالي (6.5 ← 3)، وصرف «مسترجع» صرفٌ للكاستنج — يُعرف بغياب رقم الفاتورة")
print("✔ وما وصل من شاشة الوارد (برقم فاتورة) والقيد الافتتاحي يبقيان في حساب المسترجع كما هما")
print("✔ نسخة العميل تحفظ التصحيح في قاعدتها، والمدير في الذاكرة؛ وتكراره لا يغيّر شيئاً")

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

# ═══ ١١) «بوليش 1»: الليزر مثل الصرف يُضاف إلى الفاقد، ولا خانة اسم ═══
P1 = "التلميع/البف"


def polish1(app, month, row, sarf="", qabd="", laser="", note=""):
    app.current_display_month = month
    app.pbuff_date, app.pbuff_note, app.pbuff_row_num = W(f"{month}-16"), W(note), W(row)
    app.pbuff_sarf, app.pbuff_qabd, app.pbuff_laser = W(sarf), W(qabd), W(laser)
    app.submit_polish_buff_op()


f = new_app()
assert f.get_display_label(P1) == "بوليش 1"
# أسماء الحسابات ثابتة لا تتبع اسم العرض: الحركات القديمة تبقى على حساباتها
assert (f.get_box_account_name(P1), f.get_box_loss_account(P1), f.get_box_recovery_name(P1)) == \
       ("البوليش", "فاقد البوليش", "مسترجع البوليش")
assert (f.get_display_label("خياس الطقوم"), f.get_box_account_name("خياس الطقوم"), f.get_box_loss_account("خياس الطقوم"),
        f.get_box_recovery_name("خياس الطقوم")) == ("بوليش 2", "بوليش 2", "فاقد بوليش 2", "مسترجع بوليش 2")
print("✔ القسم يُعرض «بوليش 1»، وحساباته كما هي: «البوليش» و«فاقد البوليش» و«مسترجع البوليش»؛ "
      "و«خياس التلميع النهائي» صار «بوليش 2» وحساباته «بوليش 2» و«فاقد بوليش 2» و«مسترجع بوليش 2»")

polish1(f, M9, "41", sarf="20", qabd="18", laser="0.5", note="طقم")
got = sorted((i["الاسم"], i["النوع"], i["الوزن"], i["row_number"], i["البيان"]) for i in f.invoices.values())
assert got == sorted([(P1, "صرف تلميع بف", 20.0, "41", "طقم"), (P1, "قبض تلميع بف", 18.0, "41", "طقم"),
                      ("ليزر البوليش", "صرف تلميع بف", 0.5, "41", "ليزر البوليش — طقم")]), got
with sqlite3.connect(f.db_path) as conn:
    assert conn.execute("select count(*) from invoices where op_type = 'صرف تلميع بف'").fetchone()[0] == 2
print("✔ الليزر يُسجَّل صرفاً للقسم («صرف تلميع بف») على رقم الصف نفسه، باسمه ليظهر في عموده")

assert summary(f, P1, M9)[0] == 2.5, summary(f, P1, M9)
sets = f.get_treasury_type_sets()
p1 = list(f.invoices.values())
assert all(f.treasury_bucket(i, sets)[0] == "boxes" for i in p1)
assert round(sum(f.treasury_bucket(i, sets)[1] for i in p1), 2) == -2.5
print("✔ الفاقد الحالي = صرف 20 + ليزر 0.5 − قبض 18 = 2.5، والخزينة −2.5 (كالصرف تماماً)")

rows = f.collect_stage_ops_rows("صرف تلميع بف", "قبض تلميع بف")
assert len(rows) == 1 and rows[0][0] == "41", rows
g = rows[0][2]
assert (g["مدين"], g["دائن"], g["مسترجع"], g["البيان"]) == (20.0, 18.0, 0.5, "طقم"), g
f.render_stage_ops_table(None, "صرف تلميع بف", "قبض تلميع بف", section=P1, totals_label=W())
assert f._tree.cols == ("الصف", "صرف", "قبض", "الليزر", "الخياس", "البيان"), f._tree.cols
assert f._tree.rows[0] == {"الصف": "41", "صرف": "20.00", "قبض": "18.00", "الليزر": "0.50",
                           "الخياس": "2.50", "البيان": "طقم"}, f._tree.rows[0]
assert f._tree.rows[-1]["الليزر"] == "0.50" and f._tree.rows[-1]["الخياس"] == "2.50"
print("✔ الجدول: الصف | صرف | قبض | الليزر | الخياس | البيان — الليزر في صفه، والخياس بعد إضافته")

# الليزر وحده لصف؛ والصرف لصفٍّ فيه ليزر ليس تكراراً (الليزر لا يُعدّ صرف الصف)
polish1(f, M9, "42", laser="0.3")
polish1(f, M9, "42", sarf="6")
assert sorted((i["الاسم"], i["النوع"]) for i in f.invoices.values() if i["row_number"] == "42") == \
       [(P1, "صرف تلميع بف"), ("ليزر البوليش", "صرف تلميع بف")]
before = len(f.invoices)
polish1(f, M9, "41", laser="0.2")
assert len(f.invoices) == before and msgs[-1] == "عملية مكررة", msgs[-1]
polish1(f, M9, "41", sarf="1")
assert len(f.invoices) == before
polish1(f, M9, "43", sarf="5", laser="-1")
assert len(f.invoices) == before and msgs[-1] == "تنبيه"
print("✔ الليزر وحده مقبول؛ والصرف لصفٍّ فيه ليزر ليس تكراراً؛ والخانة المسجّلة لصفها لا تتكرر؛ والسالب مرفوض")

# ما سُجّل قبضاً في 1.46.0 يُصحَّح إلى صرف عند الفتح (في الذاكرة والقاعدة)، مرة واحدة
old = add(f, "ليزر البوليش", "قبض تلميع بف", 0.4, M9, row="44")
add(f, P1, "صرف تلميع بف", 10.0, M9, row="44")
assert summary(f, P1, M9)[0] == round(2.5 + 6.3 + 10 - 0.4, 2)
assert f.migrate_row_extras() == 1 and f.invoices[old]["النوع"] == "صرف تلميع بف"
with sqlite3.connect(f.db_path) as conn:
    assert conn.execute("select op_type from invoices where invoice_id = ?", (old,)).fetchone()[0] == "صرف تلميع بف"
assert f.migrate_row_extras() == 0
assert summary(f, P1, M9)[0] == round(2.5 + 6.3 + 10 + 0.4, 2)
assert "self.migrate_row_extras()" in seg("load_data_from_db")
print("✔ ليزر سُجّل قبضاً في الإصدار السابق يُصحَّح صرفاً عند الفتح (يُحفظ في القاعدة، وتكراره لا يغيّر شيئاً)")

# الكاستنج لم يتأثر: مسترجع الأشجار قبضٌ في عموده كما كان
assert f.stage_row_extra("قبض كاستنج", CAST_REC) == ("مسترجع الأشجار", "مسترجع الأشجار", -1)
assert f.stage_row_extra("قبض تلميع بف") == ("ليزر البوليش", "الليزر", 1)
assert f.stage_row_extra("قبض كاستنج") is None and f.stage_row_extra("قبض تلميع") is None
print("✔ الكاستنج كما هو (مسترجع الأشجار قبض)، والتلميع بلا حركة ثانية")

# التلميع: بلا خانة اسم — الحركات باسم القسم
t = new_app()
t.current_display_month = M9
t.polish_date, t.polish_note, t.polish_row_num = W(f"{M9}-03"), W(""), W("7")
t.polish_sarf, t.polish_qabd = W("9"), W("8.5")
t.submit_polish_op()
assert {i["الاسم"] for i in t.invoices.values()} == {"التلميع"} and len(t.invoices) == 2
for ui in ("build_polish_ui", "build_polish_buff_ui"):
    assert "name_values" not in seg(ui), ui
assert '("laser", "الليزر")' in seg("build_polish_buff_ui")
for fn in ("submit_polish_op", "submit_polish_buff_op"):
    assert "_name.get()" not in seg(fn), fn
print("✔ التلميع وبوليش 1 بلا خانة اسم: الحركات باسم القسم نفسه")

# ═══ ١٢) «خياس التلميع النهائي» ← «بوليش 2»: الحركات القديمة تنتقل لحساباتها الجديدة ═══
B2 = "خياس الطقوم"


def polish2_data(app):
    """بيانات بأسماء الإصدار 1.61: خياس مبيعات، إقفال، رصيد افتتاحي، مسترجع، وقيد على مسترجعه"""
    app.current_display_month = M9
    ids = {"sale": add(app, "عميل أ", "خياس طقوم", 4.0, M8, "خياس التلميع النهائي — طلبية"),
           "sale_plain": add(app, "عميل ب", "خياس طقوم", 1.0, M8, "خياس التلميع النهائي"),
           "polish_memo": add(app, "عميل أ", "خياس طقوم", 0.7, M8, "خياس بوليش — طلبية")}
    ref = f"JE-{app.invoice_counter + 1}"
    ids["close_loss"] = add(app, "فاقد خياس التلميع النهائي", "قيد يومي مدين", 5.0, M8, "إقفال فاقد فترة " + M8, ref=ref)
    ids["close_box"] = add(app, "خياس الطقوم", "قيد يومي دائن", 5.0, M8, "إقفال فاقد فترة " + M8, ref=ref)
    ref = f"JE-{app.invoice_counter + 1}"
    add(app, "فاقد خياس التلميع النهائي", "قيد يومي مدين", 3.0, M9, ref=ref)
    add(app, "رصيد افتتاحي", "قيد يومي دائن", 3.0, M9, ref=ref)
    ids["rec"] = add(app, "مسترجع خياس الطقوم", "وارد ذهب (عيار 18)", 1.5, M9, ref="V-9")
    ids["other"] = add(app, "عميل ج", "مبيعات ذهب", 9.0, M9, "خياس التلميع النهائي — اسم في بيان مبيعات")
    return ids


q = new_app()
ids = polish2_data(q)
# قبل النقل: الحركات بأسمائها القديمة لا تصل لحسابات «بوليش 2»
assert q.get_box_loss_total(B2) == 0.0 and q.get_box_recovered_total(B2) == 0.0
assert q.migrate_polish2_names() == 6        # خياسا مبيعات + إقفال (طرفان) + افتتاحي + مسترجع
names = {k: (q.invoices[i]["الاسم"], q.invoices[i]["البيان"]) for k, i in ids.items()}
assert names["sale"] == ("عميل أ", "خياس بوليش 2 — طلبية") and names["sale_plain"] == ("عميل ب", "خياس بوليش 2")
assert names["polish_memo"] == ("عميل أ", "خياس بوليش — طلبية")              # خياس البوليش (بوليش 1) لا يُمسّ
assert names["close_loss"][0] == "فاقد بوليش 2" and names["close_box"][0] == "بوليش 2"
assert names["rec"][0] == "مسترجع بوليش 2"
assert names["other"] == ("عميل ج", "خياس التلميع النهائي — اسم في بيان مبيعات")  # ليست حركة خياس
assert summary(q, B2, M9)[1:] == (8.0, 1.5, 6.5), summary(q, B2, M9)
assert period_summary(q, B2, M8)[1] == 5.0 and period_summary(q, B2, M9)[1:] == (3.0, 1.5, 1.5)
print("✔ النقل عند الفتح: «خياس الطقوم» ← «بوليش 2»، «فاقد خياس التلميع النهائي» ← «فاقد بوليش 2»، "
      "«مسترجع خياس الطقوم» ← «مسترجع بوليش 2»")
print("  فيعود الإقفال (5) والافتتاحي (3) والمسترجع (1.5) لحسابات بوليش 2: فاقد 8، مسترجع 1.5، صافي 6.5")
print("✔ بيان خياس المبيعات «خياس التلميع النهائي — طلبية» ← «خياس بوليش 2 — طلبية»؛ وخياس البوليش وبيان المبيعات كما هما")

with sqlite3.connect(q.db_path) as conn:
    stored = dict(conn.execute("select invoice_id, name || '|' || note from invoices").fetchall())
assert stored[ids["close_box"]] == "بوليش 2|إقفال فاقد فترة " + M8 and stored[ids["rec"]].startswith("مسترجع بوليش 2|")
assert stored[ids["sale"]] == "عميل أ|خياس بوليش 2 — طلبية"
assert not any("خياس الطقوم" in v or "فاقد خياس التلميع" in v for v in stored.values())
assert q.migrate_polish2_names() == 0
print("✔ نسخة العميل تحفظ النقل في قاعدتها (فيُرفع للسحابة)، وتكراره لا يغيّر شيئاً")

r = new_app(admin=True)
ids_r = polish2_data(r)
with sqlite3.connect(r.db_path) as conn:
    before_db = conn.execute("select name, note from invoices order by invoice_id").fetchall()
assert r.migrate_polish2_names() == 6 and r.invoices[ids_r["close_box"]]["الاسم"] == "بوليش 2"
with sqlite3.connect(r.db_path) as conn:
    assert conn.execute("select name, note from invoices order by invoice_id").fetchall() == before_db
assert summary(r, B2, M9)[1:] == summary(q, B2, M9)[1:]
ns["IS_ADMIN_BUILD"] = False
print("✔ نسخة المدير تنقل في الذاكرة وحدها (مرآته لا تُكتب) — فيرى أرقام العميل نفسها")

load = seg("load_data_from_db")
assert load.index("self.migrate_polish2_names()") < load.index("self.neutralize_auto_recovery_closings()")
assert 'BOX_DISPLAY_OVERRIDES = {"خياس الطقوم": "بوليش 2"}' in src and "خياس التلميع النهائي" not in seg("get_box_account_name")
print("✔ النقل أول خطوات الفتح (قبل ما يتعرّف على الحسابات بأسمائها)")

shutil.rmtree(TMP, ignore_errors=True)
print("\n✅ نموذج الفاقد والمسترجع سليم")
