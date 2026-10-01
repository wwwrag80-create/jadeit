# -*- coding: utf-8 -*-
"""
إصلاحات المراجعة الشاملة (الدفعة ١٤) — من دوال البرنامج نفسه:

  ١) المرجع ٧٥٠: سلك كل صف بعياره (لا مجموع السلك بآخر عيار)، والصف بلا عيار يأخذ آخر
     عيار للعامل في الفترة — مصدر واحد لكشف العامل وصناديق الخياس والنافذة القديمة.
  ٢) التعديل لا ينقل الحركات لفترة أخرى: فاتورة المبيعات وحركات نوافذ التعديل تبقى في
     فترتها الأصلية، والخانة الجديدة في نافذة الحركة المجمّعة تنضمّ لصفّها.
  ٣) القيد اليومي يُعدَّل ويُحذف بطرفيه معاً من نافذة الحركة، وحركة المبيعات تُفتح بفاتورتها.
  ٤) التاريخ: صيغة واحدة YYYY-MM-DD في كل شاشات الترحيل، والأرقام الهندية تُحوَّل.
  ٥) كشف صندوق المصنعين/المركبين = الفاقد الحالي في شاشة الخسائر (أسطر المعادلة).
  ٦) الذهب عند القسم بفترته، وحذف حركات اسم يطابق القاعدة في الذاكرة.
"""
import ast, io, sys, textwrap, datetime

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def body(name):
    return ast.get_source_segment(src, node(name))


def member_src(name):
    x = node(name)
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(x, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, x))


raji_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "raji_ayar")
ns = {"RAJI_PURITY": 750.0, "ALLOWANCE_8": 0.008, "ALLOWANCE_4": 0.004, "datetime": datetime}
exec(ast.get_source_segment(src, raji_fn), ns)


class Box:
    msgs = []

    @staticmethod
    def showwarning(*a, **k):
        Box.msgs.append(a)


ns["messagebox"] = Box
members = ["worker_rows_raji", "calculate_single_ledger", "inv_period", "inv_in_period", "invoices_by_name",
           "_DATE_DIGITS", "read_entry_date"]
