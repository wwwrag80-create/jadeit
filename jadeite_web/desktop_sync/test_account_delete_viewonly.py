# -*- coding: utf-8 -*-
"""
1.72: (١) حذف حساب أو حساب فرعي من شجرة الحسابات — يختفي من كل الشاشات وقوائم الأسماء، وحركاته تبقى
محفوظة ولا يتغيّر أي رصيد، والحسابات الأساسية لا تُحذف، والتراجع يعيده. (٢) حساب العميل في برنامج المدير
للعرض فقط — لا يُكتب شيء في قاعدته من أي مسار.
"""
import ast, io, json, os, sqlite3, sys, tempfile, textwrap, time

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(node, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, node))


MEMBERS = ("UNDO_LIMIT", "INVOICE_COLUMNS", "OPENING_ACCOUNT", "DELETED_ACCOUNTS_KEY", "deleted_account_names",
           "_store_deleted_accounts", "revive_deleted_accounts", "system_account_names", "delete_account", "get_supplier_name_values",
           "get_supplier_name_values_no_mustarja", "get_account_statement_options", "save_name_to_db",
           "set_setting", "get_setting", "push_undo", "_close_undo_step", "_undo_note_row", "_undo_note_name",
           "undo_step_label", "can_undo", "apply_undo_step", "invoice_from_row", "delete_worker_from_db",
           "check_delete_permission", "view_only_blocked", "save_invoice_to_db", "LOCKED_PERIODS_KEY", "locked_periods", "is_period_locked", "period_lock_blocked", "CHANGE_LOG_SQL", "CHANGE_LOG_FIELDS", "_log_change", "_change_detail", "_log_auto_fix", "undo_step_periods", "_view_only_restore",
           "VIEW_ONLY_ACTIONS", "_install_view_only_guards", "save_suspended_sale", "SUSPENDED_TABLE_SQL")
shown = []
ns = {"sqlite3": sqlite3, "json": json, "time": time, "log_cloud_error": lambda *a: None,
      "messagebox": type("MB", (), {"showinfo": staticmethod(lambda *a, **k: shown.append(a[0]))})}
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)


class App(ns["Base"]):
    def __init__(self, path):
        self.db_path, self.invoices, self.invoice_counter = path, {}, 0
        self.categories = {"الموردين": ["مورد أ", "مورد ب"], "حسابات إضافية": ["صندوق النقد"],
                           "المصنعين": ["أحمد"]}
        self.current_display_month = "2026-10"
        self.idle, self.refreshed, self.toasts = [], 0, []

    def after_idle(self, fn): self.idle.append(fn)
    def end_click(self):
        while self.idle:
            self.idle.pop(0)()
    def update_undo_buttons(self): pass
    def check_edit_permission(self, silent=False): return not getattr(self, "view_only", False)
    def mark_backup_dirty(self): pass
    def get_all_mustarja_names(self): return ["مسترجع كاستنج"]
    def get_khayas_box_categories(self): return ["الكاستنج", "المصنعين"]
    def get_all_stage_categories(self): return ["الكاستنج"]
    def get_box_account_name(self, c): return f"صندوق {c}"
    def get_all_loss_accounts(self): return ["فاقد الكاستنج"]
    def refresh_account_name_lists(self): self.refreshed += 1
    def toast(self, text, kind="info"): self.toasts.append(text)
    def load_data_from_db(self): self.reloaded = getattr(self, "reloaded", 0) + 1
    def recalculate_all(self): pass

    def post(self, name, t, w):
        self.invoice_counter += 1
        d = {"رقم الفاتورة": self.invoice_counter, "التاريخ": "2026-10-05 10:00:00", "الاسم": name, "النوع": t,
             "الوزن": w, "البيان": "", "settled_status": "ACTIVE", "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0,
             "set_number": "", "row_number": "", "period": "2026-10"}
        self.invoices[self.invoice_counter] = d
        self.save_invoice_to_db(self.invoice_counter, d)
        return self.invoice_counter


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "a.db")
with sqlite3.connect(path) as c:
    c.execute("CREATE TABLE names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT)")
    c.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT, "
              "weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT, trees_count REAL, "
              "set_number TEXT, row_number TEXT, manual_no TEXT, period TEXT, sale_kind TEXT)")
    c.executemany("INSERT INTO names (name, category) VALUES (?, ?)",
                  [("مورد أ", "الموردين"), ("مورد ب", "الموردين"), ("صندوق النقد", "حسابات إضافية"), ("أحمد", "المصنعين")])

