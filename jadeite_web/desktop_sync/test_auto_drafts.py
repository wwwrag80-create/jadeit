# -*- coding: utf-8 -*-
"""1.93: الحفظ التلقائي لما لم يُرحَّل — فاتورة المبيعات قيد الإدخال ونموذجا الوارد والقيود اليومية.

  • تُحفظ بعد كل تغيير بلحظة في ملف محلي بجوار قاعدة البيانات (<قاعدة البيانات>.drafts.json) كتابةً ذرّية،
    ولا تمسّ قاعدة البيانات ولا الحسابات؛ ووضع العرض لا يحفظ ولا يستعيد.
  • تعود عند فتح الشاشة بعد انقطاع الكهرباء أو الإغلاق، وتُمسح لحظة الترحيل أو التعليق أو التصفير.
  • مسودةٌ رُحِّلت فعلاً (انقطاع بين الترحيل ومسحها) لا تعود بلا سؤال — فلا تُرحَّل فاتورة مرتين."""
import ast, datetime, io, json, os, sys, tempfile, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.splitlines()
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))


def flat(text):
    return " ".join(text.split())


class Box:
    answer = False

    def __init__(self):
        self.asked = []

    def askyesno(self, title, msg, **k):
        self.asked.append(msg)
        return self.answer


class Ctk:
    class CTkComboBox:
        pass

    class CTkOptionMenu:
        pass


errors = []
box = Box()
ns = {"os": os, "json": json, "datetime": datetime, "messagebox": box, "ctk": Ctk,
      "log_cloud_error": lambda *a: errors.append(a), "replace_db_file": lambda a, b, attempts=6: os.replace(a, b)}
MEMBERS = ("SALE_KIND_GOLD", "SALE_KIND_DIAMOND", "SALE_KINDS", "SALE_TYPES", "DRAFT_SAVE_DELAY_MS", "DRAFTS_SUFFIX",
           "DRAFT_COLLECTORS", "FORM_DRAFT_FIELDS", "DRAFT_TITLES", "DRAFT_SCREENS", "drafts_path", "drafts_enabled",
           "load_drafts", "write_drafts", "save_draft", "get_draft", "discard_draft", "schedule_draft_save",
           "flush_draft", "flush_all_drafts", "mark_draft_ready", "collect_sales_draft", "sales_draft_posted",
           "restore_sales_draft", "collect_form_draft", "collect_inbound_draft", "collect_journal_draft",
           "restore_form_draft", "notify_saved_drafts", "queue_draft_notice", "show_draft_notice", "collect_sale_form",
           "SALE_DRAFT_FIELDS")
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)


class Entry:
    def __init__(self, v=""):
        self.v = v

    def get(self):
        return self.v

    def delete(self, *a):
        self.v = ""

    def insert(self, _i, v):
        self.v = str(v) + self.v

    def configure(self, **k):
        self.__dict__.update(k)


class Combo(Entry, Ctk.CTkComboBox):
    def set(self, v):
        self.v = v


class App(ns["Base"]):
    def __init__(self, folder, view_only=False):
        self.db_path = os.path.join(folder, "client_data_X.db")
        self.view_only = view_only
        self.invoices, self.pending_sale_rows, self.current_suspended_id = {}, [], None
        self.timers, self.toasts, self.suspended = {}, [], {}
        self._sale_kind = "ذهب"
        for _k, attr in self.SALE_DRAFT_FIELDS:
            setattr(self, attr, Entry())
        self.sale_date, self.sale_invoice_num, self.sale_note = Entry("2026-10-31"), Entry("F-77"), Entry()
        self.sale_name, self.sale_discount_pct = Combo("زبون"), Combo("30%")
        self.lbl_sales_status = Entry()

    # بيئة الواجهة
    def after(self, ms, fn):
        self.tick = getattr(self, "tick", 0) + 1
        tid = f"t{self.tick}"
        self.timers[tid] = fn
        return tid

    def after_cancel(self, tid):
        self.timers.pop(tid, None)

    def run_timers(self):
        while self.timers:
            _tid, fn = self.timers.popitem()
            fn()

    def toast(self, text, kind="info", ms=0, parent=None):
        self.toasts.append(text)

    def current_sale_kind(self):
        return self._sale_kind

    @staticmethod
    def normalize_set_number(v):
        return str(v or "").strip()

    def fill_sale_form(self, data):
        self.filled = data
        self.pending_sale_rows = [dict(r) for r in data.get("rows", [])]
        self._sale_kind = data.get("kind") or "ذهب"

    def get_suspended_sale(self, sid):
        return self.suspended.get(sid)

    def set_current_suspended(self, sid, rec=None):
        self.current_suspended_id = sid

    def refresh_pending_sales_table(self):
        self.schedule_draft_save("sales")


TMP = tempfile.mkdtemp(prefix="drafts_")
a = App(TMP)
path = a.drafts_path()
assert path == a.db_path + ".drafts.json"

