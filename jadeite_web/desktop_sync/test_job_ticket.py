# -*- coding: utf-8 -*-
"""
رقم التشغيل (الدفعة ١٥): التتبّع، وتذكرة التشغيل، وخانة رقم التشغيل الصديقة لقارئ الباركود.

  • التتبّع: كل حركة تحمل الرقم (بأي صيغة أرقام) + بقية حركات صفّه عند المصنّع/المركّب،
    بلا القيود اليومية ولا صفوف عامل آخر أو فترة أخرى، وبترتيب التاريخ.
  • بيانات التذكرة: أول صرف ذهب للرقم، ومجموع صرفه.
  • البحث عن صف الرقم والتحقق من تكراره يوحّدان الأرقام («٧٧٠٠١» = «77001»).
  • بعد المسح (Enter أو مغادرة الخانة) يُوحَّد الرقم ويُملأ رقم صفّه عند العامل نفسه فقط.
"""
import ast, io, re, sys, textwrap

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


MEMBERS = ["_SET_DIGITS", "normalize_set_number", "scanned_set_number", "JOURNAL_TYPES", "SALE_TYPES", "WORKER_SECTIONS",
           "TRACE_STATUSES", "set_number_trace", "trace_section", "job_ticket_info", "find_row_by_set_number",
           "row_set_numbers", "on_stage_set_number_entered", "stage_selected_set_number"]
