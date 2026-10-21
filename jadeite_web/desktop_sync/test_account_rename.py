# -*- coding: utf-8 -*-
"""
1.83: تعديل اسم الحساب (مورد، مصنّع، مركّب، حساب مضاف) — الاسم الجديد في كل مكان والأرقام كما هي.

  • معاملة واحدة: شجرة الأسماء، وكل الحركات في كل الفترات (حتى المقفلة)، وأرشيف الإقفال، والفواتير المعلّقة،
    وقوالب أرقام التشغيل (العميل والمركّب)، وقائمة الحسابات المحذوفة — وسطرٌ في سجل التغييرات.
  • الذاكرة: موضع الاسم في قسمه كما هو، وحركاته، والفهارس؛ والخانات التي كان مختاراً فيها.
  • يُرفض: الاسم الجديد مستخدم (لا دمج)، والحسابات الأساسية والأقسام والمكائن، واسم غير مسجّل، ووضع العرض.
  • خطوة تراجع واحدة تعيد كل شيء — ولا تُرجع اسماً صار لحسابٍ آخر.
"""
import ast, io, json, os, re, sqlite3, sys, tempfile, textwrap, time, datetime

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


MEMBERS = ("LOCKED_PERIODS_KEY", "locked_periods", "is_period_locked", "set_period_locked", "period_lock_blocked",
           "UNDO_LIMIT", "INVOICE_COLUMNS", "CHANGE_LOG_LIMIT", "CHANGE_LOG_SQL", "CHANGE_LOG_FIELDS", "_log_change",
           "_change_detail", "save_invoice_to_db", "push_undo", "_close_undo_step", "_undo_note_row",
           "_undo_note_name", "undo_step_label", "can_undo", "apply_undo_step", "undo_step_periods",
           "undo_last_action", "invoice_from_row", "inv_period", "inv_in_period", "get_setting", "set_setting",
           "view_only_blocked", "clean_name", "check_name_exists", "invoices_by_name", "DELETED_ACCOUNTS_KEY",
           "deleted_account_names", "_store_deleted_accounts", "system_account_names", "SB_PREFIX", "SB_NAME",
           "RENAME_TABLES", "account_rename_block", "account_name_taken", "_rename_in_db", "_rename_in_memory",
           "_rename_settings", "rename_account", "undo_account_rename", "after_account_rename")


class MB:
    log, answers = [], []
    YES, NO = "yes", "no"

    @classmethod
    def showwarning(cls, title, *a, **k): cls.log.append(("warn", title, a[0] if a else ""))
    @classmethod
    def showinfo(cls, title, *a, **k): cls.log.append(("info", title, a[0] if a else ""))
    @classmethod
    def showerror(cls, title, *a, **k): cls.log.append(("error", title, a[0] if a else ""))
    @classmethod
    def askyesno(cls, title, msg, **k):
        cls.log.append(("ask", title, msg, k.get("default")))
        return cls.answers.pop(0) if cls.answers else True


errors = []
ns = {"sqlite3": sqlite3, "time": time, "re": re, "datetime": datetime, "json": json, "messagebox": MB,
      "log_cloud_error": lambda *a: errors.append(a), "COUNTED_STATUSES": ("ACTIVE", "SETTLED_INOUT")}
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)