# ═══ ١) لا حفظ قبل الاستعادة، ثم حفظ مؤجل يجمع الفاتورة كما هي ═══
a.pending_sale_rows = [{"row_number": "1", "set_number": "88001", "ذهب": 30.0}]
a.refresh_pending_sales_table()
assert not a.timers and not os.path.exists(path), "قبل استعادة مسودة الشاشة لا يُكتب شيء (لا تُمحى المسودة القديمة)"
a.mark_draft_ready("sales")
a.sale_gold.v = "12.5"
a.refresh_pending_sales_table()
a.refresh_pending_sales_table()
assert len(a.timers) == 1, "حفظ واحد مؤجل مهما تتالت التغييرات"
a.run_timers()
saved = json.load(open(path, encoding="utf-8"))
assert saved["sales"]["rows"] == [{"row_number": "1", "set_number": "88001", "ذهب": 30.0}]
assert saved["sales"]["draft"] == {"ذهب": "12.5"} and saved["sales"]["manual_no"] == "F-77"
assert saved["sales"]["kind"] == "ذهب" and saved["sales"]["_saved_at"] and saved["sales"]["suspended_id"] is None
assert not os.path.exists(path + ".tmp"), "الكتابة الذرّية لا تترك الملف المؤقت"
print("✔ الفاتورة قيد الإدخال (سطورها وخانة السطر ورقمها ونوعها) تُحفظ تلقائياً بعد لحظة — حفظ واحد لكل دفعة تغييرات")

# ═══ ٢) «انقطاع الكهرباء»: نسخة جديدة من البرنامج تستعيدها كما كانت ═══
b = App(TMP)
assert b.restore_sales_draft() is True
assert b.pending_sale_rows == [{"row_number": "1", "set_number": "88001", "ذهب": 30.0}] and b.filled["draft"] == {"ذهب": "12.5"}
assert not b.toasts and "المبيعات" in b._draft_notices, "بُنيت الشاشة في الخلفية: الرسالة تنتظر فتحها"
assert "♻️ استُعيدت فاتورة لم تُرحَّل (1 سطر)" in b.show_draft_notice("المبيعات")
assert "♻️ استُعيدت فاتورة لم تُرحَّل (1 سطر)" in b.lbl_sales_status.text and b.toasts
assert b.show_draft_notice("المبيعات") is None, "مرة واحدة"
assert "sales" in b._draft_ready
c = App(TMP)
parts = c.notify_saved_drafts()
assert parts == ["فاتورة مبيعات (1 سطر) في «المبيعات»"] and "يعود عند فتح الشاشة" in c.toasts[-1]
print("✔ بعد الانقطاع: تنبيه عند التشغيل، وشاشة المبيعات تعود بسطورها وخاناتها ونوعها")

# ═══ ٣) الترحيل/التعليق يمسحها فوراً، والتفريغ لا يترك مسودة ═══
b.timers.clear()
b.schedule_draft_save("sales")
assert b.timers
assert b.discard_draft("sales") is True and not b.timers and not os.path.exists(path), "مُسحت ولا حفظ مؤجل يعيدها"
b.pending_sale_rows = []
b.sale_gold.v = ""
b.refresh_pending_sales_table()
b.run_timers()
assert not os.path.exists(path), "فاتورة فارغة لا مسودة لها"
commit = member("commit_sale_invoice")
assert flat('committed_groups = self.post_sale_rows(self.pending_sale_rows, name, full_dt, manual_no, note, kind=kind) '
            '# رُحِّلت: مسودتها التلقائية تُمسح فوراً — لا تعود بعد انقطاع فتُرحَّل مرتين (1.93) '
            'self.discard_draft("sales")') in flat(commit)
assert 'self.discard_draft("sales")' in member("suspend_sale_invoice")
assert 'self.discard_draft("inbound")' in member("submit_inbound")
assert 'self.discard_draft("journal")' in member("submit_journal_entry")
assert "self.wipe_drafts_and_forms()" in member("wipe_system_data")
assert "self.flush_all_drafts()" in member("on_app_closing")
assert "self.after(2500, self.notify_saved_drafts)" in src
assert "self.after_idle(lambda: self.show_draft_notice(name))" in member("navigate_to_screen")
build = member("build_sales_tab")
assert build.rstrip().endswith("self.restore_sales_draft()") and 'self.watch_draft_widgets("sales"' in build
assert 'self.schedule_draft_save("sales")' in member("refresh_pending_sales_table")
assert 'self.restore_form_draft("inbound")' in member("build_inout_tab")
assert 'self.restore_form_draft("journal")' in member("build_journal_entries_tab")
print("✔ الترحيل والتعليق يمسحان المسودة لحظتها، والتصفير والإغلاق والتنبيه موصولة، والوارد والقيود كذلك")

