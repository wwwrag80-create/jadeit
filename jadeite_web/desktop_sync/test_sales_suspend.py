# -*- coding: utf-8 -*-
"""
اختبار شاشة المبيعات — يشغّل الدوال الحقيقية من البرنامج (والحفظ الفعلي في SQLite مؤقتة):

  • «البيان» بعد الاسم: يُحفظ مع كل حركة من حركات الفاتورة بعد دورها، ويظهر في
    «العمليات» ويعود عند تعديل الفاتورة المرحّلة.
  • «تعليق الفاتورة»: تُحفظ الفاتورة كما هي (رأسها وسطورها وما كُتب ولم يُضف) في
    «المعلقات» بلا أي حركة محاسبية؛ «فتح» يعيدها كما كانت؛ وترحيلها يُثبتها في
    «العمليات» ويحذفها من «المعلقات».
  • Enter والأسهم في كل الخانات (ومنها نافذة تعديل الفاتورة المرحّلة).
  • أعمدة الجداول تملأ عرض الجدول تماماً على أي شاشة.
"""
import ast, datetime, io, json, os, shutil, sqlite3, sys, tempfile, textwrap

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


def module_func(name):
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


seg = method_src
M9 = "2026-09"

METHODS = [
    # البيان والترحيل والعمليات
    "sale_bayan", "sale_note_of", "post_sale_rows", "get_sale_invoice_groups", "get_sale_invoice_records",
    "sale_records_to_rows", "commit_sale_invoice", "save_invoice_to_db", "_undo_note_row", "invoice_from_row", "mark_backup_dirty",
    "inv_period", "inv_in_period", "invoices_by_period", "period_invoices",
    # المعلقات
    "list_suspended_sales", "get_suspended_sale", "save_suspended_sale", "delete_suspended_sale",
    "suspended_totals", "collect_sale_form", "fill_sale_form", "clear_sale_form", "set_current_suspended",
    "suspend_sale_invoice", "get_selected_suspended_id", "open_suspended_sale",
    "delete_selected_suspended_sale", "update_suspended_count",
    # التنقل وتوزيع الأعمدة
    "bind_enter_navigation", "bind_arrow_navigation", "plan_column_widths",
    # فتح المسودة يُبقي خياس المركب المحفوظ حتى يتغيّر رقم التشغيل (ويُخفي سطر المصدر)
    "normalize_set_number", "show_assembler_source",
    # تاريخ الترحيل بصيغة واحدة (والأرقام الهندية تُحوَّل)
    "read_entry_date",
    # تذاكر أرقام التشغيل مع الفاتورة (الدفعة ١٧)
    "sale_tickets_with_invoice",
    # ترقيم الفواتير تلقائياً (الدفعة ٣٠): الفاتورة الجديدة بعد التعليق أو الترحيل تأخذ الرقم التالي
    "split_invoice_number", "sale_invoice_start", "used_sale_invoice_numbers", "next_sale_invoice_number",
    "fill_next_sale_invoice_number", "set_sale_invoice_start",
]
ATTRS = ["SALE_TYPES", "SALE_NOTE_SEP", "POLISH2_SALE_BAYAN", "SALE_NO_START_KEY", "SUSPENDED_TABLE_SQL", "SALE_DRAFT_FIELDS", "COMPACT_HEADERS",
         "SHRINKABLE_COLUMNS", "_SET_DIGITS", "_DATE_DIGITS"]

EXTRA = '''
def check_edit_permission(self): return True
def recalculate_all(self): self.recalcs += 1
def register_operation_period(self, d): pass
def refresh_pending_sales_table(self): self.pending_refreshes += 1
def refresh_sales_table(self): pass
def refresh_sales_ops_table(self): pass
def refresh_suspended_sales_table(self): self.suspended_refreshes += 1
def preview_invoice_groups(self, groups): self.previews.append(groups)
def switch_sales_subtab(self, key): self.current_sales_subtab = key
def get_smart_default_date(self): return "2026-09-01"
def get_supplier_name_values_no_mustarja(self): return ["المصنع", "مورد 1", "مورد 2"]
def after(self, ms, fn=None): pass
def remember_discount_pct(self): pass
def get_setting(self, key, default=None): return getattr(self, "_settings", {}).get(key, default)
def set_setting(self, key, value): self.__dict__.setdefault("_settings", {})[key] = str(value)
'''