TODAY = datetime.datetime.now().strftime("%Y-%m")
PAST = (datetime.date.today().replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")


class Combo:
    def __init__(self, text=""): self.text, self.values = text, []
    def get(self): return self.text
    def set(self, t): self.text = t
    def configure(self, **k): self.values = k.get("values", self.values)


class App(ns["Base"]):
    OPENING_ACCOUNT = "رصيد افتتاحي"

    def __init__(self, path):
        self.db_path, self.invoices, self.invoice_counter = path, {}, 0
        self.categories = {"المصنعين": ["أحمد"], "المركبين": ["سالم", "خالد"], "الموردين": ["مورد أ", "مورد ب"],
                           "حسابات إضافية": [], "الآلة/المكائن": ["الكاستينج", "التلميع النهائي"],
                           "أقسام_خياس_إضافية": [], "نسب_خصم_احجار": []}
        self.current_display_month = TODAY
        self.idle, self.toasts, self.lists_refreshed, self.recalcs, self.sb_renders = [], [], 0, 0, 0
        self.view_only, self.edit_ok = False, True

    def after_idle(self, fn): self.idle.append(fn)
    def end_click(self):
        while self.idle:
            self.idle.pop(0)()
    def update_undo_buttons(self): pass
    def check_edit_permission(self, silent=False): return self.edit_ok
    def mark_backup_dirty(self): self._inv_version = getattr(self, "_inv_version", 0) + 1
    def recalculate_all(self): self.recalcs += 1
    def toast(self, text, kind="info"): self.toasts.append(text)
    def refresh_account_name_lists(self): self.lists_refreshed += 1
    def rtl(self, n): return "‏" + n
    def sb_render(self): self.sb_renders += 1
    def get_all_stage_categories(self): return ["الكاستنج", "التلميع/البف"]
    def get_khayas_box_categories(self): return ["الكاستنج", "المصنعين", "المركبين"]
    def get_box_account_name(self, cat): return f"صندوق {cat}"
    def get_all_loss_accounts(self): return ["فاقد الكاستنج"]
    def get_all_mustarja_names(self): return ["مسترجع كاستنج"]
    def get_display_label(self, cat): return cat

    def post(self, name, t, w, row="", period=None, set_number=""):
        self.invoice_counter += 1
        p = period or TODAY
        d = {"رقم الفاتورة": self.invoice_counter, "التاريخ": f"{p}-05 10:00:00", "الاسم": name,
             "النوع": t, "الوزن": w, "البيان": "", "settled_status": "ACTIVE", "trees_count": 0.0, "قبل": 0.0,
             "بعد": 0.0, "set_number": set_number, "row_number": row, "period": p}
        self.invoices[self.invoice_counter] = d
        assert self.save_invoice_to_db(self.invoice_counter, d)
        self.end_click()
        return self.invoice_counter


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "r.db")
with sqlite3.connect(path) as c:
    c.execute("CREATE TABLE names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT)")
    c.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT, "
              "weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT, trees_count REAL, "
              "set_number TEXT, row_number TEXT, manual_no TEXT, period TEXT, sale_kind TEXT)")
    c.execute("CREATE TABLE monthly_archive (id INTEGER PRIMARY KEY AUTOINCREMENT, archive_date TEXT, name TEXT, "
              "category TEXT, khayas REAL DEFAULT 0)")
    c.execute("CREATE TABLE suspended_sales (id INTEGER PRIMARY KEY AUTOINCREMENT, sale_date TEXT DEFAULT '', "
              "manual_no TEXT DEFAULT '', name TEXT DEFAULT '', note TEXT DEFAULT '', discount_pct TEXT DEFAULT '', "
              "rows_json TEXT DEFAULT '[]', draft_json TEXT DEFAULT '{}', created_at TEXT DEFAULT '', "
              "updated_at TEXT DEFAULT '')")
    for cat, names in (("المصنعين", ["أحمد"]), ("المركبين", ["سالم", "خالد"]), ("الموردين", ["مورد أ", "مورد ب"]),
                       ("الآلة/المكائن", ["الكاستينج", "التلميع النهائي"])):
        for n in names:
            c.execute("INSERT INTO names (name, category) VALUES (?, ?)", (n, cat))
    c.execute("INSERT INTO monthly_archive (archive_date, name, category, khayas) VALUES (?, 'سالم', 'المركبين', 1.5)",
              (PAST + "-30",))
    c.execute("INSERT INTO suspended_sales (sale_date, manual_no, name) VALUES (?, '77', 'مورد أ')", (TODAY + "-06",))
    c.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
              ("set_build:9001", json.dumps({"set_number": "9001", "customer": "مورد أ", "assembler": "سالم"},
                                            ensure_ascii=False, sort_keys=True)))
    c.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
              ("set_build:9002", json.dumps({"set_number": "9002", "customer": "مورد أأ"}, ensure_ascii=False,
                                            sort_keys=True)))
    c.execute("INSERT INTO settings (key, value) VALUES ('deleted_accounts', ?)", (json.dumps(["قديم"]),))