# ═══ ٤) مسودة رُحِّلت فعلاً (انقطاع بين الترحيل ومسحها) لا تعود بلا سؤال ═══
a.discard_draft("sales")
a.pending_sale_rows = [{"row_number": "1", "set_number": "88001", "ذهب": 30.0}]
a.flush_draft("sales")
d = App(TMP)
d.invoices = {1: {"النوع": "مبيعات ذهب", "رقم الفاتورة اليدوي": "F-77", "الاسم": "زبون", "sale_kind": "ذهب",
                  "التاريخ": "2026-10-31 10:00:00", "set_number": "88001"}}
assert d.sales_draft_posted(d.get_draft("sales")) is True
box.answer = False
assert d.restore_sales_draft() is False and box.asked and not os.path.exists(path), "رُحِّلت: تُحذف بعد السؤال"
d.invoices[1]["set_number"] = "99999"
a.flush_draft("sales")
assert d.sales_draft_posted(d.get_draft("sales")) is False, "رقم تشغيل لم يُرحَّل ← ليست مرحّلة"
d.invoices[1]["set_number"] = "88001"
d.invoices[1]["sale_kind"] = "الماس"
assert d.sales_draft_posted(d.get_draft("sales")) is False, "النوع غير النوع"
a.discard_draft("sales")
print("✔ مسودةٌ يبدو أنها رُحِّلت (الرقم والاسم والتاريخ والنوع وأرقام التشغيل) لا تعود إلا بموافقة — لا ترحيل مرتين")

# ═══ ٥) الفاتورة المعلّقة المفتوحة تعود معلّقةً مفتوحة (ترحيلها يحذفها من المعلقات) ═══
a.current_suspended_id = 7
a.flush_draft("sales")
e = App(TMP)
e.suspended = {7: {"manual_no": "F-77"}}
assert e.restore_sales_draft() and e.current_suspended_id == 7
f = App(TMP)
assert f.restore_sales_draft() and f.current_suspended_id is None, "معلّقة حُذفت بعدها: تعود فاتورة عادية"
a.current_suspended_id = None
a.discard_draft("sales")
print("✔ الفاتورة المعلّقة المفتوحة تعود مربوطة بمعلّقتها، وإن حُذفت المعلّقة تعود فاتورة عادية")

# ═══ ٦) نموذجا الوارد والقيود: الخانات الافتراضية وحدها لا تصنع مسودة ═══
g = App(TMP)
g.in_date, g.in_supplier, g.in_invoice_num = Entry("2026-10-31"), Combo("المصنع"), Entry("V-1")
g.in_type, g.in_to_account = Combo("ذهب"), Combo("الخزينة")
g.in_weight, g.in_carat, g.in_note = Entry(), Entry(), Entry()
assert g.collect_inbound_draft() is None
g.in_weight.v, g.in_carat.v, g.in_supplier.v = "105.5", "21", "مورد أ"
g.mark_draft_ready("inbound")
g.schedule_draft_save("inbound")
g.run_timers()
h = App(TMP)
h.in_date, h.in_supplier, h.in_invoice_num = Entry("2026-11-01"), Combo("المصنع"), Entry("")
h.in_type, h.in_to_account = Combo("ذهب"), Combo("الخزينة")
h.in_weight, h.in_carat, h.in_note = Entry(), Entry(), Entry()
h.toggled = []
h.toggle_in_carat_field = h.toggled.append
assert h.restore_form_draft("inbound") is True
assert (h.in_weight.v, h.in_carat.v, h.in_supplier.v, h.in_invoice_num.v, h.in_date.v) == (
    "105.5", "21", "مورد أ", "V-1", "2026-10-31") and h.toggled == ["ذهب"]
h.discard_draft("inbound")
h.je_date, h.je_from_name, h.je_to_name, h.je_amount, h.je_note = Entry("2026-10-31"), Combo(""), Combo(""), Entry(), Entry()
assert h.collect_journal_draft() is None
h.je_amount.v = "3.25"
assert h.collect_journal_draft() == {"fields": {"je_date": "2026-10-31", "je_from_name": "", "je_to_name": "",
                                                "je_amount": "3.25", "je_note": ""}}
print("✔ الوارد والقيود اليومية: ما كُتب ولم يُرحَّل يعود إلى خاناته (والتاريخ والاسم الافتراضيان وحدهما لا مسودة)")

# ═══ ٧) وضع العرض لا يحفظ ولا يستعيد، والملف التالف لا يوقف الشاشة ═══
v = App(TMP, view_only=True)
v.mark_draft_ready("sales")
v.pending_sale_rows = [{"set_number": "1"}]
v.schedule_draft_save("sales")
assert not v.timers and v.save_draft("sales", {"x": 1}) is False and v.get_draft("sales") is None
with open(path, "w", encoding="utf-8") as fh:
    fh.write("{تالف")
w = App(TMP)
assert w.load_drafts() == {} and w.restore_sales_draft() is False and "sales" in w._draft_ready
os.remove(path)
print("✔ وضع العرض لا يكتب مسودة ولا يستعيدها، وملفٌ تالف يُتجاهل بلا خطأ")

print("\n✅ 1.93: الحفظ التلقائي لما لم يُرحَّل — يعود بعد انقطاع الكهرباء ويُمسح عند الترحيل")