msgs = []


class FakeBox:
    answers = {}

    @staticmethod
    def askyesno(title, *a, **k):
        msgs.append(title)
        return FakeBox.answers.get(title, title not in ("معاينة الطباعة",))

    @staticmethod
    def showinfo(title, *a, **k):
        msgs.append(title)

    showwarning = showerror = showinfo


class W:
    """خانة إدخال بديلة (Entry/ComboBox/Label/Button) تسجّل ربط المفاتيح"""
    focused = None

    def __init__(self, v=""):
        self.v, self.binds, self.selected = v, {}, False

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

    def cget(self, key):
        return self.v

    def focus_set(self):
        W.focused = self

    def select_range(self, *a):
        self.selected = True

    def bind(self, seq, fn=None, add=None):
        self.binds.setdefault(seq, []).append(fn)

    def press(self, seq):
        out = None
        for fn in self.binds.get(seq, []):
            out = fn(None)
        return out


class FakeTree:
    def __init__(self):
        self.sel = ()

    def selection(self):
        return self.sel


errors = []
ns = {"messagebox": FakeBox, "datetime": datetime, "sqlite3": sqlite3, "json": json, "re": __import__("re"),
      "MEMO_STATUS": module_value("MEMO_STATUS"), "SALE_READ_STATUSES": module_value("COUNTED_STATUSES") + (module_value("MEMO_STATUS"),),
      "KHAYAS_MARK_NET": module_value("KHAYAS_MARK_NET"), "KHAYAS_MARK_POLISH": module_value("KHAYAS_MARK_POLISH"),
      "KHAYAS_MARK_ASSEMBLER": module_value("KHAYAS_MARK_ASSEMBLER"),
      "KHAYAS_MARK_FINAL": module_value("KHAYAS_MARK_FINAL"), "IS_ADMIN_BUILD": False,
      "log_cloud_error": lambda *a, **k: errors.append(a), "load_ui_prefs": lambda: {}}
exec(module_func("sale_net_weight"), ns)
body = "\n".join(textwrap.indent(attr_src(a), "    ") for a in ATTRS)
body += "\n" + "\n".join(textwrap.indent(method_src(m), "    ") for m in METHODS)
exec("class App:\n" + body + "\n" + textwrap.indent(EXTRA, "    "), ns)
App = ns["App"]

TMP = tempfile.mkdtemp(prefix="sales_suspend_")
SCHEMA = """CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
            weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
            trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '',
            manual_no TEXT DEFAULT '', period TEXT DEFAULT '')"""
FORM = ("sale_date", "sale_invoice_num", "sale_name", "sale_note", "sale_discount_pct", "sale_set_number",
        "sale_gold", "sale_gems", "sale_stones", "sale_diamond", "sale_stones_discount", "sale_khayas",
        "sale_khayas_polish", "sale_khayas_assembler", "lbl_sales_status", "lbl_suspended_open")


def new_app(with_table=True):
    app = App()
    app.current_display_month = M9
    app.invoice_counter = 1000
    app.invoices = {}
    app.recalcs = app.pending_refreshes = app.suspended_refreshes = 0
    app.previews = []
    app.pending_sale_rows = []
    app.current_suspended_id = None
    app.current_sales_subtab = "المبيعات"
    app.sales_subtab_buttons = {"المعلقات": W("⏸️ المعلقات")}
    app.suspended_tree, app.suspended_map = FakeTree(), {}
    for f in FORM:
        setattr(app, f, W())
    app.sale_date.v, app.sale_name.v, app.sale_discount_pct.v = "2026-09-20", "المصنع", "30%"
    app.db_path = os.path.join(TMP, f"db{len(os.listdir(TMP))}.sqlite")
    with sqlite3.connect(app.db_path) as conn:
        conn.execute(SCHEMA)
        if with_table:
            conn.execute(App.SUSPENDED_TABLE_SQL)
    return app


def row(set_no, gold=0.0, gems=0.0, stones=0.0, disc=0.0, diamond=0.0, khayas=0.0, polish=0.0, asm=0.0, n="1"):
    return {"row_number": n, "set_number": set_no, "ذهب": gold, "فصوص": gems, "أحجار": stones,
            "أحجار بعد الخصم": disc, "الماس": diamond, "خياس": khayas, "خياس البوليش": polish,
            "خياس المركب": asm}


