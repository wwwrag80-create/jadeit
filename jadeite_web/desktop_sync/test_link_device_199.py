# -*- coding: utf-8 -*-
"""1.99 رابط المدير ← جهاز المصنع: ما يفعله المدير يظهر فوراً وثابتاً، ويُعدَّل ويُحذف أي شيء، والأرصدة:
  • live_run: الحركات التي مسّها الرابط تُعرف من خطوة التراجع نفسها، وخطوته لا تبقى في تراجع الجهاز، وخطوةٌ مفتوحة
    على الجهاز لا تضمّ ما فعله المدير؛
  • guard_stale_write: نافذةٌ فُتحت قبل أن يغيّر الرابط حركاتها لا تكتب فوقها ولا تعيد محذوفاً — يُلغى ما كتبته في
    الضغطة نفسها، ولا يُكتب بعده شيءٌ منها (LiveStaleEdit من BaseException فلا يبتلعه «except Exception»)؛
  • التراجع على الجهاز لا يعيد ما قبل تعديل المدير؛
  • فاتورة المبيعات تُعدَّل من الرابط بالدالة نفسها التي في نافذة الجهاز (rewrite_sale_invoice)، وسطور النموذج تُفحص؛
  • العمليات: كل الفترات والفترة والاسم والبحث والصفحات؛
  • الأرصدة: دفتر الخزينة مصدرٌ واحد للشريط وللرابط (treasury_ledger)، وتفصيل الرصيد لأي فترة."""
import ast, io, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
methods = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}


def member(name):
    node = methods.get(name) or next(m for m in cls.body if isinstance(m, ast.Assign)
                                     and getattr(m.targets[0], "id", "") == name)
    deco = "".join(f"@{ast.get_source_segment(src, d)}\n" for d in getattr(node, "decorator_list", []))
    return deco + textwrap.dedent(ast.get_source_segment(src, node))


def module_src(name):
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    return ast.get_source_segment(src, node)


def make(names, extra="", env=None):
    ns = dict(env or {})
    body = "\n\n".join(member(n) for n in names) + "\n\n" + extra
    exec("class App:\n" + textwrap.indent(body, "    "), ns)
    return ns["App"], ns


class MB:
    log = []

    @classmethod
    def showwarning(cls, *a, **k):
        cls.log.append(("warning",) + a)

    showerror = showinfo = showwarning

    @classmethod
    def askyesno(cls, *a, **k):
        return True

    askokcancel = askquestion = askyesnocancel = askretrycancel = askyesno


# ═══ ١) LiveStaleEdit ═══
env = {"messagebox": MB}
exec(module_src("LiveStaleEdit"), env)
LiveStaleEdit = env["LiveStaleEdit"]
assert issubclass(LiveStaleEdit, BaseException) and not issubclass(LiveStaleEdit, Exception), \
    "BaseException: «except Exception» في النافذة لا يبتلعه فيكمل الحفظ"
rce = member("report_callback_exception")
assert "isinstance(val, LiveStaleEdit)" in rce and rce.index("return") < rce.index("super().report_callback_exception")
print("✔ إلغاء حفظ النافذة القديمة استثناءٌ لا يبتلعه «except Exception»، وتتجاهله Tk بلا رسالة خطأ")

# ═══ ٢) live_run: ما مسّه الرابط، وتراجع الجهاز ═══
for name in ("_live_noop", "_LiveSink", "_LiveDialogs", "_LiveWriter"):
    exec(module_src(name), env)
env.update(tk=type("tk", (), {"TclError": Exception, "END": "end"}), re=__import__("re"))
UNDO = ("UNDO_LIMIT", "push_undo", "_close_undo_step", "_undo_note_row", "update_undo_buttons", "can_undo",
        "undo_step_label")