exec("class S:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in members), ns)
S = ns["S"]


def inv(i, name, t, w, row, dt="2026-09-05 10:00:00", period="2026-09", status="ACTIVE"):
    return {"رقم الفاتورة": i, "الاسم": name, "النوع": t, "الوزن": w, "row_number": row, "التاريخ": dt,
            "period": period, "settled_status": status, "set_number": ""}


# ═══ ١) المرجع ٧٥٠ صفاً بصف ═══
app = S()
app.current_display_month = "2026-09"
app.categories = {"المركبين": ["سالم"]}
app.invoices = {i: x for i, x in enumerate([
    inv(1, "سالم", "صرف ذهب", 100.0, "1"), inv(2, "سالم", "السلك الراجع", 10.0, "1"),
    inv(3, "سالم", "العيار بعد الفحص", 900.0, "1"),
    inv(4, "سالم", "صرف ذهب", 100.0, "2", dt="2026-09-06 10:00:00"),
    inv(5, "سالم", "السلك الراجع", 10.0, "2", dt="2026-09-06 10:00:00"),
    inv(6, "سالم", "العيار بعد الفحص", 600.0, "2", dt="2026-09-06 10:00:00"),
], 1)}
rows, last = S.worker_rows_raji(app.invoices.values())
assert rows == {"1": 12.0, "2": 8.0} and last == 600.0, (rows, last)
led = app.calculate_single_ledger("سالم", "المركبين")
assert led["المرجع 750"] == 20.0, led["المرجع 750"]          # القديم: 20 سلك × 600 ÷ 750 = 16
print("✔ عياران في الشهر: 10×900÷750 + 10×600÷750 = 20 (كان كل السلك بآخر عيار = 16)")

app.invoices[7] = inv(7, "سالم", "السلك الراجع", 5.0, "3", dt="2026-09-07 10:00:00")
assert app.calculate_single_ledger("سالم", "المركبين")["المرجع 750"] == 24.0
print("✔ صف بسلك بلا عيار يأخذ آخر عيار للعامل في الفترة (5×600÷750 = 4) — كما يسجّل من يكتب العيار مرة")

app.invoices = {1: inv(1, "سالم", "السلك الراجع", 10.0, "1"), 2: inv(2, "سالم", "العيار بعد الفحص", 750.0, "9")}
assert app.calculate_single_ledger("سالم", "المركبين")["المرجع 750"] == 10.0
print("✔ العيار في صف مستقل والسلك في صف آخر: يُطبَّق العيار (السلوك السابق محفوظ)")

ledger_src = body("refresh_op_ledger_table")
assert "self.worker_rows_raji(worker_invs)" in ledger_src and "raji_rows.get(gkey, 0.0)" in ledger_src
assert "raji_ayar(data['سلك راجع'], data['عيار'])" not in ledger_src
window = body("open_worker_ledger_window")
assert "self.worker_rows_raji(worker_invs)" in window and "- raji_v" in window
print("✔ كشف حركة العامل ونافذة الحركة القديمة من المصدر نفسه (والنافذة صارت تخصم الراجع/عيار)")

# ═══ ٢) التعديل يبقي الفترة ═══
editor = body("open_sale_invoice_editor")
assert "old_period = self.inv_period(" in editor and "period=old_period" in editor
post = body("post_sale_rows")
assert "period=None" in post and 'record["period"] = period' in post
assert post.count("store(") == 6           # التعريف + خمس حركات (مبيعات، بوليش، مركب، صافي، خياس)
stage = body("open_stage_op_edit_dialog")
assert stage.count('"period": ref_period') == 2
assert '"row_number": new_row_no, "period": month' in body("open_row_full_edit_dialog")
assert '"row_number": ref_row, "period": ref_period' in window
print("✔ فاتورة المبيعات تبقى في فترتها عند تعديلها من البحث/التدقيق، وكل حركة جديدة في نوافذ التعديل "
      "بفترة صفّها، والخانة الجديدة في نافذة الحركة المجمّعة برقم صفّها")


class Rec:
    """تجربة سلوكية: post_sale_rows يختم الفترة الممرَّرة على كل الحركات"""
    def __init__(self):
        self.invoices, self.invoice_counter, self.saved = {}, 0, []

    def sale_bayan(self, base, note):
        return base

    def save_invoice_to_db(self, i, d):
        self.saved.append(dict(d))
        return True


ns2 = {"sale_net_weight": lambda r: 1.0, "MEMO_STATUS": "MEMO", "KHAYAS_MARK_POLISH": 7.0,
       "KHAYAS_MARK_ASSEMBLER": 5.0, "KHAYAS_MARK_NET": 9.0, "KHAYAS_MARK_FINAL": 0.0}
exec("class P(Rec):\n" + textwrap.indent(member_src("post_sale_rows"), "    "), dict(ns2, Rec=Rec), ns2)
p = ns2["P"]()
p.post_sale_rows([{"ذهب": 10.0, "فصوص": 1.0, "خياس": 0.5, "خياس البوليش": 0.2, "خياس المركب": 0.1,
                   "set_number": "7", "row_number": "1"}], "زبون", "2026-07-10 10:00:00", "S-1", period="2026-07")
assert len(p.saved) == 6 and {d.get("period") for d in p.saved} == {"2026-07"}, p.saved
q = ns2["P"]()
q.post_sale_rows([{"ذهب": 10.0, "set_number": "7", "row_number": "1"}], "زبون", "2026-07-10 10:00:00", "S-1")
assert all("period" not in d for d in q.saved)
print("✔ الحركات الست لسطر الفاتورة تُختم بفترتها الأصلية عند التعديل، والترحيل الجديد بلا فترة كما كان")

# ═══ ٣) القيد اليومي بطرفيه، وحركة المبيعات بفاتورتها ═══
gen = body("open_edit_invoice_ui")
assert "partner = self.journal_partner(" in gen
assert 'partner["الوزن"] = inv["الوزن"]' in gen and 'self.delete_invoice_from_db(partner["رقم الفاتورة"])' in gen
assert "self.open_sale_invoice_editor(key)" in gen and 'inv["النوع"] in self.SALE_TYPES' in gen
assert "if new_w < 0:" in gen and "valid_date(entry_date.get())" in gen
print("✔ نافذة الحركة: القيد يُعدَّل ويُحذف بطرفيه، وحركة المبيعات تُفتح بفاتورتها، والوزن السالب والتاريخ الخاطئ يُرفضان")

# ═══ ٤) التاريخ ═══
d = S()
assert d.read_entry_date("٢٠٢٦-١٠-٠١") == "2026-10-01"
assert d.read_entry_date("2026/10/1") == "2026-10-01" and d.read_entry_date(" 2026-09-30 ") == "2026-09-30"
assert d.read_entry_date("2026-13-01") is None and d.read_entry_date("") is None and Box.msgs
for fn in ("submit_unified_op", "submit_casting_loss_op", "submit_casting_recovery_op", "submit_polish_op",
           "submit_polish_buff_op", "submit_generic_stage_op", "submit_inbound", "submit_journal_entry",
           "commit_sale_invoice"):
    assert "self.read_entry_date(" in body(fn), fn
print("✔ التاريخ بصيغة واحدة في شاشات الترحيل التسع (الأرقام الهندية تُحوَّل، والشهر ١٣ يُرفض)")

# ═══ ٥) كشف صندوق العمال بأسطر المعادلة ═══
rows_all = body("_account_ledger_rows_all")
assert "self.get_section_khayas_parts(cat, target_month=period)" in rows_all
assert '"المرجع ٧٥٠"' in rows_all and '"الخياس الموجب"' in rows_all
assert '{"قبض ذهب"} if cat == "المركبين"' in rows_all
print("✔ كشف صندوق المصنعين/المركبين يُكمل المعادلة في آخر كل فترة فيطابق بطاقة شاشة الخسائر")

# ═══ ٦) الذهب عند القسم، وحذف حركات اسم ═══
assert "get_box_closed_total(cat_name, month=self.current_display_month)" in body("get_gold_at_section")
dw = body("delete_worker_from_db")
assert 'v.get("settled_status") == "ACTIVE"' in dw and "settled_status = 'ACTIVE'" in dw
print("✔ الذهب عند القسم يطرح إقفالات فترته فقط، وحذف حركات اسم يطابق القاعدة في الذاكرة")

print("\n✅ إصلاحات المراجعة الشاملة سليمة")
