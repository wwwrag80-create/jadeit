# -*- coding: utf-8 -*-
"""
التراجع الخفيف (الدفعة ١٥) — من دوال البرنامج نفسه على قاعدة SQLite حقيقية مؤقتة:

  • كل حذف حركة قابل للتراجع تلقائياً، وكل حذف في الضغطة نفسها خطوة واحدة.
  • الخطوة تسجّل الصورة السابقة **من القاعدة** للحركات التي تتغيّر داخلها فقط
    (لا نسخة كاملة من البيانات)، والإقفال/إعادة الفتح/حذف الاسم خطوات بأسمائها.
  • الترحيل العادي بعد انتهاء الضغطة لا يدخل في الخطوة، والخطوة الفارغة تُزال.
  • التراجع يُعيد القاعدة والذاكرة معاً (والأسماء بمواضعها) في معاملة واحدة.
"""
import ast, io, os, sqlite3, sys, tempfile, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def member_src(name):
    x = node(name)
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(x, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, x))


def body(name):
    return ast.get_source_segment(src, node(name))


MEMBERS = ["UNDO_LIMIT", "INVOICE_COLUMNS", "invoice_from_row", "push_undo", "_close_undo_step",
           "_undo_note_row", "_undo_note_name", "undo_step_label", "can_undo", "apply_undo_step",
           "save_invoice_to_db", "delete_invoice_from_db", "delete_worker_from_db"]
ns = {"sqlite3": sqlite3, "log_cloud_error": lambda *a: (_ for _ in ()).throw(AssertionError(a)),
      "IS_ADMIN_BUILD": False}
exec("class Base:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in MEMBERS), ns)


class App(ns["Base"]):
    def __init__(self, path):
        self.db_path, self.invoices, self.invoice_counter = path, {}, 0
        self.categories = {"المصنعين": ["أحمد", "سالم", "خالد"], "الموردين": ["مورد"]}
        self.current_display_month = "2026-09"
        self.idle = []

    def after_idle(self, fn):           # نهاية الضغطة الجارية
        self.idle.append(fn)

    def end_click(self):
        while self.idle:
            self.idle.pop(0)()

    def update_undo_buttons(self): pass
    def check_delete_permission(self): return True
    def check_edit_permission(self): return True
    def mark_backup_dirty(self): pass

    def inv_period(self, inv):
        return inv.get("period") or str(inv.get("التاريخ", ""))[:7]

    def post(self, name, t, w, period="2026-09"):
        self.invoice_counter += 1
        d = {"رقم الفاتورة": self.invoice_counter, "التاريخ": f"{period}-05 10:00:00", "الاسم": name,
             "النوع": t, "الوزن": w, "البيان": "", "settled_status": "ACTIVE", "trees_count": 0.0,
             "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": "", "رقم الفاتورة اليدوي": "",
             "period": period}
        self.invoices[self.invoice_counter] = d
        self.save_invoice_to_db(self.invoice_counter, d)
        return self.invoice_counter


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "undo.db")
with sqlite3.connect(path) as c:
    c.execute("CREATE TABLE names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT)")
    c.execute("""CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
                 weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
                 trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '',
                 manual_no TEXT DEFAULT '', period TEXT DEFAULT '')""")
    c.executemany("INSERT INTO names (name, category) VALUES (?, ?)",
                  [("أحمد", "المصنعين"), ("سالم", "المصنعين"), ("خالد", "المصنعين"), ("مورد", "الموردين")])

app = App(path)
ids = [app.post("أحمد", "صرف ذهب", 10.0), app.post("سالم", "صرف ذهب", 20.0),
       app.post("سالم", "قبض ذهب", 15.0), app.post("مورد", "وارد", 50.0)]
app.end_click()
assert not app.can_undo(), "الترحيل العادي لا يفتح خطوة تراجع"


def db_rows():
    with sqlite3.connect(path) as c:
        return c.execute(f"SELECT {app.INVOICE_COLUMNS} FROM invoices ORDER BY invoice_id").fetchall()


def db_names():
    with sqlite3.connect(path) as c:
        return sorted(c.execute("SELECT name, category FROM names").fetchall())


def mem():
    return {k: app.invoice_from_row(r) for k, r in ((r[0], r) for r in db_rows())}


base_rows, base_names = db_rows(), db_names()
base_mem = {k: dict(v) for k, v in app.invoices.items()}
assert mem() == base_mem, "الذاكرة = ما يُحمَّل من القاعدة (invoice_from_row مصدر التحويل الواحد)"

# ═══ ١) حذف حركة واحدة ثم التراجع ═══
assert app.delete_invoice_from_db(ids[0])
assert app.can_undo() and app.undo_step_label(app._undo_stack[-1]) == "حذف حركة (أحمد — صرف ذهب)"
app.end_click()
assert len(app._undo_stack[-1]["rows"]) == 1, "الخطوة تحفظ الحركة المحذوفة وحدها لا نسخة من كل البيانات"
app.apply_undo_step(app._undo_stack.pop())
assert db_rows() == base_rows and app.invoices == base_mem
print("✔ حذف حركة يفتح خطوة تراجع تلقائياً، والتراجع يُعيدها للقاعدة والذاكرة كما كانت")

# ═══ ٢) عدّة حذوفات في الضغطة نفسها = خطوة واحدة، والترحيل بعدها خارجها ═══
app.delete_invoice_from_db(ids[1]); app.delete_invoice_from_db(ids[2])
assert len(app._undo_stack) == 1 and app.undo_step_label(app._undo_stack[-1]) == "حذف 2 حركات"
app.end_click()
later = app.post("خالد", "صرف ذهب", 7.0)             # ضغطة لاحقة: ترحيل عادي
app.end_click()
assert later not in app._undo_stack[-1]["rows"], "ما بعد الضغطة لا يدخل في خطوتها"
app.apply_undo_step(app._undo_stack.pop())
assert later in app.invoices and all(i in app.invoices for i in ids[1:3])
assert [r for r in db_rows() if r[0] != later] == base_rows
app.delete_invoice_from_db(later); app.end_click(); app._undo_stack.clear()
print("✔ حذف قيد بطرفيه (أو صفّ بحركاته) في ضغطة واحدة = خطوة واحدة، والترحيل اللاحق يبقى")

