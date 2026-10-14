# -*- coding: utf-8 -*-
"""
1.77: إقفال الفترة وسجل التغييرات ومراجعة الفترة، وكشف لكل عملية في الكاستنج وبوليش 1.

  • فترة مقفلة: لا إضافة ولا تعديل ولا حذف ولا تراجع فيها — قبل أن يبدأ الإجراء، وفي الحفظ والحذف أنفسهما.
  • ترحيل في فترة سابقة غير مقفلة: تأكيد مرة لكل زيارة («لا» افتراضياً) — أكثر سبب لأرقام «لم أُدخلها».
  • التراجع عن خطوة في فترة غير المعروضة: تنبيه صريح و«لا» افتراضياً.
  • سجل التغييرات: كل إضافة وتعديل (وما تغيّر) وحذف وتراجع وإقفال بوقته وبالفترة المعروضة وقتها.
  • مراجعة الفترة: الحركات المضافة بعد إقفال خياس صندوقها أو بتاريخ خارج الفترة، ونقلها لفترة تاريخها.
"""
import ast, io, os, re, sqlite3, sys, tempfile, textwrap, time, datetime

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
           "PERIOD_GUARDED_ACTIONS", "PERIOD_ADD_ACTIONS", "_install_period_guards", "confirm_past_period_entry",
           "UNDO_LIMIT", "INVOICE_COLUMNS", "CHANGE_LOG_LIMIT", "CHANGE_LOG_SQL", "CHANGE_LOG_FIELDS", "_log_change",
           "_change_detail", "save_invoice_to_db", "delete_invoice_from_db", "push_undo", "_close_undo_step",
           "_undo_note_row", "_undo_note_name", "undo_step_label", "can_undo", "apply_undo_step",
           "undo_step_periods", "undo_last_action", "invoice_from_row", "inv_period", "inv_in_period",
           "get_setting", "set_setting", "view_only_blocked", "delete_worker_from_db", "check_delete_permission",
           "_stage_type_map", "movement_section", "period_review_data", "MOVABLE_EXCLUDED",
           "move_movements_to_date_period", "JOURNAL_TYPES", "SALE_TYPES", "section_ops_khayas_text",
           "CAST_OPERATIONS", "POLISH_OPERATIONS")


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
ns = {"sqlite3": sqlite3, "time": time, "re": re, "datetime": datetime, "messagebox": MB,
      "log_cloud_error": lambda *a: errors.append(a), "COUNTED_STATUSES": ("ACTIVE", "SETTLED_INOUT")}
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)

TODAY = datetime.datetime.now().strftime("%Y-%m")
PAST = (datetime.date.today().replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")


class App(ns["Base"]):
    def __init__(self, path):
        self.db_path, self.invoices, self.invoice_counter = path, {}, 0
        self.categories = {"المصنعين": ["أحمد"], "المركبين": [], "أقسام_خياس_إضافية": []}
        self.current_display_month = PAST
        self.idle, self.toasts, self.closings = [], [], {}

    def after_idle(self, fn): self.idle.append(fn)
    def end_click(self):
        while self.idle:
            self.idle.pop(0)()
    def update_undo_buttons(self): pass
    def check_edit_permission(self, silent=False): return True
    def mark_backup_dirty(self): self._inv_version = getattr(self, "_inv_version", 0) + 1
    def recalculate_all(self): pass
    def toast(self, text, kind="info"): self.toasts.append(text)
    def get_all_stage_categories(self): return ["الكاستنج", "التلميع/البف"]
    def get_khayas_box_categories(self): return ["الكاستنج", "المصنعين"]
    def get_display_label(self, cat): return {"التلميع/البف": "بوليش 1"}.get(cat, cat)
    def get_stage_config(self, cat):
        return {"الكاستنج": ("صرف كاستنج", "قبض كاستنج", "مسترجع كاستنج"),
                "التلميع/البف": ("صرف تلميع بف", "قبض تلميع بف", "مسترجع بوليش 1")}[cat]
    def get_current_unclosed_khayas(self, cat, month=None): return {"الكاستنج": 2.5}.get(cat, 0.0)
    def get_box_closed_total(self, cat, month=None): return {"الكاستنج": 10.0}.get(cat, 0.0)
    def get_box_closing_entries(self, cat, month=None): return self.closings.get((cat, month), [])
    def period_invoices(self, month):
        return [i for i in self.invoices.values() if self.inv_period(i) == month]

    def post(self, name, t, w, row="", period=None, date=None):
        self.invoice_counter += 1
        d = {"رقم الفاتورة": self.invoice_counter, "التاريخ": date or f"{PAST}-05 10:00:00", "الاسم": name,
             "النوع": t, "الوزن": w, "البيان": "", "settled_status": "ACTIVE", "trees_count": 0.0, "قبل": 0.0,
             "بعد": 0.0, "set_number": "", "row_number": row}
        if period:
            d["period"] = period
        self.invoices[self.invoice_counter] = d
        ok = self.save_invoice_to_db(self.invoice_counter, d)
        self.end_click()
        return self.invoice_counter if ok else None


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "p.db")
with sqlite3.connect(path) as c:
    c.execute("CREATE TABLE names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT)")
    c.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT, "
              "weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT, trees_count REAL, "
              "set_number TEXT, row_number TEXT, manual_no TEXT, period TEXT, sale_kind TEXT)")
