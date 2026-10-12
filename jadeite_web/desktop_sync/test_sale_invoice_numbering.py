# -*- coding: utf-8 -*-
"""
ترقيم فواتير المبيعات تلقائياً (الدفعة ٣٠): يُختار رقم البداية مرة (🔢 بجوار «رقم الفاتورة») فيُحفظ،
ثم تأخذ كل فاتورة جديدة الرقم التالي — بعد الترحيل، وبعد تعليق فاتورة، وعند فتح الشاشة — بلا تكرار رقم
مستخدم (مرحّلاً أو معلّقاً)، وبالبادئة وعدد الخانات نفسيهما. بلا رقم بداية: الإدخال اليدوي كما كان.
"""
import ast, io, re, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.split("\n")
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))


MEMBERS = ("SALE_TYPES", "SALE_KIND_GOLD", "SALE_KIND_DIAMOND", "SALE_KINDS", "SALE_DIAMOND_TYPES",
           "SALE_NO_START_KEY", "SALE_NO_START_KEYS", "SALE_NO_DEFAULT_START", "sale_kind_inferred", "sale_key_of",
           "current_sale_kind", "set_sale_kind", "split_invoice_number", "sale_invoice_start_saved",
           "sale_invoice_start", "posted_sale_invoice_numbers", "used_sale_invoice_numbers",
           "next_sale_invoice_number", "fill_next_sale_invoice_number", "suggest_sale_invoice_start",
           "set_sale_invoice_start")