App, ns = make(("live_run", "live_mark_touched") + UNDO, extra='''
def after_idle(self, fn):
    self._idle.append(fn)

def open_dialog_paths(self):
    return list(self.dialogs)

def nametowidget(self, path):
    if path not in self.dialogs:
        raise KeyError(path)                              # نافذةٌ أُغلقت
    return type("W", (), {"winfo_exists": lambda w: 1})()

def write(self, inv_id, value):
    self.push_undo("x", auto=True) if self._undo_open is None else None
    self._undo_note_row(inv_id, (inv_id, "d", "اسم", "نوع") if inv_id in self.invoices else None)
    self.invoices[inv_id] = {"الوزن": value}
    return True

def remove(self, inv_id):
    self.push_undo("x", auto=True) if self._undo_open is None else None
    self._undo_note_row(inv_id, (inv_id, "d", "اسم", "نوع"), deleted=True)
    self.invoices.pop(inv_id, None)
    return True
''', env=env)
app = App()
app.__dict__.update(invoices={1: {"الوزن": 1.0}, 2: {"الوزن": 2.0}}, _idle=[], dialogs=[".!dlg1"], _undo_stack=[])
app.push_undo("خطوة الجهاز")
app._undo_note_row(1, (1, "d", "اسم", "نوع"))              # الجهاز عدّل 1 والخطوة لم تُغلق بعد
device_step = app._undo_stack[-1]
res, lines, new = app.live_run("write", 2, 9.0)
assert res is True and new == [] and app.invoices[2]["الوزن"] == 9.0
assert app._undo_stack == [device_step] and set(device_step["rows"]) == {1}, \
    "خطوة الجهاز المفتوحة لا تضمّ ما فعله المدير، وخطوة المدير ليست في تراجع الجهاز"
assert app._live_touch == {2: 1} and app._live_stale == {".!dlg1": {2}} and not app._live_writing
app.live_run("remove", 1)
app.live_run("write", 7, 3.0)
assert app._live_touch == {2: 1, 1: 2, 7: 3} and app._live_stale[".!dlg1"] == {1, 2, 7}, \
    "الحذف والإضافة من الرابط تُعلَّم أيضاً، والنافذة المفتوحة تُعلَّم بها"
assert app._undo_stack == [device_step] and app._undo_open is None
app.dialogs = []                                          # النافذة أُغلقت: تُنسى علامتها
app.live_run("write", 8, 1.0)
assert app._live_stale == {} and app._live_touch[8] == 4
assert "self.__dict__[\"_live_writing\"] = True" in member("live_run") and "finally:" in member("live_run")
print("✔ live_run: ما أضافه المدير أو عدّله أو حذفه معلَّم، وخطوته ليست تراجعاً على الجهاز، ولا تختلط بخطوةٍ مفتوحة هناك")

# ═══ ٣) guard_stale_write ═══
G, _ = make(("guard_stale_write",), extra='''
def after_idle(self, fn):
    self._idle.append(fn)

def _write_origin(self):
    return self.origin

def apply_undo_step(self, step):
    self.reverted.append(dict(step["rows"]))
''', env=dict(env, log_cloud_error=lambda *a: None))
g = G()
g.__dict__.update(_idle=[], reverted=[], origin=None, _undo_stack=[], _undo_open=None)
g.guard_stale_write(5)                                    # لا رابط غيّر شيئاً: لا شيء
g._live_stale = {".!dlg1": {2, 7}}
g.origin = ".!main_dialog_other"
g.guard_stale_write(2)                                    # نافذةٌ أخرى (فُتحت بعد التعديل): تحفظ
g.origin = ".!dlg1"
g.guard_stale_write(3)                                    # حركةٌ لم يمسّها الرابط: تحفظ
step = {"rows": {3: (3,)}}
g._undo_stack, g._undo_open = [step], step
try:
    g.guard_stale_write(2)
    raise AssertionError("كان يجب أن يُلغى الحفظ")
except LiveStaleEdit:
    pass
assert g.reverted == [{3: (3,)}] and g._undo_stack == [] and g._undo_open is None and g._stale_block == ".!dlg1", \
    "ما كتبته النافذة في الضغطة نفسها قبلها يُلغى، وتُزال خطوته"
try:
    g.guard_stale_write(3)
    raise AssertionError("بعد الإلغاء لا تكتب النافذة شيئاً")
except LiveStaleEdit:
    pass
g._live_writing = True
g.guard_stale_write(2)                                    # الرابط نفسه يكتب: لا حارس
assert len(g._idle) == 1
for name in ("save_invoice_to_db", "delete_invoice_from_db"):
    body = member(name)
    assert "self.guard_stale_write(inv_id)" in body and body.index("self.guard_stale_write(inv_id)") < body.index(
        "sqlite3.connect"), f"{name}: الحارس قبل أي كتابة"
stopped = member("_stale_write_stopped")
assert "win.destroy()" in stopped and "self.recalculate_all()" in stopped and "تغيّرت من رابط المدير" in stopped
origin = member("_write_origin")
assert origin.index("self.grab_current") < origin.index("self._pointer_widget") < origin.index("self.focus_get")
print("✔ نافذةٌ قديمة لا تكتب فوق ما فعله المدير ولا تعيد محذوفاً: يُلغى حفظها كاملاً وتُغلق برسالة — وغيرها يحفظ عادياً")