a = App(path)


def db_count():
    with sqlite3.connect(path) as c:
        return c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]


def log_rows():
    with sqlite3.connect(path) as c:
        return c.execute("SELECT action, invoice_id, period, view_period, weight, detail FROM change_log "
                         "ORDER BY id").fetchall()


# ═══ ١) الإقفال إعدادٌ يُحفظ، ولا يغيّر رقماً ═══
x1 = a.post("كاستنج", "صرف كاستنج", 10.0, row="1")
x2 = a.post("كاستنج", "قبض كاستنج", 9.0, row="1")
assert a.locked_periods() == frozenset() and not a.is_period_locked(PAST)
assert a.set_period_locked(PAST, True) and a.is_period_locked(PAST)
assert a.set_period_locked("2026-9", True) is False, "صيغة فترة غير صحيحة لا تُقفل"
with sqlite3.connect(path) as c:
    assert c.execute("SELECT value FROM settings WHERE key = 'locked_periods'").fetchone()[0] == PAST
assert log_rows()[-1][:3] == ("إقفال الفترة", None, PAST)
print("✔ إقفال الفترة إعدادٌ في القاعدة (يُرفع مع النسخة) — لا حركة ولا رقم يتغيّر — ويُسجَّل في السجل")

# ═══ ٢) لا إضافة ولا تعديل ولا حذف في فترة مقفلة ═══
n0, MB.log[:] = db_count(), []
assert a.post("كاستنج", "صرف كاستنج", 5.0, row="2") is None
assert db_count() == n0 and a.invoice_counter not in a.invoices, "الحركة المرفوضة لا تبقى في الذاكرة"
assert [m[1] for m in MB.log] == ["الفترة مقفلة 🔒"] and PAST in MB.log[0][2]
edited = dict(a.invoices[x1], **{"الوزن": 99.0})
assert a.save_invoice_to_db(x1, edited) is False and a.invoices[x1]["الوزن"] == 10.0
moved_out = dict(a.invoices[x1], **{"period": TODAY})
assert a.save_invoice_to_db(x1, moved_out) is False, "ولا تُنقل حركة من فترة مقفلة"
assert a.delete_invoice_from_db(x2) is False and x2 in a.invoices and db_count() == n0
assert a.delete_worker_from_db("كاستنج", "الكاستنج", keep_transactions=False) is False
assert len(MB.log) == 1, "رسالة واحدة لكل ضغطة (لا تتكرر مع كل حركة)"
a._period_lock_warned_at = -10.0
assert a.post("كاستنج", "صرف كاستنج", 1.0, period=TODAY) is not None, "فترة أخرى غير مقفلة تعمل كالعادة"
print("✔ الفترة المقفلة: الإضافة والتعديل والنقل منها والحذف (وحذف اسم بحركاته) كلها مرفوضة برسالة واحدة واضحة،"
      " والقاعدة والذاكرة كما هما")