prefs = {}
ns = {"re": re, "save_ui_pref": prefs.__setitem__}
exec("class App:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)


class Entry:
    def __init__(self, v=""): self.v = v
    def get(self): return self.v
    def delete(self, *a): self.v = ""
    def insert(self, _i, v): self.v = str(v) + self.v


class App(ns["App"]):
    def __init__(self):
        self.settings, self.invoices, self.suspended = {}, {}, []
        self.sale_invoice_num = Entry()

    def get_setting(self, key, default=None): return self.settings.get(key, default)
    def set_setting(self, key, value): self.settings[key] = str(value)
    def list_suspended_sales(self): return self.suspended

    def post(self, no, t="مبيعات ذهب", kind="", date="2026-10-01 10:00:00", name="المصنع"):
        self.invoices[len(self.invoices) + 1] = {"رقم الفاتورة اليدوي": no, "النوع": t, "sale_kind": kind,
                                                 "التاريخ": date, "الاسم": name}


a = App()
# ═══ ١) بلا رقم بداية: الإدخال اليدوي كما كان ═══
assert a.next_sale_invoice_number() == "" and a.fill_next_sale_invoice_number() == "" and a.sale_invoice_num.v == ""
print("✔ بلا رقم بداية: لا ترقيم تلقائي — يُكتب الرقم يدوياً كما كان")

# ═══ ٢) رقم البداية يُحفظ، والفاتورة الأولى تأخذه ثم التالي ═══
assert a.split_invoice_number("F-0042") == ("F-", 42, 4) and a.split_invoice_number("ABC") is None
assert not a.set_sale_invoice_start("بدون رقم") and a.sale_invoice_start() == ""
assert a.set_sale_invoice_start("1001") and a.settings["sale_invoice_start"] == "1001"
assert a.fill_next_sale_invoice_number() == "1001" and a.sale_invoice_num.v == "1001"
a.post("1001"); a.post("1001", "خياس طقوم")
assert a.next_sale_invoice_number() == "1002"
a.sale_invoice_num.v = ""
a.fill_next_sale_invoice_number()
assert a.sale_invoice_num.v == "1002"
a.sale_invoice_num.v = "يدوي-7"
assert a.fill_next_sale_invoice_number() == "1002" and a.sale_invoice_num.v == "يدوي-7"     # لا يمسح ما كُتب
assert a.fill_next_sale_invoice_number(force=True) == "1002" and a.sale_invoice_num.v == "1002"
print("✔ رقم البداية 1001 يُحفظ؛ الفاتورة الأولى 1001 ثم 1002 — ولا يُمسح رقم كتبه المستخدم إلا بالأمر")

# ═══ ٣) المعلّقة تحجز رقمها، والرقم المكتوب يدوياً من السلسلة يُتخطّى ═══
a.suspended = [{"manual_no": "1002"}]
assert a.next_sale_invoice_number() == "1003"
a.post("1007")
assert a.next_sale_invoice_number() == "1008"
a.post("950")                                  # أقل من البداية: لا يغيّر شيئاً
a.post("F-2000")                               # سلسلة أخرى (بادئة مختلفة)
assert a.next_sale_invoice_number() == "1008"
print("✔ الفاتورة المعلّقة تحجز رقمها (1002 ← التالي 1003)، ولا يتكرر رقم مستخدم (بعد 1007 ← 1008)")

# ═══ ٤) تغيير البداية: البادئة والخانات تبقى، والبداية الأعلى تبدأ منها ═══
assert a.set_sale_invoice_start("5000") and a.next_sale_invoice_number() == "5000"
assert a.set_sale_invoice_start("F-0001") and a.next_sale_invoice_number() == "F-2001"
b = App()
b.set_sale_invoice_start("INV-0098")
b.post("INV-0098"); b.post("INV-0099")
assert b.next_sale_invoice_number() == "INV-0100" and b.next_sale_invoice_number("INV-0500") == "INV-0500"
assert b.suggest_sale_invoice_start() == "1"
a2 = App(); a2.post("3050"); a2.post("F-9")
assert a2.suggest_sale_invoice_start() == "3051"
assert a.set_sale_invoice_start("") and a.next_sale_invoice_number() == ""
print("✔ البادئة وعدد الخانات تبقى (INV-0099 ← INV-0100)، والبداية الأعلى تبدأ منها (5000)، والاقتراح أول مرة "
      "بعد أكبر رقم مستخدم (3051)، و«إيقاف الترقيم» يعيد الإدخال اليدوي")

# ═══ ٥) في الشاشة: الزر، وعند الفتح، وبعد الترحيل، وبعد التعليق ═══
assert "command=self.open_sale_invoice_start_dialog" in src
i = src.index("self.sale_invoice_num = ctk.CTkEntry(")
assert "self.fill_next_sale_invoice_number()" in src[i:i + 900]
commit = member("commit_sale_invoice")
assert commit.index("self.sale_invoice_num.delete(0, 'end')") < commit.index("self.fill_next_sale_invoice_number()")
assert '"manual_no": self.next_sale_invoice_number()' in member("clear_sale_form")
dlg = member("open_sale_invoice_start_dialog")
assert "self.set_sale_invoice_start(ent.get(), kind=kind)" in dlg and "self.set_sale_invoice_start(\"\", kind=kind)" in dlg
assert "fill_next_sale_invoice_number(force=True, kind=kind)" in dlg and 'getattr(self, "current_suspended_id", None)' in dlg
print("✔ الشاشة: زر 🔢 بجوار «رقم الفاتورة» لرقم البداية (حفظ أو إيقاف)، والرقم التالي عند فتح الشاشة "
      "وبعد كل ترحيل وبعد تعليق فاتورة — والفاتورة المعلّقة المفتوحة تبقى برقمها")

# ═══ ٦) نوع العملية (ذهب/الماس): لكل نوع ترقيمه المستقل ═══
G, D = "ذهب", "الماس"
c = App()
assert c.current_sale_kind() == G and c.next_sale_invoice_number(kind=D) == ""     # لا ترقيم في أي نوع: يدوي
assert c.set_sale_invoice_start("1001") and c.settings == {"sale_invoice_start": "1001"}   # الذهب بمفتاحه الأصلي
c.post("1001", kind=G); c.post("1002", kind=G)
# الالماس بلا بداية والترقيم التلقائي مستخدم في الذهب: تلقائي من 1 بسلسلته وحدها
assert c.next_sale_invoice_number(kind=D) == "1" and c.next_sale_invoice_number(kind=G) == "1003"
c.post("1", "مبيعات الماس", kind=D); c.post("1", "خياس طقوم", kind=D)
c.post("2", "مبيعات ذهب مع الماس", kind=D)
assert c.next_sale_invoice_number(kind=D) == "3" and c.next_sale_invoice_number(kind=G) == "1003"
# فاتورة ذهب بالرقم 3 لا تمسّ ترقيم الالماس
c.post("3", kind=G)
assert c.next_sale_invoice_number(kind=D) == "3"
print("✔ لكل نوع ترقيمه: الذهب 1001 ← 1003، والالماس 1 ← 3 بسلسلته وحدها (رقم ذهب لا يحجز رقم الماس)")

# فاتورة أقدم بلا نوع محفوظ: فيها ماس ← الماس، وإلا ذهب
c.post("7", "مبيعات الماس"); c.post("7", "مبيعات ذهب مع الماس")
c.post("1010", "مبيعات ذهب"); c.post("1010", "مبيعات فصوص وأحجار")
assert c.next_sale_invoice_number(kind=D) == "8" and c.next_sale_invoice_number(kind=G) == "1011"
assert c.posted_sale_invoice_numbers(D) == {"1", "2", "7"}
assert c.sale_key_of(c.invoices[1]) == ("1001", "2026-10-01 10:00:00", "المصنع", G)
print("✔ الفواتير الأقدم (قبل خانة النوع) بنوعها المستنتج: فيها ماس ← الماس، وإلا ذهب")

# المعلّقة تحجز رقمها في نوعها وحده
c.suspended = [{"manual_no": "1011", "kind": G}, {"manual_no": "9", "kind": D}]
assert c.next_sale_invoice_number(kind=G) == "1012" and c.next_sale_invoice_number(kind=D) == "10"
# بداية مستقلة لكل نوع، وإيقاف ترقيم نوع لا يوقف الآخر
c._sale_kind = D
assert c.set_sale_invoice_start("D-001") and c.settings["sale_invoice_start_diamond"] == "D-001"
assert c.next_sale_invoice_number() == "D-001" and c.next_sale_invoice_number(kind=G) == "1012"
assert c.suggest_sale_invoice_start() == "10"            # بعد أكبر رقم الماس مستخدم (9 معلّقة)
assert c.set_sale_invoice_start("", kind=G) and c.next_sale_invoice_number(kind=G) == ""
assert c.next_sale_invoice_number(kind=D) == "D-001"
print("✔ بداية مستقلة لكل نوع (الماس D-001 والذهب 1001)، والمعلّقة تحجز رقمها في نوعها، وإيقاف نوع لا يمسّ الآخر")

# تبديل النوع في الشاشة: الرقم التلقائي يتبدّل، والمكتوب يدوياً يبقى
e = App()
e.set_sale_invoice_start("500")
e.post("500", kind=G)
e.fill_next_sale_invoice_number()
assert e.sale_invoice_num.v == "501"
e.set_sale_kind(D)
assert e.current_sale_kind() == D and e.sale_invoice_num.v == "1" and prefs["sale_kind"] == D
e.set_sale_kind(G)
assert e.sale_invoice_num.v == "501"
e.sale_invoice_num.v = "خاص-1"
e.set_sale_kind(D)
assert e.sale_invoice_num.v == "خاص-1"
e.set_sale_kind("غير معروف")
assert e.current_sale_kind() == G
print("✔ تبديل «نوع العملية» يضع رقم فاتورة النوع الجديد تلقائياً، ولا يمسّ رقماً كُتب يدوياً")

# ═══ ٧) في الشاشة: خانة النوع قبل رقم الفاتورة، والترحيل بنوعه ═══
build = src[src.index("    def build_sales_tab(self):"):src.index("    def switch_sales_subtab(self, key):")]
assert build.index('head_label("التاريخ:")') < build.index('head_label("نوع العملية:")') < build.index('head_label("رقم الفاتورة:")')
assert "command=lambda k=kind: self.set_sale_kind(k)" in build
commit = member("commit_sale_invoice")
assert "kind = self.current_sale_kind()" in commit and "self.posted_sale_invoice_numbers(kind)" in commit
assert "self.post_sale_rows(self.pending_sale_rows, name, full_dt, manual_no, note, kind=kind)" in commit
dlg = member("open_sale_invoice_start_dialog")
assert "kind = self.current_sale_kind()" in dlg and "self.set_sale_invoice_start(ent.get(), kind=kind)" in dlg
print("✔ «نوع العملية» بعد التاريخ وقبل رقم الفاتورة؛ الترحيل بنوعه والتكرار داخل النوع؛ و🔢 لترقيم النوع المختار")

print("\n✅ ترقيم فواتير المبيعات تلقائياً من رقم البداية المحفوظ — بلا تكرار، ولكل نوع (ذهب/الماس) ترقيمه")