# ═══ ٣) خطوة صريحة (إقفال): ما يُنشأ داخلها يُحذف بالتراجع، وما يُعدَّل يعود ═══
app.push_undo("إقفال المصنعين 2026-09")
new1 = app.post("حساب الخسائر", "قيد يومي مدين", 3.0)
new2 = app.post("صندوق المصنعين", "قيد يومي دائن", 3.0)
edited = dict(app.invoices[ids[3]], **{"الوزن": 99.0})
app.invoices[ids[3]] = edited                       # الذاكرة تتغيّر قبل الحفظ (النمط الشائع)
app.save_invoice_to_db(ids[3], edited)
app.end_click()
step = app._undo_stack[-1]
assert step["label"] == "إقفال المصنعين 2026-09" and step["rows"][new1] is None and step["rows"][new2] is None
assert step["rows"][ids[3]][4] == 50.0, "الصورة السابقة من القاعدة لا من الذاكرة المعدّلة سلفاً"
app.apply_undo_step(app._undo_stack.pop())
assert db_rows() == base_rows and app.invoices == base_mem
print("✔ التراجع عن الإقفال يحذف قيديه، والحركة المعدّلة تعود بقيمتها المحفوظة (50 لا 99)")

# ═══ ٤) حذف اسم بحركاته: الاسم يعود في موضعه وحركاته معه ═══
app.delete_worker_from_db("سالم", "المصنعين", keep_transactions=False)
assert "سالم" not in app.categories["المصنعين"] and ids[1] not in app.invoices
app.end_click()
app.apply_undo_step(app._undo_stack.pop())
assert app.categories["المصنعين"] == ["أحمد", "سالم", "خالد"], app.categories
assert db_names() == base_names and db_rows() == base_rows and app.invoices == base_mem
print("✔ حذف اسم بحركاته ثم التراجع: الاسم يعود في موضعه وحركاته كما كانت")

# ═══ ٥) خطوة داخل خطوة تنضمّ إليها (حذف صندوق بعمّاله خطوة واحدة) ═══
outer = app.push_undo("حذف صندوق (المصنعين)")
app.delete_invoice_from_db(ids[0])
app.delete_worker_from_db("خالد", "المصنعين")
assert len(app._undo_stack) == 1 and app._undo_stack[-1] is outer and outer["label"] == "حذف صندوق (المصنعين)"
app.end_click()
app.apply_undo_step(app._undo_stack.pop())
assert app.categories["المصنعين"] == ["أحمد", "سالم", "خالد"] and app.invoices == base_mem
print("✔ الخطوات المتداخلة في الضغطة نفسها خطوة واحدة باسمها الصريح")

# ═══ ٦) اسم غير موجود لا يُضاف بالتراجع، والخطوة الفارغة تُزال ═══
app.push_undo("حذف الاسم (غير موجود)")
app._undo_note_name("غير موجود", "المصنعين")
app.end_click()
assert not app.can_undo(), "خطوة لم يتغيّر فيها شيء لا تبقى في المكدس"
print("✔ الخطوة الفارغة تُزال، والاسم غير الموجود لا يُسجَّل (فلا يُضاف بالتراجع)")

# ═══ ٧) المكدس محدود ═══
for k in range(app.UNDO_LIMIT + 5):
    app.push_undo(f"خطوة {k}")
    app._undo_open["names"].append(("x", "y", 0))
    app.end_click()
assert len(app._undo_stack) == app.UNDO_LIMIT and app._undo_stack[0]["label"] == "خطوة 5"
print(f"✔ المكدس محدود بـ {app.UNDO_LIMIT} خطوة")

# ═══ ٨) الربط في البرنامج ═══
for fn, label in (("close_split_khayas_box", "إقفال "), ("close_khayas_box", "إقفال "),
                  ("reopen_khayas_box_dialog", "إعادة فتح إقفال"), ("perform_khayas_box_deletion", "حذف صندوق")):
    assert "self.push_undo(f\"" + label in body(fn), fn
assert 'step["cats"].append(stage_name)' in body("perform_khayas_box_deletion")
assert "self._undo_stack, self._undo_open = [], None" in body("load_data_from_db")
assert "self.invoice_from_row(row)" in body("load_data_from_db")
ctrl = body("_on_ctrl_number_key")
assert '("z", "Z")' in ctrl and "keycode\", 0) == 90" in ctrl and "self._on_ctrl_z(event)" in ctrl
assert "isinstance(focus, (tk.Entry, tk.Text))" in body("_on_ctrl_z")
assert "self.register_undo_button(btn_global_undo, compact=True)" in body("create_layout")
assert "deepcopy" not in body("push_undo")
undo = body("undo_last_action")
assert "askyesno" in undo and "self.apply_undo_step(step)" in undo and "recalculate_all" in undo
apply_src = body("apply_undo_step")
assert 'cur.execute("BEGIN")' in apply_src and "conn.rollback()" in apply_src
print("✔ الإقفال وإعادة الفتح وحذف الصندوق خطوات بأسمائها، وزر تراجع عام + Ctrl+Z بأي لغة كتابة")
print("✔ إعادة تحميل البيانات (استعادة نسخة) تمسح خطوات التراجع القديمة")

print("\n✅ التراجع الخفيف سليم")