def db_count(app, sql, *args):
    with sqlite3.connect(app.db_path) as conn:
        return conn.execute(sql, args).fetchone()[0]


# ═══ ١) البيان مع الفاتورة المرحّلة ═══
a = new_app()
assert a.sale_bayan("مبيعات", "طلبية العيد") == "مبيعات — طلبية العيد"
assert a.sale_bayan("مبيعات", "  ") == "مبيعات" and a.sale_note_of("مبيعات") == ""
assert a.sale_note_of("خياس بوليش 2 — طلبية — العيد") == "طلبية — العيد"
assert a.sale_note_of("خياس التلميع النهائي — طلبية — العيد") == "طلبية — العيد"   # بيان قديم قبل نقله
a.post_sale_rows([row("S1", gold=10, gems=1, stones=2, disc=0.6, khayas=0.5, polish=0.2)],
                 "مورد 1", "2026-09-20 10:00:00", "F-1", "طلبية العيد")
notes = sorted(i["البيان"] for i in a.invoices.values())
assert notes == sorted(["مبيعات — طلبية العيد", "مبيعات — طلبية العيد", "مبيعات — طلبية العيد",
                        "خياس بوليش — طلبية العيد", "صافي الطقم — طلبية العيد",
                        "خياس بوليش 2 — طلبية العيد"]), notes
assert db_count(a, "select count(*) from invoices where note like '% — طلبية العيد'") == len(notes)
print("✔ البيان يُحفظ مع كل حركة من حركات الفاتورة بعد دورها («مبيعات — طلبية العيد»)")

a.post_sale_rows([row("S2", gold=4)], "مورد 2", "2026-09-21 10:00:00", "F-2")
assert {i["البيان"] for i in a.invoices.values() if i["رقم الفاتورة اليدوي"] == "F-2"} == {"مبيعات"}
g = {x["manual_no"]: x for x in a.get_sale_invoice_groups(M9)}
assert g["F-1"]["البيان"] == "طلبية العيد" and g["F-2"]["البيان"] == "", g
print("✔ بلا بيان تبقى الحركات كما كانت («مبيعات»)؛ و«العمليات» تعرض بيان كل فاتورة")

rows_back = a.sale_records_to_rows(a.get_sale_invoice_records(("F-1", "2026-09-20 10:00:00", "مورد 1")))
assert rows_back[0]["ذهب"] == 10 and rows_back[0]["خياس"] == 0.5 and rows_back[0]["خياس البوليش"] == 0.2
print("✔ إعادة بناء سطور الفاتورة للتعديل لا تتأثر بالبيان")

ops = seg("refresh_sales_ops_table")
assert '"الاسم", "البيان", "الذهب"' in ops and 'g.get("البيان", "")' in ops
assert 'self.fit_columns_to_content(tree, "sales_ops"' in ops
editor = seg("open_sale_invoice_editor")
assert "self.sale_note_of(" in editor and "ent_note.get().strip()" in editor
# البيان يُمرَّر، والفاتورة تبقى في فترتها الأصلية عند الحفظ
assert "self.post_sale_rows(edit_rows, new_name, new_full_dt, new_manual, ent_note.get().strip()," in editor
assert "period=old_period" in editor
print("✔ جدول العمليات: عمود البيان بعد الاسم؛ ونافذة التعديل تعرض البيان وتحفظه")

# ═══ ٢) تعليق الفاتورة: بلا أي حركة محاسبية ═══
b = new_app()
b.sale_invoice_num.v, b.sale_name.v, b.sale_note.v = "S-501", "مورد 1", "طلبية العيد"
b.pending_sale_rows = [row("7001", gold=10, gems=1, stones=2, disc=0.6, khayas=0.5, n="1"),
                       row("7002", gold=8, diamond=0.4, khayas=0.3, n="2")]