a = App(path)
moves = [a.post("مورد أ", "وارد ذهب (عيار 18)", 100.0), a.post("مورد أ", "قيد يومي مدين", 5.0),
         a.post("حساب قديم", "قيد يومي دائن", 3.0)]
a.end_click(); a._undo_stack.clear()
opts = a.get_account_statement_options()
assert "مورد أ" in opts and "حساب قديم" in opts and "صندوق النقد" in opts

# ═══ ١) حذف مورد له حركات ═══
a.delete_account("مورد أ")
a.end_click()
assert "مورد أ" not in a.categories["الموردين"] and "مورد أ" not in a.get_supplier_name_values()
assert "مورد أ" not in a.get_account_statement_options(), "يختفي من كشف الحساب والقيود والبحث (مصدرها واحد)"
assert all(i in a.invoices for i in moves), "حركاته باقية"
with sqlite3.connect(path) as c:
    assert c.execute("SELECT COUNT(*) FROM invoices WHERE name = 'مورد أ'").fetchone()[0] == 2
    assert c.execute("SELECT COUNT(*) FROM names WHERE name = 'مورد أ'").fetchone()[0] == 0
assert a.deleted_account_names() == {"مورد أ"} and a.refreshed == 1
print("✔ حذف مورد له حركات: يختفي من الموردين وكشف الحساب والقيود والبحث، وحركتاه باقيتان في الدفاتر")

# ═══ ٢) حساب ظاهر من القيود اليومية فقط (بلا قائمة أسماء) ═══
a.delete_account("حساب قديم")
a.end_click()
assert "حساب قديم" not in a.get_account_statement_options() and moves[2] in a.invoices
print("✔ حساب ظاهر من القيود اليومية وحدها يختفي أيضاً (ولا يعود من حركاته)، وقيده باقٍ")

# ═══ ٣) التراجع خطوة بخطوة يعيد الحساب ═══
assert a.undo_step_label(a._undo_stack[-1]) == "حذف الحساب (حساب قديم)"
a.apply_undo_step(a._undo_stack.pop())
assert "حساب قديم" in a.get_account_statement_options() and "مورد أ" not in a.get_account_statement_options()
a.apply_undo_step(a._undo_stack.pop())
assert "مورد أ" in a.get_supplier_name_values() and "مورد أ" in a.get_account_statement_options()
assert a.deleted_account_names() == frozenset()
print("✔ التراجع: الأولى تعيد «حساب قديم»، والثانية تعيد «مورد أ» إلى قائمته")

# ═══ ٤) إضافة حساب بالاسم نفسه تعيده بحركاته ═══
a.delete_account("صندوق النقد"); a.end_click()
assert "صندوق النقد" not in a.get_account_statement_options()
a.categories["حسابات إضافية"].append("صندوق النقد"); a.save_name_to_db("صندوق النقد", "حسابات إضافية")
assert "صندوق النقد" in a.get_account_statement_options() and a.deleted_account_names() == frozenset()
print("✔ إضافة حساب بالاسم نفسه تعيده ظاهراً (ومعه حركاته)")

# قيد جديد على حساب محذوف يعيده، والتراجع عن القيد يُخفيه من جديد
a.delete_account("حساب قديم"); a.end_click()
je = a.post("حساب قديم", "قيد يومي دائن", 2.0)
a.revive_deleted_accounts(("حساب قديم", "صندوق النقد"))
a.end_click()
assert "حساب قديم" in a.get_account_statement_options() and a.deleted_account_names() == frozenset()
assert a.undo_step_label(a._undo_stack[-1]) != "حذف الحساب (حساب قديم)"
a.apply_undo_step(a._undo_stack.pop())
assert je not in a.invoices and a.deleted_account_names() == {"حساب قديم"}
assert "حساب قديم" not in a.get_account_statement_options() and moves[2] in a.invoices
a.apply_undo_step(a._undo_stack.pop())
assert a.deleted_account_names() == frozenset()
jsrc = member("submit_journal_entry")
assert jsrc.index("self.revive_deleted_accounts((from_name, to_name))") > jsrc.rindex("save_invoice_to_db")
print("✔ قيد جديد على حساب محذوف يعيده ظاهراً، والتراجع عن القيد يحذف القيد ويُخفيه من جديد")