a = App(path)
a.sale_name, a.in_supplier, a.kh_account_name = Combo("مورد أ"), Combo("مورد ب"), Combo("مورد أ")
a.combo_op_name, a.current_op_cat = Combo("‏سالم"), "المركبين"
a._sb_state = {"key": "9001"}

# حركات المورد في فترتين (الأولى مقفلة): مبيعات ووارد وقيد يومي؛ وحركات المركّب في صفّه
s1 = a.post("مورد أ", "مبيعات ذهب", 20.0, period=PAST, set_number="9001")
s2 = a.post("مورد أ", "وارد ذهب (عيار 18)", 50.0)
j1 = a.post("مورد أ", "قيد يومي مدين", 3.0, set_number="JE-3")
j2 = a.post("حساب الخزينة", "قيد يومي دائن", 3.0, set_number="JE-3")
b1 = a.post("مورد ب", "مبيعات ذهب", 7.0)
w1 = a.post("سالم", "صرف ذهب", 42.0, row="1", set_number="9001")
w2 = a.post("سالم", "قبض ذهب", 38.5, row="1", set_number="9001")
q1 = a.post("قديم", "قيد يومي مدين", 1.0)
assert a.set_period_locked(PAST, True) and a.is_period_locked(PAST)


def db(sql, *args):
    with sqlite3.connect(path) as c:
        return c.execute(sql, args).fetchall()


def totals():
    out = {}
    for i in a.invoices.values():
        out[i["الاسم"]] = round(out.get(i["الاسم"], 0.0) + i["الوزن"], 2)
    return out


before_totals = totals()
log_before = db("SELECT COUNT(*) FROM change_log")[0][0]

# ═══ ١) تعديل اسم مورد: كل الجداول والفترات (حتى المقفلة) والذاكرة — والأرقام كما هي ═══
MB.log.clear()
assert a.rename_account("مورد أ", "  مورد الأمل‏ ") is True, MB.log
a.end_click()
assert db("SELECT name, category FROM names WHERE name LIKE 'مورد%' ORDER BY id") == [("مورد الأمل", "الموردين"),
                                                                                   ("مورد ب", "الموردين")]
assert db("SELECT invoice_id FROM invoices WHERE name = 'مورد الأمل' ORDER BY invoice_id") == [(s1,), (s2,), (j1,)]
assert not db("SELECT 1 FROM invoices WHERE name = 'مورد أ'")
assert db("SELECT period FROM invoices WHERE invoice_id = ?", s1) == [(PAST,)], "الحركة في الفترة المقفلة باسمها الجديد"
assert db("SELECT name FROM suspended_sales") == [("مورد الأمل",)]
rec = json.loads(db("SELECT value FROM settings WHERE key = 'set_build:9001'")[0][0])
assert rec["customer"] == "مورد الأمل" and rec["assembler"] == "سالم"
assert json.loads(db("SELECT value FROM settings WHERE key = 'set_build:9002'")[0][0])["customer"] == "مورد أأ", \
    "اسمٌ يحوي الاسم القديم لا يُمسّ"