# ═══ ٣) قبل أن يبدأ الإجراء: الحارس على إجراءات الفترة المعروضة ═══
calls = []


class Guarded(App):
    def submit_inbound(self): calls.append("inbound"); return "ran"
    def edit_selected_casting_row(self): calls.append("edit"); return "ran"


g = Guarded(path)
g._install_period_guards()
assert "submit_inbound" in g.__dict__ and "edit_selected_casting_row" in g.__dict__
MB.log[:] = []
assert g.submit_inbound() is None and g.edit_selected_casting_row() is None and calls == []
assert MB.log and MB.log[0][1] == "الفترة مقفلة 🔒"
print("✔ الحارس: في فترة معروضة مقفلة يُمنع الترحيل والتعديل قبل أن يبدأ (لا يُستدعى الإجراء أصلاً)")

a.set_period_locked(PAST, False)
g._locked_periods_cache = None
MB.log[:], MB.answers[:] = [], [False]
assert g.submit_inbound() is None and calls == [], "«لا» يلغي الترحيل في فترة سابقة"
ask = [m for m in MB.log if m[0] == "ask"][0]
assert ask[1] == "التسجيل في فترة سابقة" and ask[3] == "no" and PAST in ask[2] and TODAY in ask[2]
MB.answers[:] = [True]
assert g.submit_inbound() == "ran" and g.submit_inbound() == "ran" and calls == ["inbound", "inbound"]
assert len([m for m in MB.log if m[0] == "ask"]) == 2, "يُسأل مرة واحدة لكل زيارة للفترة"
assert g.edit_selected_casting_row() == "ran", "التعديل لا يُسأل عنه (يخص صفاً قائماً في فترته)"
g.current_display_month = TODAY
assert g.confirm_past_period_entry() is True, "الشهر الحالي بلا سؤال"
assert "self._past_period_ok = set()" in member("on_period_changed")
print("✔ فترة سابقة مفتوحة: قبل أول ترحيل يُسأل «التسجيل في فترة سابقة» و«لا» افتراضياً — مرة لكل زيارة؛ "
      "والشهر الحالي والتعديل بلا سؤال")

# ═══ ٤) التراجع: لا يمسّ فترة مقفلة، وينبّه إن كانت الخطوة في فترة غير المعروضة ═══
a.current_display_month = PAST
x3 = a.post("كاستنج", "صرف كاستنج", 4.0, row="3")
assert a.undo_step_periods(a._undo_stack[-1]) == {PAST}
a.set_period_locked(PAST, True)
MB.log[:] = []
a._period_lock_warned_at = -10.0
a.undo_last_action()
assert x3 in a.invoices and [m[1] for m in MB.log] == ["الفترة مقفلة 🔒"], "لا تراجع في فترة مقفلة"
a.set_period_locked(PAST, False)
a.current_display_month = TODAY
MB.log[:], MB.answers[:] = [], [False]
a.undo_last_action()
ask = [m for m in MB.log if m[0] == "ask"][0]
assert "ليست الفترة المعروضة" in ask[2] and PAST in ask[2] and ask[3] == "no" and x3 in a.invoices
MB.answers[:] = [True]
a.undo_last_action()
assert x3 not in a.invoices
print("✔ التراجع: يُرفض في فترة مقفلة؛ وخطوة في فترة غير المعروضة تُنبَّه صراحةً و«لا» افتراضياً "
      "(كان Ctrl+Z في الشهر الجديد يتراجع بصمت عن إقفال الشهر السابق)")