b.sale_set_number.v, b.sale_gold.v = "7003", "5"              # سطر كُتب ولم يُضف بعد
rid = b.suspend_sale_invoice()
assert rid and b.invoices == {} and db_count(b, "select count(*) from invoices") == 0
assert b.pending_sale_rows == [] and b.sale_invoice_num.v == "" and b.sale_note.v == ""
assert b.sale_name.v == "المصنع" and b.sale_set_number.v == "" and b.sale_gold.v == ""
assert b.sale_date.v == "2026-09-20" and b.sale_discount_pct.v == "30%"
assert b.current_suspended_id is None
assert b.sales_subtab_buttons["المعلقات"].v == "⏸️ المعلقات (1)"
print("✔ «تعليق الفاتورة»: لا حركة ولا أثر على أي رصيد، وتُفرَّغ الشاشة لفاتورة جديدة (التاريخ والنسبة كما هما)")

# مع الترقيم التلقائي: المعلّقة تحجز رقمها، والفاتورة الجديدة تأخذ التالي
n = new_app()
assert n.set_sale_invoice_start("S-0600") and n.fill_next_sale_invoice_number() == "S-0600"
n.pending_sale_rows = [row("7101", gold=3, n="1")]
assert n.suspend_sale_invoice() and n.sale_invoice_num.v == "S-0601"
print("✔ مع الترقيم التلقائي: المعلّقة تحجز رقمها (S-0600)، والفاتورة الجديدة في الشاشة S-0601")

recs = b.list_suspended_sales()
assert len(recs) == 1
r = recs[0]
assert (r["manual_no"], r["name"], r["note"], r["date"], r["discount_pct"]) == \
       ("S-501", "مورد 1", "طلبية العيد", "2026-09-20", "30%")
assert len(r["rows"]) == 2 and r["draft"] == {"set_number": "7003", "ذهب": "5"}, r["draft"]
t = b.suspended_totals(r)
assert t == {"ذهب": 18.0, "فصوص": 1.0, "أحجار بعد الخصم": 0.6, "الماس": 0.4, "خياس": 0.8}, t
print("✔ في «المعلقات» بكل بياناتها: الرقم والاسم والبيان والتاريخ والنسبة والسطور وما كُتب ولم يُضف، وإجمالياتها")

before = len(msgs)
assert b.suspend_sale_invoice() is None and msgs[before:] == ["لا شيء لتعليقه"]
assert len(b.list_suspended_sales()) == 1
print("✔ فاتورة فارغة لا تُعلَّق (تنبيه واضح)")

# فاتورة ثانية تُعلَّق، والأحدث أولاً
b.sale_invoice_num.v, b.sale_name.v = "S-502", "مورد 2"
b.pending_sale_rows = [row("7100", gold=3)]
rid2 = b.suspend_sale_invoice()
assert [x["manual_no"] for x in b.list_suspended_sales()] in (["S-502", "S-501"], ["S-501", "S-502"])
assert b.sales_subtab_buttons["المعلقات"].v == "⏸️ المعلقات (2)"

# ═══ ٣) الفتح: تعود كما عُلّقت تماماً ═══
b.open_suspended_sale(rid)
assert b.current_sales_subtab == "المبيعات" and b.current_suspended_id == rid
assert (b.sale_invoice_num.v, b.sale_name.v, b.sale_note.v, b.sale_date.v) == \
       ("S-501", "مورد 1", "طلبية العيد", "2026-09-20")
assert [x["set_number"] for x in b.pending_sale_rows] == ["7001", "7002"]
assert (b.sale_set_number.v, b.sale_gold.v) == ("7003", "5")
assert "S-501" in b.lbl_suspended_open.v
print("✔ «فتح» يعيدها إلى قسم المبيعات ببياناتها كلها، ومعها ما كُتب ولم يُضف — تُستكمل من حيث توقفت")

# فتح غيرها والشاشة فيها فاتورة: تُعلَّق الحالية أولاً (تحديث المعلّقة نفسها لا نسخة جديدة)
b.pending_sale_rows.append(row("7003", gold=5, n="3"))
b.sale_set_number.v = b.sale_gold.v = ""
FakeBox.answers["فاتورة غير مرحّلة في الشاشة"] = False
b.open_suspended_sale(rid2)
assert b.current_suspended_id == rid and len(b.pending_sale_rows) == 3     # رفض ← لا شيء تغيّر
FakeBox.answers["فاتورة غير مرحّلة في الشاشة"] = True
b.open_suspended_sale(rid2)
assert b.current_suspended_id == rid2 and b.sale_invoice_num.v == "S-502"
again = b.get_suspended_sale(rid)
assert len(b.list_suspended_sales()) == 2 and len(again["rows"]) == 3 and again["draft"] == {}
print("✔ فتح فاتورة أخرى يعلّق ما في الشاشة أولاً (بموافقة) — تحديثاً للمعلّقة نفسها، فلا تضيع ولا تتكرر")