assert a.categories["الموردين"] == ["مورد الأمل", "مورد ب"], "موضعه في قسمه كما هو"
assert all(a.invoices[i]["الاسم"] == "مورد الأمل" for i in (s1, s2, j1))
assert "مورد أ" not in a.invoices_by_name() and len(a.invoices_by_name()["مورد الأمل"]) == 3
after = totals()
assert after.pop("مورد الأمل") == before_totals["مورد أ"] and {k: v for k, v in before_totals.items() if k != "مورد أ"} == after, \
    "الأرصدة لا تتغيّر — الاسم وحده"
assert a.sale_name.get() == "مورد الأمل" and a.kh_account_name.get() == "مورد الأمل" and a.in_supplier.get() == "مورد ب"
assert a.lists_refreshed == 1 and a.recalcs == 1 and a.sb_renders == 1 and a.toasts
log = db("SELECT action, name, period, detail FROM change_log ORDER BY id DESC LIMIT 1")[0]
assert log[0] == "تعديل اسم حساب" and log[1] == "مورد الأمل" and "(مورد أ) ← (مورد الأمل)" in log[3] and "3 حركة" in log[3]
assert db("SELECT COUNT(*) FROM change_log")[0][0] == log_before + 1, "سطرٌ واحد في السجل لا سطر لكل حركة"
assert not [x for x in MB.log if x[0] in ("warn", "error")]
print("✔ تعديل اسم المورد: شجرة الأسماء وكل حركاته في كل الفترات (حتى المقفلة) والمعلّقة وقالب الطقم — والأرصدة كما هي")
print("✔ الذاكرة: موضعه في قسمه، وحركاته وفهرس الأسماء، والخانات التي كان مختاراً فيها؛ وسطرٌ واحد في السجل")

# ═══ ٢) التراجع: كل شيء كما كان (ولا يمنعه إقفال الفترة: الأرقام لم تتغيّر) ═══
MB.log.clear()
a.undo_last_action()
ask = next(x for x in MB.log if x[0] == "ask")
assert "يعود الاسم (مورد أ) بدل (مورد الأمل) في حركاته (3)" in ask[2], ask
assert db("SELECT name FROM names WHERE name LIKE 'مورد%' ORDER BY id") == [("مورد أ",), ("مورد ب",)]
assert db("SELECT invoice_id FROM invoices WHERE name = 'مورد أ' ORDER BY invoice_id") == [(s1,), (s2,), (j1,)]
assert db("SELECT name FROM suspended_sales") == [("مورد أ",)]
assert json.loads(db("SELECT value FROM settings WHERE key = 'set_build:9001'")[0][0])["customer"] == "مورد أ"
assert a.categories["الموردين"] == ["مورد أ", "مورد ب"] and a.invoices[s1]["الاسم"] == "مورد أ"
assert totals() == before_totals and a.sale_name.get() == "مورد أ"
assert not [s for s in a._undo_stack if s.get("rename")], "خطوة التعديل أُزيلت من المكدس"
assert db("SELECT action FROM change_log ORDER BY id DESC LIMIT 1") == [("تراجع (تعديل اسم حساب)",)]
assert not [x for x in MB.log if x[0] in ("warn", "error")], MB.log
print("✔ التراجع (Ctrl+Z) خطوة واحدة: الاسم السابق في كل الجداول والذاكرة والخانات — والفترة المقفلة لا تمنعه")

# ═══ ٣) المركّب: صفّه وحركاته وأرشيف الإقفال وقالب الطقم، وخانة الاسم في مراحل التصنيع ═══
assert a.rename_account("سالم", "سالم الجديد") is True
a.end_click()
assert db("SELECT name, op_type, row_number FROM invoices WHERE set_number = '9001' AND name LIKE 'سالم%' "
          "ORDER BY invoice_id") == [("سالم الجديد", "صرف ذهب", "1"), ("سالم الجديد", "قبض ذهب", "1")]