# ═══ ٥) سجل التغييرات ═══
a.current_display_month = PAST
x4 = a.post("أحمد", "صرف ذهب", 3.0, row="7")
a.invoices[x4]["الوزن"] = 4.0
a.invoices[x4]["row_number"] = "8"
a.save_invoice_to_db(x4, a.invoices[x4]); a.end_click()
a.save_invoice_to_db(x4, a.invoices[x4]); a.end_click()          # بلا تغيير: لا سطر
a.delete_invoice_from_db(x4); a.end_click()
rows = [r for r in log_rows() if r[1] == x4]
assert [r[0] for r in rows] == ["إضافة", "تعديل", "حذف"], rows
assert rows[1][5] == "الوزن من 3.00 إلى 4.00، الصف من 7 إلى 8" and rows[1][2] == PAST and rows[1][3] == PAST
undo_rows = [r for r in log_rows() if r[0].startswith("تراجع")]
assert undo_rows and undo_rows[0][1] == x3
assert "self._log_change(cursor" in member("save_invoice_to_db") and "self.CHANGE_LOG_SQL" in member("init_database")
print("✔ السجل: الإضافة، والتعديل بما تغيّر («الوزن من 3.00 إلى 4.00، الصف من 7 إلى 8»)، والحذف، والتراجع — "
      "بوقتها وفترتها والفترة المعروضة وقتها؛ والحفظ بلا تغيير لا يُسجَّل")

# ═══ ٦) مراجعة الفترة: ما أُضيف بعد الإقفال، وما تاريخه خارج الفترة ═══
c1 = a.post("الخياس الفعلي", "قيد يومي دائن", 10.0)
a.closings[("الكاستنج", PAST)] = [{"ids": [c1], "date": f"{PAST}-28 23:59:00"}]
late = a.post("كاستنج", "صرف كاستنج", 6.0, row="5", date=f"{TODAY}-02 09:00:00")
data = a.period_review_data(PAST)
by = {f["id"]: f for f in data["flagged"]}
assert set(by) == {late}, data["flagged"]
assert by[late]["section"] == "الكاستنج" and len(by[late]["reasons"]) == 2
assert by[late]["reasons"][0].startswith("أُضيفت بعد إقفال خياس الكاستنج")
assert by[late]["reasons"][1] == f"تاريخها {TODAY}-02 خارج الفترة"
assert data["boxes"][0] == {"cat": "الكاستنج", "label": "الكاستنج", "total": 12.5, "closed": 10.0,
                            "remaining": 2.5, "closings": 1}
assert any(r[2] == late and r[1] == "إضافة" for r in data["log"])
print("✔ المراجعة: حركة أُضيفت بعد إقفال خياس الكاستنج وبتاريخ الشهر التالي تظهر بسببيها، وخياس الصندوق "
      "(12.50 = المُقفل 10.00 + غير المُقفل 2.50)، والسجل")

# النقل إلى فترة التاريخ: خطوة تراجع واحدة، ولا يندمج بصفٍّ قائم، ولا يمسّ فترة مقفلة
clash = a.post("كاستنج", "صرف كاستنج", 1.0, row="9", date=f"{TODAY}-03 09:00:00")
a.post("كاستنج", "قبض كاستنج", 2.0, row="9", period=TODAY)
a.set_period_locked(TODAY, True)
moved, skipped = a.move_movements_to_date_period([late])
assert moved == [] and skipped[-1] == (late, "فترة مقفلة")
a.set_period_locked(TODAY, False)
a._period_lock_warned_at = -10.0
moved, skipped = a.move_movements_to_date_period([late, clash, x1])
assert moved == [late] and a.inv_period(a.invoices[late]) == TODAY
assert dict(skipped) == {clash: f"الصف 9 مستخدم في فترة {TODAY}", x1: "تاريخها داخل فترتها"}
assert a.undo_step_label(a._undo_stack[-1]) == "نقل 1 حركة إلى فترات تواريخها"
with sqlite3.connect(path) as c:
    assert c.execute("SELECT period FROM invoices WHERE invoice_id = ?", (late,)).fetchone()[0] == TODAY
assert any(r[1] == late and r[0] == "تعديل" and f"الفترة من {PAST} إلى {TODAY}" in r[5] for r in log_rows())
print("✔ «نقل المحدد إلى فترة تاريخه»: يُنقل ويُسجَّل، ولا يُنقل ما صفّه مستخدم في الهدف (لا اندماج) "
      "ولا ما تاريخه داخل فترته، ولا شيء إن كانت إحدى الفترتين مقفلة")