ns = {"re": re}
exec("class Base:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in MEMBERS), ns)


class Entry:
    def __init__(self, v=""): self.v = v
    def get(self): return self.v
    def delete(self, a, b): self.v = ""
    def insert(self, i, s): self.v = s + self.v


class Combo(Entry):
    pass


class App(ns["Base"]):
    def __init__(self):
        self.current_display_month = "2026-09"
        self.categories = {"المصنعين": ["سالم", "خالد"], "المركبين": ["مركب"]}
        self.invoices = {}
        self.n = 0

    def inv_period(self, inv): return inv.get("period") or str(inv.get("التاريخ", ""))[:7]
    def inv_in_period(self, inv, m): return self.inv_period(inv) == m
    def clean_name(self, s): return (s or "").strip()

    def add(self, name, t, w, row="", set_no="", dt="2026-09-10 10:00:00", period=None, status="ACTIVE", manual=""):
        self.n += 1
        self.invoices[self.n] = {"رقم الفاتورة": self.n, "الاسم": name, "النوع": t, "الوزن": w, "row_number": row,
                                 "set_number": set_no, "التاريخ": dt, "period": period or dt[:7],
                                 "settled_status": status, "رقم الفاتورة اليدوي": manual}
        return self.n


a = App()
i1 = a.add("سالم", "صرف ذهب", 100.0, "3", "٧٧٠٠١")
i2 = a.add("سالم", "قبض ذهب", 90.0, "3", dt="2026-09-12 10:00:00")
i3 = a.add("سالم", "السلك الراجع", 4.0, "3", dt="2026-09-11 10:00:00")
i4 = a.add("مركب", "صرف ذهب", 90.0, "1", "77001 ", dt="2026-09-14 10:00:00")
i5 = a.add("زبون", "مبيعات ذهب", 85.0, "1", "77001", dt="2026-09-20 10:00:00", manual="S-9")
a.add("زبون", "مبيعات ذهب", 70.0, "1", "55", dt="2026-09-21 10:00:00")        # صف الزبون نفسه برقم آخر
a.add("سالم", "قبض ذهب", 5.0, "3", period="2026-08", dt="2026-08-30 10:00:00")  # الصف نفسه في فترة أخرى
a.add("خالد", "قبض ذهب", 7.0, "3")                                               # الصف نفسه لعامل آخر
a.add("حساب الخزينة", "قيد يومي مدين", 1.0, "", "77001")                        # قيد لا يدخل
a.add("سالم", "صرف ذهب", 9.0, "3", "77001", status="DELETED")                  # حالة غير محاسبية

ids = [m["رقم الفاتورة"] for m in a.set_number_trace("77001")]
assert ids == [i1, i3, i2, i4, i5], ids
assert [m["رقم الفاتورة"] for m in a.set_number_trace("٧٧٠٠١")] == ids
assert a.set_number_trace("") == [] and a.set_number_trace("999") == []
print("✔ التتبّع: الرقم بأي صيغة + حركات صفّه عند المصنّع، بترتيب التاريخ، بلا القيود ولا صفوف غيره")

assert [a.trace_section(a.invoices[i]) for i in (i1, i4, i5)] == ["المصنعين", "المركبين", "المبيعات"]
info = a.job_ticket_info("77001")
assert info["worker"] == "سالم" and info["row"] == "3" and info["section"] == "المصنعين"
assert info["issued"] == 100.0 and info["date"] == "2026-09-10" and info["moves"] == 5, info
assert a.job_ticket_info("404") is None
print("✔ التذكرة: أول صرف ذهب (العامل والصف والتاريخ) وصرف ذلك العامل وحده (لا يُجمع صرف المركّب للذهب نفسه)")

assert a.find_row_by_set_number("المصنعين", "77001") == ("سالم", "3")
assert a.find_row_by_set_number("المصنعين", " ٧٧٠٠١ ") == ("سالم", "3")
assert a.find_row_by_set_number("المركبين", "٧٧٠٠١") == ("مركب", "1")
assert a.row_set_numbers("سالم", "3") == {"77001"}
print("✔ صف الرقم ورفض تكراره يوحّدان الأرقام: «٧٧٠٠١» و«77001» رقم واحد")

# بعد المسح: الرقم يُوحَّد، والصف يُملأ للعامل نفسه فقط ولا يُكتب فوق صفٍّ مكتوب
a.current_op_cat = "المصنعين"
a.combo_op_name = Combo("سالم")
a.current_win_entries = {"رقم التشغيل": Entry("٧٧٠٠١"), "رقم الصف": Entry("")}
a.on_stage_set_number_entered()
assert a.current_win_entries["رقم التشغيل"].get() == "77001" and a.current_win_entries["رقم الصف"].get() == "3"
# مسح رمز QR تذكرة المبيعات في الخانة: يبقى رقم التشغيل وحده
a.current_win_entries = {"رقم التشغيل": Entry("رقم التشغيل: ٧٧٠٠١ | الوزن المقيد: 40.25 جم"), "رقم الصف": Entry("")}
a.on_stage_set_number_entered()
assert a.current_win_entries["رقم التشغيل"].get() == "77001" and a.current_win_entries["رقم الصف"].get() == "3"
a.current_win_entries = {"رقم التشغيل": Entry("77001"), "رقم الصف": Entry("9")}
a.on_stage_set_number_entered()
assert a.current_win_entries["رقم الصف"].get() == "9"
a.combo_op_name = Combo("خالد")
a.current_win_entries = {"رقم التشغيل": Entry("77001"), "رقم الصف": Entry("")}
a.on_stage_set_number_entered()
assert a.current_win_entries["رقم الصف"].get() == "", "رقم عامل آخر لا يملأ الصف (الترحيل يرفضه برسالته)"
a.op_ledger_tree = None
assert a.stage_selected_set_number() == "77001"
print("✔ بعد مسح الباركود: الرقم بأرقام لاتينية، وصفّه المسجّل يُملأ تلقائياً للعامل نفسه")

sub = body("submit_unified_op")
assert "set_typed = self.normalize_set_number(set_entry.get())" in sub
assert 'set_num = self.normalize_set_number(self.current_win_entries["رقم التشغيل"].get())' in sub
render = body("render_unified_fields")
assert 'set_ent.bind("<Return>", self.on_stage_set_number_entered, add="+")' in render
assert 'set_ent.bind("<FocusOut>", self.on_stage_set_number_entered, add="+")' in render
print("✔ الترحيل يحفظ الرقم موحّداً، وخانة رقم التشغيل تستجيب لقارئ الباركود (Enter/مغادرة الخانة)")

ticket = body("print_job_ticket")
assert "code128.Code128(code" in ticket and "qr.QrCodeWidget(code)" in ticket and "(W, H)" in ticket
assert "W, H = 100 * mm, 70 * mm" in ticket and "self._open_file(out_path)" in ticket
assert body("open_set_number_trace").count("self.print_job_ticket(key)") == 1
ctrl = body("_on_ctrl_number_key")
assert '("b", "B")' in ctrl and "keycode\", 0) == 66" in ctrl and "self.open_set_number_trace()" in ctrl
mfg = body("build_mfg_ui")
assert "command=self.print_stage_job_ticket" in mfg and "self.open_set_number_trace(" in mfg
print("✔ التذكرة ١٠٠×٧٠ مم بباركود Code128 ورمز QR بالرقم نفسه، من كشف العامل ونافذة التتبّع، وCtrl+B للتتبّع")

print("\n✅ تتبّع رقم التشغيل وتذكرته سليمان")