# ═══ ٤) ترحيلها: تنتقل إلى «العمليات» وتختفي من «المعلقات» ═══
b.open_suspended_sale(rid)
assert b.current_suspended_id == rid and b.sale_invoice_num.v == "S-501"
assert len(b.list_suspended_sales()) == 2                       # S-502 عُلّقت ثانيةً قبل فتح S-501
b.commit_sale_invoice()
left = b.list_suspended_sales()
assert [x["manual_no"] for x in left] == ["S-502"], left
assert b.current_suspended_id is None and b.lbl_suspended_open.v == ""
assert b.sales_subtab_buttons["المعلقات"].v == "⏸️ المعلقات (1)"
grp = next(x for x in b.get_sale_invoice_groups(M9) if x["manual_no"] == "S-501")
assert grp["البيان"] == "طلبية العيد" and grp["ذهب"] == 23.0 and len(grp["sets"]) == 3, grp
assert b.pending_sale_rows == [] and b.sale_note.v == "" and b.sale_invoice_num.v == ""
print("✔ ترحيل المعلّقة يُثبتها في «العمليات» (بالبيان وكل سطورها) ويحذفها من «المعلقات»")

# فاتورة عادية (لم تُعلَّق) لا تمسّ المعلقات
b.sale_invoice_num.v, b.sale_name.v = "S-600", "مورد 2"
b.pending_sale_rows = [row("7200", gold=2)]
b.commit_sale_invoice()
assert [x["manual_no"] for x in b.list_suspended_sales()] == ["S-502"]
print("✔ ترحيل فاتورة لم تُعلَّق لا يمسّ المعلقات")

# الحذف
b.suspended_map = {"I1": rid2}
b.suspended_tree.sel = ("I1",)
b.delete_selected_suspended_sale()
assert b.list_suspended_sales() == [] and b.sales_subtab_buttons["المعلقات"].v == "⏸️ المعلقات"
print("✔ حذف المعلّقة بتأكيد (لا أثر على الأرصدة لأنها لم تُرحَّل)")

# ═══ ٥) قاعدة قديمة بلا جدول المعلقات (مرآة المدير لجهاز لم يُحدَّث) ═══
c = new_app(with_table=False)
assert c.list_suspended_sales() == [] and c.get_suspended_sale(1) is None
c.pending_sale_rows = [row("1", gold=1)]
assert c.suspend_sale_invoice() and len(c.list_suspended_sales()) == 1
print("✔ قاعدة بلا جدول المعلقات: القائمة فارغة بلا خطأ، والتعليق ينشئ الجدول")

init = seg("init_database")
assert "cursor.execute(self.SUSPENDED_TABLE_SQL)" in init
assert 'cursor.execute("DELETE FROM suspended_sales")' in seg("reset_system_data_action")
assert "self.refresh_suspended_sales_table()" in seg("_apply_admin_mirror")
print("✔ الجدول يُنشأ مع القاعدة، ويُصفَّر مع تصفير البيانات، ومرآة المدير تعرض معلقات العميل")

# ═══ ٦) الواجهة: الزر بجانب الترحيل، والقسم بعد العمليات ═══
build = seg("build_sales_tab")
i_entry = build.index('("المبيعات", "🧾 إصدار مبيعات")')
i_ops, i_susp = build.index('("العمليات", "📚 المبيعات الصادرة")'), build.index('("المعلقات", "⏸️ المعلقات")')
assert i_entry < i_ops < i_susp
assert '"🧾 المبيعات"' not in build and '"📚 العمليات"' not in build
for gone in ("في قسم المبيعات", "جدول العمليات", "تنتقل إلى «العمليات»"):
    assert gone not in src, gone