# ═══ ٤) التراجع على الجهاز ═══
undo = member("undo_last_action")
assert "clash = [i for i in step[\"rows\"] if touched.get(i, 0) > step.get(\"seq\", 0)]" in undo
assert undo.index("if clash:") < undo.index("self.apply_undo_step(step)")
assert '"seq": self.__dict__.get("_live_seq", 0)' in member("push_undo")
print("✔ Ctrl+Z على الجهاز لا يعيد صور حركاتٍ عدّلها المدير بعد الخطوة — تُزال الخطوة برسالة")

# ═══ ٥) فاتورة المبيعات من الرابط ═══
S, _ = make(("SALE_ROW_NUM_KEYS", "sale_rows_from_form", "_SET_DIGITS", "normalize_set_number",
             "next_free_sale_row_number", "sale_invoice_note_split"), extra='''
def sale_hidden_keys(self, kind=None):
    return ("الماس",) if kind == "ذهب" else ()

def sale_discount_ratio(self, row=None):
    return 0.7
''')
s = S()
rows, err = s.sale_rows_from_form([
    {"row_number": "1", "set_number": "9001", "ذهب": "26.5", "الماس": "3"},
    {"row_number": "", "set_number": "", "ذهب": ""},               # فارغ ← يُحذف
    {"row_number": "", "set_number": "9003", "ذهب": "٧", "أحجار": "10", "البيان": "جديد"}], "ذهب")
assert err is None and len(rows) == 2 and rows[0]["ذهب"] == 26.5 and rows[0]["الماس"] == 0.0, "الماس مخفيٌّ للذهب"
assert rows[1]["ذهب"] == 7.0 and rows[1]["أحجار بعد الخصم"] == 7.0 and rows[1]["row_number"] == "2", \
    "الأرقام الهندية، والأحجار بعد الخصم بالنسبة، وأصغر صفٍّ شاغر"
for bad in ({"ذهب": "-1"}, {"ذهب": "nan"}, {"ذهب": "abc"}, {"set_number": "9", "ذهب": "0"}):
    assert s.sale_rows_from_form([bad], "ذهب")[0] is None, bad
r = [{"البيان": "أ"}, {"البيان": "أ"}, {"البيان": "خاص"}]
assert s.sale_invoice_note_split(r) == "أ" and [x["البيان"] for x in r] == ["", "", "خاص"]
rw = member("rewrite_sale_invoice")
assert rw.index("push_undo(") < rw.index("delete_invoice_from_db(") < rw.index("self.post_sale_rows(")
assert "self.apply_undo_step(step)" in rw, "مُنع حذف حركةٍ منها: تعود الفاتورة كما كانت"
assert "self.rewrite_sale_invoice(key, edit_rows" in member("open_sale_invoice_editor")
assert "self.sale_invoice_note_split(edit_rows)" in member("open_sale_invoice_editor")
assert '"rewrite_sale_invoice", key, rows' in member("live_do_sale_edit")
print("✔ فاتورة المبيعات من الرابط: سطورها تُفحص (لا سالب ولا nan، والفارغ يُحذف) وتُكتب بالدالة نفسها التي في نافذة الجهاز")

# ═══ ٦) كل نوعٍ يُعدَّل من الرابط ═══
card = member("live_move_html")
for action in ("move_save", "inb_save", "je_save", "rec_save", "mach_save", "any_del", 'v="sedit"'):
    assert action in card, action
post = member("live_post")
for action in ('"rec_save": self.live_do_recovery', '"mach_save": self.live_do_machine', '"sale_save": self.live_do_sale_edit'):
    assert action in post, action
assert "self.live_device_notice(result)" in post
print("✔ كل عملية تُعدَّل وتُحذف من الرابط: مراحل التصنيع، الوارد بعياره، القيد بطرفيه، صب وتحليل بعياره، خياس "
      "المكائن، وفاتورة المبيعات بسطورها — وإشعارٌ على الجهاز")