assert db("SELECT name, category, khayas FROM monthly_archive") == [("سالم الجديد", "المركبين", 1.5)]
assert json.loads(db("SELECT value FROM settings WHERE key = 'set_build:9001'")[0][0])["assembler"] == "سالم الجديد"
assert a.categories["المركبين"] == ["سالم الجديد", "خالد"]
assert a.combo_op_name.get() == "‏سالم الجديد" and a.combo_op_name.values == ["‏سالم الجديد", "‏خالد"]
print("✔ المركّب: حركاته في صفّه وأرشيف إقفال فترته وقالب الطقم، والعامل المختار في مراحل التصنيع باسمه الجديد")

# التراجع لا يُرجع اسماً صار لحسابٍ آخر (أُضيف بعد التعديل): تنبيه، ولا يتغيّر شيء، والخطوة تبقى
a.categories["المصنعين"].append("سالم")
with sqlite3.connect(path) as c:
    c.execute("INSERT INTO names (name, category) VALUES ('سالم', 'المصنعين')")
MB.log.clear()
a.undo_last_action()
assert [x[1] for x in MB.log] == ["لا يمكن التراجع الآن"], MB.log
assert db("SELECT COUNT(*) FROM invoices WHERE name = 'سالم الجديد'") == [(2,)] and \
    db("SELECT name FROM monthly_archive") == [("سالم الجديد",)]
assert a.categories["المركبين"] == ["سالم الجديد", "خالد"] and a._undo_stack[-1].get("rename")
# وإن تخطّى الفحص (القاعدة وحدها تحمل الاسم): المعاملة تُرجع كلها ولا يتغيّر شيء
a.categories["المصنعين"].remove("سالم")
try:
    a.apply_undo_step(a._undo_stack[-1])
    raise AssertionError("كان يجب أن يُرفض")
except ValueError:
    pass
assert db("SELECT COUNT(*) FROM invoices WHERE name = 'سالم الجديد'") == [(2,)] and \
    db("SELECT name FROM monthly_archive") == [("سالم الجديد",)], "رُجعت المعاملة كاملة"
with sqlite3.connect(path) as c:
    c.execute("DELETE FROM names WHERE name = 'سالم'")
MB.log.clear()
a.undo_last_action()
assert a.categories["المركبين"] == ["سالم", "خالد"] and db("SELECT name FROM monthly_archive") == [("سالم",)]
assert not [x for x in MB.log if x[0] in ("warn", "error")], MB.log
assert a.rename_account("سالم", "سالم الجديد") is True
a.end_click()
print("✔ التراجع لا يُرجع اسماً صار لحسابٍ آخر بعد التعديل: تنبيه والخطوة تبقى، ولا يتغيّر شيء (كل شيء أو لا شيء)")

# ═══ ٤) يُرفض: الاسم مستخدم (لا دمج)، والحسابات الأساسية والأقسام والمكائن، واسم غير مسجّل، والعرض ═══
snap = (db("SELECT * FROM names ORDER BY id"), db("SELECT invoice_id, name FROM invoices ORDER BY invoice_id"))
cases = (("مورد أ", "مورد ب"), ("مورد أ", "حساب الخزينة"), ("مورد أ", "المركبين"), ("مورد أ", "صندوق الكاستنج"),
         ("مورد أ", "الإجمالي العام"), ("المصنع", "مصنع جديد"), ("حساب الخزينة", "خزينة"), ("الكاستينج", "مكينة"),
         ("المركبين", "قسم"), ("مسترجع كاستنج", "مسترجع"), ("غير موجود", "اسم"), ("مورد أ", ""), ("لا يوجد أسماء", "س"))
for old, new in cases:
    MB.log.clear()
    assert a.rename_account(old, new) is False, (old, new)
    assert any(x[0] == "warn" for x in MB.log), (old, new, MB.log)