print("✔ أقسام شاشة المبيعات: «إصدار مبيعات» ثم «المبيعات الصادرة» ثم «المعلقات» — والرسائل بالأسماء الجديدة")
assert 'text="⏸️ تعليق الفاتورة"' in build and "command=self.suspend_sale_invoice" in build
assert build.index("btn_commit.pack(side=\"right\"") < build.index("self.btn_suspend_sale.pack(side=\"right\"")
assert 'head_label("البيان:")' in build and build.index('head_label("الاسم:")') < build.index('head_label("البيان:")')
sw = seg("switch_sales_subtab")
assert 'key == "المعلقات"' in sw and "self.refresh_suspended_sales_table()" in sw
rs = seg("refresh_suspended_sales_table")
assert '"الاسم", "البيان", "الذهب"' in rs and '"إجمالي المعلقات"' in rs
assert 'tree.bind("<Double-1>"' in rs and 'tree.bind("<Return>"' in rs
assert 'self.fit_columns_to_content(tree, "sales_suspended"' in rs
print("✔ زر «تعليق الفاتورة» بجانب «ترحيل واعتماد الفاتورة»؛ «المعلقات» بعد «المبيعات الصادرة» بالبيان والإجماليات؛ فتحٌ بنقرتين أو Enter")

# ═══ ٧) Enter والأسهم في كل الخانات ═══
d = new_app()
fields = [W() for _ in range(5)]
added = []
d.bind_enter_navigation(fields, on_last=lambda: added.append(1))
d.bind_arrow_navigation(fields)
for i in range(4):
    assert fields[i].press("<Return>") == "break"
    assert W.focused is fields[i + 1] and fields[i + 1].selected
assert fields[4].press("<KP_Enter>") == "break" and added == [1]
fields[2].press("<Left>")
assert W.focused is fields[3]
fields[2].press("<Right>")
assert W.focused is fields[1]
print("✔ Enter ينقل للخانة التالية (ويحدّد نصها)، وفي آخر خانة يضيف السطر؛ ← التالية و→ السابقة")

assert ("nav_fields = [self.sale_date, self.sale_invoice_num, self.sale_name, self.sale_note,"
        in build) and "self.bind_enter_navigation(nav_fields, on_last=self.stage_sale_row)" in build
assert "self.bind_arrow_navigation(nav_fields)" in build
assert "nav = [ent_manual, ent_date, cmb_name, ent_note] + [entries[k] for _l, k in field_defs]" in editor
assert "self.bind_enter_navigation(nav, on_last=save_row_and_continue)" in editor
assert "self.bind_arrow_navigation(nav)" in editor
assert "self.fit_dialog_to_screen(win, 1180, 720)" in editor
assert 'btn_save_inv.pack(side="bottom", pady=10, before=table_frame)' in editor
print("✔ شاشة المبيعات (والمعلّقة المفتوحة فيها) من التاريخ حتى آخر خانة، ونافذة تعديل الفاتورة المرحّلة كذلك")

# ═══ ٨) الأعمدة تملأ عرض الجدول تماماً ═══
plan = d.plan_column_widths
w = plan([100, 60, 80], [80, 40, 60], 480)
assert sum(w) == 480 and w[0] > w[2] > w[1], w                      # الفائض بالتناسب
w = plan([100, 60, 80], [80, 40, 60], 200)
assert sum(w) == 200 and all(x >= f for x, f in zip(w, [80, 40, 60])), w   # انكماش نحو الحد الأدنى
w = plan([100, 60, 80], [80, 40, 60], 150)
assert sum(w) == 150 and all(x >= 20 for x in w), w                  # أضيق من الحدود: نسبة واحدة
assert plan([96, 50], [96, 30], 146) == [96, 50]
print("✔ توزيع العرض: الفائض بالتناسب، والضيق نحو الحد الأدنى — المجموع = عرض الجدول دائماً")

fit = seg("fit_columns_to_content")
assert "widths = self.plan_column_widths(desired, floors, avail)" in fit
assert "stretch=not s[\"fixed\"]" in fit and "self.COMPACT_HEADERS.get(col_id)" in fit
assert 'design.get("font", 11)' in fit and 'tree.tag_configure("total_tag", "font")' in fit
pend = seg("refresh_pending_sales_table")
assert pend.index("tree.column(act, width=96") < pend.index("self.fit_columns_to_content(tree, \"pending_sales\"")
print("✔ القياس بخط الجدول الحقيقي، والعناوين تُختصر عند الضيق، وعمود الأزرار ثابت قبل التوزيع")

assert not errors, errors
shutil.rmtree(TMP, ignore_errors=True)
print("\n✅ المبيعات: البيان، المعلقات، التنقل، وتناسق الأعمدة — كلها سليمة")