# ═══ ٧) العمليات: الفترة والاسم والبحث والصفحات ═══
R, _ = make(("LIVE_RECENT_LIMIT", "live_recent_group", "live_recent_match", "live_recent", "live_recent_page",
             "TRACE_STATUSES",
             "_SET_DIGITS", "normalize_set_number"), extra='''
LOSSES_ALL = "__all__"
SALE_TYPES = ("مبيعات ذهب",)
JOURNAL_TYPES = ("قيد يومي مدين", "قيد يومي دائن")

def inv_period(self, inv):
    return inv["period"]

def _stage_type_map(self):
    return {}

def movement_section(self, inv, type_map=None):
    return ("المصنعين", "المصنعين") if inv["الاسم"] in ("خالد", "أحمد") else ("مبيعات", "المبيعات")

def sale_key_of(self, inv):
    return (inv.get("رقم الفاتورة اليدوي", ""), inv["التاريخ"], inv["الاسم"], "")
''')
r = R()
inv = {}
for i in range(1, 51):
    inv[i] = {"رقم الفاتورة": i, "الاسم": "خالد" if i % 2 else "أحمد", "النوع": "صرف ذهب", "الوزن": 1.0,
              "period": "2026-10" if i <= 10 else "2026-11", "settled_status": "ACTIVE", "التاريخ": "x",
              "set_number": f"S{i}", "row_number": str(i), "البيان": "خاص" if i == 33 else ""}
inv[51] = dict(inv[50], **{"رقم الفاتورة": 51, "النوع": "مبيعات ذهب", "رقم الفاتورة اليدوي": "F-1", "الاسم": "زبون"})
inv[52] = dict(inv[51], **{"رقم الفاتورة": 52})
r.invoices = inv
page, more = r.live_recent_page()
assert len(page) == 40 and more and page[0]["رقم الفاتورة"] == 52, "الأحدث أولاً، وفاتورة المبيعات مرة واحدة"
page2, more2 = r.live_recent_page(offset=40)
assert [x["رقم الفاتورة"] for x in page2] == list(range(11, 0, -1)) and not more2
assert {x["period"] for x in r.live_recent_page(period="2026-10")[0]} == {"2026-10"}
assert all(x["الاسم"] == "خالد" for x in r.live_recent_page(name="خالد")[0])
assert [x["رقم الفاتورة"] for x in r.live_recent_page(text="خاص")[0]] == [33]
assert [x["رقم الفاتورة"] for x in r.live_recent_page(text="s7")[0]] == [7], "رقم التشغيل بلا اعتبار لحالة الحروف"
assert [x["رقم الفاتورة"] for x in r.live_recent_page(text="12")[0]][:1] == [12], "ورقم العملية"
assert r.live_recent()[0]["رقم الفاتورة"] == 52
print("✔ العمليات: الأحدث أولاً بصفحات ٤٠، وبالفترة والاسم والبحث (الرقم ورقم التشغيل والبيان)")

# ═══ ٨) الأرصدة ═══
recalc = member("recalculate_all")
ledger = member("treasury_ledger")
assert "self.treasury_ledger(self.current_display_month)" in recalc and "self.current_treasury_balance = treasury_balance" in recalc
assert "self.treasury_bucket(inv, type_sets)" in ledger and "self.get_workers_khayas(month)" in ledger
assert "self.inv_in_period(inv, month)" in ledger and "self.current_display_month" not in ledger, \
    "دفتر الخزينة بالفترة المعطاة وحدها"
bd = member("get_gold_balance_breakdown")
assert 'self.get_current_unclosed_khayas("المصنعين", month)' in bd and "self.get_box_khayas_cumulative(cat, month=month)" in bd
B, _ = make(("live_balances",), extra='''
current_display_month = "2026-11"
current_treasury_balance = 68.0
current_total_gold = 209.5

def treasury_ledger(self, month):
    return 0.0, [], 43.0

def get_gold_balance_breakdown(self, month=None, treasury=None):
    return [("الخزينة", treasury), ("عمال", 5.0), ("صندوق", 2.0)]
''')
b = B()
assert b.live_balances("2026-11") == (68.0, 209.5, [("الخزينة", 68.0), ("عمال", 5.0), ("صندوق", 2.0)]), \
    "فترة الجهاز: أرقام شريطيه نفسها"
assert b.live_balances("2026-10")[:2] == (43.0, 50.0), "فترةٌ أخرى: من دفتر الخزينة وتفصيل الرصيد"
html = member("live_html")
assert "self.live_balance_strip(params, period, periods)" in html
strip = member("live_balance_strip")
assert 'v="bal", c="tr"' in strip and 'v="bal")' in strip and "رصيد الخزينة الحالي" in strip and "الرصيد الحالي" in strip
assert "self.treasury_kind_breakdown(month)" in member("live_view_treasury_kinds")
print("✔ الأرصدة في الرابط: الشريطان بأرقام الجهاز، و«أين الرصيد» وتفصيل الخزينة من مصادر البرنامج نفسها لأي فترة")
print("✔ رابط المدير ← جهاز المصنع 1.99 سليم")