# ═══ ٧) مسارات الكتابة الأخرى والواجهة ═══
for name in ("close_split_khayas_box", "close_khayas_box"):
    assert "self.period_lock_blocked([month])" in member(name), name
assert "self.period_lock_blocked({self.inv_period(self.invoices[i])" in member("reopen_khayas_box_dialog")
assert "self.period_lock_blocked({self.inv_period(inv) for inv in related})" in member("perform_khayas_box_deletion")
assert "self.period_lock_blocked(self.locked_periods())" in member("reset_system_data_action")
assert "self.is_period_locked(str(arch_date" in member("sync_all_archives")
assert "self.period_lock_blocked([self.inv_period(mem)" in member("open_edit_invoice_ui")
assert "self.is_period_locked(month)" in member("get_unclosed_periods")
missing = [n for n in a.PERIOD_GUARDED_ACTIONS if not any(isinstance(m, ast.FunctionDef) and m.name == n
                                                          for m in cls.body)]
assert not missing, missing
assert set(a.PERIOD_ADD_ACTIONS) <= set(a.PERIOD_GUARDED_ACTIONS)
init = member("__init__")
assert init.index("self._install_view_only_guards()") < init.index("self._install_period_guards()")
assert "self.btn_period_lock = ctk.CTkButton(" in src and "command=self.toggle_period_lock" in src
toggle = member("toggle_period_lock")
assert "self.check_edit_permission()" in toggle and "self.period_lock_notes(month)" in toggle
assert '"🔎 مراجعة الفترة", lambda: self.open_period_review_window()' in src
print("✔ الإقفال يشمل: إقفال الخياس وفتحه، وحذف صندوق، والتصفير، والأرشفة القديمة، وفتح حركة للتعديل من "
      "كشف حساب؛ وزر «🔒 إقفال الفترة / 🔓 فتح الفترة» أعلى الشاشة، و«🔎 مراجعة الفترة» في الرئيسية")

# ═══ ٨) كشف لكل عملية في الكاستنج وبوليش 1، وخياس القسم = مجموعهما ═══
assert a.section_ops_khayas_text("الكاستنج", "مسترجع كاستنج", {"فاقد": 3.5, "صب وتحليل": 0.2}) == \
    "خياس قسم الكاستنج (العمليات مدموجة) = فاقد 3.50  +  صب وتحليل 0.20  =  3.70 جم"
assert a.section_ops_khayas_text("التلميع/البف", None, {"فاقد": 1.0, "ليزر": 0.4}) == \
    "خياس قسم بوليش 1 (العمليات مدموجة) = فاقد 1.00  +  ليزر 0.40  =  1.40 جم"
assert a.section_ops_khayas_text("الكاستنج", "x", {}) .endswith("=  0.00 جم")
render = member("render_stage_ops_table")
assert "if op_filter:" in render and 'r[2].get("op", "فاقد") == op_filter' in render
assert "self.section_ops_khayas_text(section, recover_name, op_khayas)" in render
assert 'shown_extra = extra if op_filter != self.CAST_ANALYSIS else None' in render
assert 'f"كشف {operation} — {label}"' in member("refresh_casting_table")
assert 'f"كشف {operation} — {label}"' in member("refresh_polish_buff_table")
assert 'r[2].get("op", "فاقد") == "فاقد"' in member("get_stage_monthly_tree_totals")
print("✔ الكاستنج: كشف «فاقد» وحده وكشف «صب وتحليل» وحده، وبوليش 1: كشف «فاقد» وحده وكشف «ليزر» وحده — "
      "كلٌّ بإجمالياته وخياسه، وتحته خياس القسم = مجموع العمليات (فاقد صندوقه)")
assert not errors, errors
print("\n✅ إقفال الفترة وسجل التغييرات ومراجعة الفترة وكشف كل عملية — سليمة")