# ═══ ٥) الحسابات الأساسية محمية ═══
system = a.system_account_names()
for n in ("حساب الخزينة", "المبيعات", "المصنع", "صندوق الكاستنج", "فاقد الكاستنج", "مسترجع كاستنج",
          "رصيد افتتاحي", "حساب الخسائر", "حساب الذهب"):
    assert n in system, n
assert "مورد ب" not in system and "صندوق النقد" not in system
sel = member("delete_selected_account")
assert "if name in self.system_account_names():" in sel and "حذف صندوق خياس" in sel
assert "self.delete_account(name)" in sel and sel.index("askyesno") < sel.index("self.delete_account(name)")
print("✔ الخزينة والمواد والمبيعات والخسائر والافتتاحي والمصنع وصناديق الخياس وفواقدها ومسترجعاتها لا تُحذف")

chart = member("refresh_chart_of_accounts")
assert chart.count("deleted") >= 3 and 'command=self.delete_selected_account' in member("build_chart_of_accounts_tab")
print("✔ الشجرة تُخفي المحذوف (الموردين والمضافة والقيود)، وزر «🗑️ حذف الحساب المحدد»")

# ═══ ٦) حساب العميل في برنامج المدير للعرض فقط ═══
class Viewer(App):
    def commit_sale_invoice(self): return "ran"
    def undo_last_action(self): return "ran"
    def submit_inbound(self): return "ran"


v = Viewer(path)
assert v.undo_last_action() == "ran"
v.view_only = True
v._install_view_only_guards()
before = sqlite3.connect(path).execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
shown.clear()
assert v.save_invoice_to_db(99, dict(a.invoices[moves[0]], **{"رقم الفاتورة": 99})) is False
assert v.check_delete_permission() is False and v.delete_worker_from_db("مورد ب", "الموردين") is False
v.save_name_to_db("اسم جديد", "الموردين")
v.set_setting("x", "1")
assert v.save_suspended_sale({"rows": []}) is None
with sqlite3.connect(path) as c:
    assert c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == before
    assert c.execute("SELECT COUNT(*) FROM names WHERE name = 'اسم جديد'").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM settings WHERE key = 'x'").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM names WHERE name = 'مورد ب'").fetchone()[0] == 1
assert shown and shown[0] == "للعرض فقط"
v.end_click()
assert getattr(v, "reloaded", 0) >= 1, "بعد حفظ مرفوض تعود الذاكرة كنسخة العميل"
print("✔ وضع العرض: لا حفظ حركة ولا حذف ولا اسم ولا إعداد ولا معلّقة — والقاعدة كما هي، ورسالة «للعرض فقط»")

missing = [n for n in v.VIEW_ONLY_ACTIONS if not any(isinstance(m, ast.FunctionDef) and m.name == n for m in cls.body)]
assert not missing, missing
assert "delete_account" not in v.__dict__ and "delete_selected_account" in v.VIEW_ONLY_ACTIONS
shown.clear(); v._view_only_warned_at = -10.0
assert v.commit_sale_invoice() is True and v.undo_last_action() is True and v.submit_inbound() is True
assert shown == ["للعرض فقط"], "رسالة واحدة لا تتكرر مع النقرات المتتالية"
assert App(path).__dict__.get("undo_last_action") is None, "خارج وضع العرض لا يُلمس شيء"
init = member("__init__")
assert "self.view_only = bool(IS_ADMIN_BUILD and client_id)" in init and "self._install_view_only_guards()" in init
assert 'title_suffix += " (للعرض فقط)"' in init
assert "self.view_only_blocked(silent=silent)" in member("check_edit_permission")
print(f"✔ {len(v.VIEW_ONLY_ACTIONS)} إجراء تغيير (ترحيل، تعديل، حذف، إقفال، تراجع…) تُمنع قبل أن تبدأ، "
      "وتُفعَّل في برنامج المدير لحساب العميل وحده")
print("\n✅ حذف الحساب يُبقي حركاته، وحساب العميل في برنامج المدير للعرض فقط")