assert a.rename_account("مورد أ", "مورد أ") is False
assert a.account_name_taken("مورد ب") and a.account_name_taken("قديم") and not a.account_name_taken("اسم حر")
a.view_only = True
assert a.rename_account("مورد أ", "اسم حر") is False
a.view_only, a.edit_ok = False, False
assert a.rename_account("مورد أ", "اسم حر") is False
a.edit_ok = True
assert (db("SELECT * FROM names ORDER BY id"), db("SELECT invoice_id, name FROM invoices ORDER BY invoice_id")) == snap
print("✔ يُرفض: اسمٌ مستخدم (لا دمج حسابين)، والحسابات الأساسية والصناديق والمسترجعات والأقسام والمكائن، واسمٌ غير "
      "مسجّل، والفارغ — ووضع العرض والتعديل المقفول")

# ═══ ٥) حساب قيود بلا تسجيل، وقائمة الحسابات المحذوفة تتبع الاسم ═══
assert a.rename_account("قديم", "قديم معدّل") is True
a.end_click()
assert a.deleted_account_names() == frozenset({"قديم معدّل"}) and a.invoices[q1]["الاسم"] == "قديم معدّل"
assert db("SELECT name FROM invoices WHERE invoice_id = ?", q1) == [("قديم معدّل",)]
a.undo_last_action()
assert a.deleted_account_names() == frozenset({"قديم"}) and a.invoices[q1]["الاسم"] == "قديم"
print("✔ حساب القيود (بلا تسجيل في قسم) يُعدَّل اسمه، والحساب المحذوف يبقى محذوفاً باسمه الجديد — والتراجع يعيدهما")

# ═══ ٦) كل جدول فيه اسم حساب يُعدَّل (عدا سجل التغييرات: تاريخ ما حدث) ═══
tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(\s*([^;]*?)\)\s*\"\"\"", src, re.S))
named = {t for t, body in tables if re.search(r"\bname TEXT", body)}
named |= {m for m in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \([^)]*\bname TEXT", src)}
assert named - {"change_log"} == set(a.RENAME_TABLES), (named, a.RENAME_TABLES)
print(f"✔ الجداول التي تحمل اسم الحساب كلها تُعدَّل: {', '.join(a.RENAME_TABLES)} — وسجل التغييرات يبقى كما كُتب")

# ═══ ٧) الأزرار: الموردين، وصناديق الخياس، ومراحل التصنيع (بجانب ➕)، وشجرة الحسابات ═══
assert "command=self.rename_selected_supplier" in member("build_suppliers_tab")
assert "command=self.rename_selected_worker_ui" in member("build_inquiries_tab")
mfg = member("build_mfg_ui")
assert "command=lambda: self.rename_account_dialog(self.clean_name(self.combo_op_name.get()))" in mfg
assert mfg.index("quick_add_worker") < mfg.index("rename_account_dialog")
assert "command=self.rename_selected_account" in member("build_chart_of_accounts_tab")
dlg = member("rename_account_dialog")
assert "self.account_rename_block(old)" in dlg and "self.rename_account(old, new, parent=win)" in dlg
assert "win.grab_set()" in dlg and "win.focus_force()" in dlg and 'entry.bind("<Return>", save)' in dlg
assert "messagebox.askyesno(" in dlg and "حتى المقفلة" in dlg
for fn in ("rename_selected_supplier", "rename_selected_worker_ui", "rename_selected_account"):
    assert "self.rename_account_dialog(" in member(fn) and "total_tag" in member(fn) or "leaf" in member(fn)
undo = member("undo_last_action")
assert 'self.after_account_rename(step["rename"]["new"], step["rename"]["old"], recalc=False)' in undo
assert 'or step.get("rename")' in member("_close_undo_step")
print("✔ «✏️ تعديل الاسم» في الموردين وصناديق الخياس ومراحل التصنيع (بجانب ➕) وشجرة الحسابات — نافذة بتأكيد، Enter يحفظ")

assert not errors, errors
print("\n✅ تعديل اسم الحساب: الاسم الجديد في المبيعات وكل الحركات والشاشات، والأرقام كما هي، وخطوة تراجع واحدة")
