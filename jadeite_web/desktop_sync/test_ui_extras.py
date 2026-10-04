# -*- coding: utf-8 -*-
"""
إضافات الواجهة (الدفعة ١٧) — من دوال البرنامج نفسها:

  • البحث الشامل (Ctrl+F): اسم حساب، رقم تشغيل (بأي صيغة أرقام أو بمسح الباركود)، رقم فاتورة
    مبيعات، أو رقم حركة — والنتيجة تفتح ما وُجد (كشف الحساب، تتبّع الرقم، معاينة الفاتورة، التعديل).
  • القيود والمحذوف لا تظهر في البحث، ولكل رقم تشغيل وكل فاتورة نتيجة واحدة، والمطابق تماماً أولاً.
  • أي جدول يُطبع PDF من قائمة الزر الأيمن بقالب الطباعة الموحّد، بعنوان نافذته أو شاشته.
  • أداء العمال: منحنى العامل المحدد مقابل متوسط قسمه لكل فترة.
"""
import ast, datetime, io, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree_ast = ast.parse(src)
cls = next(n for n in tree_ast.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def member_src(name):
    x = node(name)
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(x, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, x))


def body(name):
    return ast.get_source_segment(src, node(name))


ns = {"datetime": datetime, "sys": sys, "IS_ADMIN_BUILD": False}
MEMBERS = ["_SET_DIGITS", "normalize_set_number", "scanned_set_number", "TRACE_STATUSES", "JOURNAL_TYPES", "SALE_TYPES",
           "SEARCH_LIMIT", "global_search", "open_account_statement_for", "table_title", "print_tree",
           "sale_invoice_groups", "_SHORTCUT_DIGITS", "_on_ctrl_number_key"]
exec("class Base:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in MEMBERS), ns)


class App(ns["Base"]):
    def __init__(self):
        self.invoices, self.calls = {}, []

    def get_account_statement_options(self):
        return ["سالم", "سالم الصغير", "حساب الخزينة", "المبيعات", "مؤسسة الندى"]

    def inv_period(self, inv):
        return str(inv.get("التاريخ", ""))[:7]

    def add(self, iid, name, t, w, set_no="", manual="", dt="2026-09-10 10:00:00", status="ACTIVE"):
        self.invoices[iid] = {"رقم الفاتورة": iid, "الاسم": name, "النوع": t, "الوزن": w, "set_number": set_no,
                              "رقم الفاتورة اليدوي": manual, "التاريخ": dt, "settled_status": status}

    def get_sale_invoice_records(self, key):
        return [i for i in self.invoices.values() if (i["رقم الفاتورة اليدوي"], i["التاريخ"], i["الاسم"]) == key]

    def open_set_number_trace(self, x=None): self.calls.append(("trace", x))
    def preview_invoice_groups(self, groups): self.calls.append(("preview", groups))
    def open_edit_invoice_ui(self, i): self.calls.append(("edit", i))
    def open_global_search(self): self.calls.append(("search",))
    def navigate_to_screen(self, s): self.calls.append(("nav", s))
    def refresh_account_statement(self): self.calls.append(("refresh", self.kh_account_name.v))
    def toast(self, text, kind="info", ms=0, parent=None): self.calls.append(("toast", kind, text))


a = App()
a.add(1, "سالم", "صرف ذهب", 50.0, "٨٨٠٠١")
a.add(2, "سالم", "قبض ذهب", 49.0, "88001")
a.add(3, "خالد", "صرف ذهب", 30.0, "188001")
a.add(4, "مؤسسة الندى", "مبيعات ذهب", 41.15, "88001", manual="7001", dt="2026-09-20 11:00:00")
a.add(5, "مؤسسة الندى", "مبيعات ذهب", 12.0, "88002", manual="7001", dt="2026-09-20 11:00:00")
a.add(6, "حساب الخزينة", "قيد يومي مدين", 5.0, "88077")                    # قيد: لا يظهر رقمه
a.add(7, "خالد", "صرف ذهب", 9.0, "88009", status="DELETED")               # محذوف: لا يظهر
a.add(8, "عميل", "مبيعات الماس", "3.5", manual="17001", dt="2026-09-21 09:00:00")

r = a.global_search("88001")
kinds = [(k, v) for k, v, _d, _a in r]
assert kinds == [("رقم تشغيل", "88001"), ("رقم تشغيل", "188001")], kinds
assert r[0][2] == "سالم — 2026-09", "تفاصيل أول ظهور للرقم"
r[0][3]()
assert a.calls[-1] == ("trace", "88001")
assert [v for k, v, _d, _x in a.global_search("٨٨٠٠١") if k == "رقم تشغيل"] == ["88001", "188001"]
assert not any(v == "88009" for _k, v, _d, _x in a.global_search("8800")), "المحذوف لا يظهر"
assert a.global_search("رقم التشغيل: 88001 | الوزن المقيد: 40.25 جم")[0][:2] == ("رقم تشغيل", "88001"), "مسح QR التذكرة"
assert not any(v == "88077" for _k, v, _d, _x in a.global_search("880")), "رقم القيد لا يظهر"
print("✔ رقم التشغيل يُبحث بأي صيغة أرقام (أو بمسح باركوده)، نتيجة واحدة لكل رقم والمطابق تماماً أولاً، "
      "والقيود والمحذوف لا تظهر — والنتيجة تفتح تتبّع الرقم")

r = a.global_search("7001")
sales = [(v, d) for k, v, d, _x in r if k == "فاتورة مبيعات"]
assert sales == [("7001", "مؤسسة الندى — 2026-09-20"), ("17001", "عميل — 2026-09-21")], sales
next(x for k, v, d, x in r if v == "7001")()
assert a.calls[-1] == ("preview", [("88001", "2026-09-20 11:00:00", "مؤسسة الندى"),
                                   ("88002", "2026-09-20 11:00:00", "مؤسسة الندى")])
print("✔ رقم فاتورة المبيعات: نتيجة واحدة للفاتورة كلها، تفتح معاينتها بكل أرقام تشغيلها")

r = a.global_search("8")
assert r[0][0] == "حركة" and r[0][1] == "8" and r[0][2] == "عميل — مبيعات الماس — 3.50", r[0]
r[0][3]()
assert a.calls[-1] == ("edit", 8)
a.add(4, "مؤسسة الندى", "مبيعات ذهب", 41.15, "88001", manual="7001", dt="2026-09-20 11:00:00")
a.add(5, "مؤسسة الندى", "مبيعات ذهب", 12.0, "88002", manual="7001", dt="2026-09-20 11:00:00")
a.add(88001, "سالم", "قبض ذهب", 1.0, "")                 # رقم حركة يساوي رقم تشغيل
assert [k for k, v, _d, _x in a.global_search("٨٨٠٠١")][:2] == ["رقم تشغيل", "حركة"]
del a.invoices[88001]
assert a.global_search("999") == [] and a.global_search("  ") == []
print("✔ المطابق تماماً أولاً (رقم حركة بعينه يفتح تعديلها، والوزن المحفوظ نصاً يُعرض رقماً)، وعند تساوي رقم "
      "التشغيل ورقم الحركة فرقم التشغيل أولاً (مسح التذكرة ثم Enter)، والبحث الفارغ بلا نتائج")


class Combo:
    v = ""
    def set(self, v): self.v = v


r = a.global_search("سالم")
assert [v for k, v, _d, _x in r] == ["سالم", "سالم الصغير"] and r[0][0] == "حساب"
a.kh_account_name = Combo()
r[1][3]()
assert a.calls[-2:] == [("nav", "كشف حساب"), ("refresh", "سالم الصغير")]
print("✔ اسم الحساب يفتح «كشف حساب» عليه مباشرة")

a.add(100, "x", "صرف ذهب", 1.0, "")
for n in range(200):
    a.add(1000 + n, "y", "صرف ذهب", 1.0, f"55{n:03d}")
assert len(a.global_search("55")) == a.SEARCH_LIMIT == 60
print("✔ النتائج محدودة بـ ٦٠ (البحث سريع مع كل حرف)")


# ═══ Ctrl+F ═══
class Ev:
    def __init__(self, keysym, keycode=0): self.keysym, self.keycode, self.char = keysym, keycode, ""


assert a._on_ctrl_number_key(Ev("f")) == "break" and a.calls[-1] == ("search",)
assert a._on_ctrl_number_key(Ev("F")) == "break"
if sys.platform.startswith("win"):
    assert a._on_ctrl_number_key(Ev("ب", 70)) == "break"
assert "Ctrl + F" in body("SHORTCUTS") and "طباعة PDF" in body("SHORTCUTS")
assert 'text="🔍 بحث", width=86' in src and "command=self.open_global_search)" in src
win = body("open_global_search")
assert "win.after(220, run)" in win and 'entry.bind("<Return>", activate)' in win and "win.destroy()\n" in win
print("✔ Ctrl+F (بأي لغة كتابة) وزر «🔍 بحث» في الشريط العلوي يفتحان نافذة واحدة، تبحث مع الكتابة "
      "وEnter يفتح المحدد — مسجّل في F1")


# ═══ طباعة أي جدول ═══
class FakeTree:
    def __init__(self, rows, top_title=None, explicit=None):
        self.rows, self._top = rows, top_title
        if explicit:
            self._print_title = explicit

    def winfo_toplevel(self):
        app = self

        class Top:
            def title(self_): return app._top
        return A if self._top is None else Top()


class Tab:
    current_screen = "صناديق الخياس"


A = App()
A.tabview = Tab()
A.printed = []
A.tree_rows = lambda t: (["الاسم", "التاريخ", "الوزن"], t.rows)
A.print_generic_table_screen = lambda title, heads, ratios, rows, key, subtitle="": A.printed.append(
    (title, heads, ratios, rows, key, subtitle))

assert A.table_title(FakeTree([])) == "صناديق الخياس"
assert A.table_title(FakeTree([], top_title="أداء العمال")) == "أداء العمال"
assert A.table_title(FakeTree([], top_title="x", explicit="كشف سالم")) == "كشف سالم"
assert A.print_tree(FakeTree([])) is None and A.calls[-1][:2] == ("toast", "warn") and not A.printed
rows = [["سالم", "2026-09-01", "12.50"], ["الإجمالي", "", "12.50"]]
assert A.print_tree(FakeTree(rows, top_title="أداء العمال")) == "أداء العمال"
title, heads, ratios, prow, key, sub = A.printed[-1]
assert title == "📋 أداء العمال" and heads == ("الاسم", "التاريخ", "الوزن") and ratios == [1.4, 1.4, 1.0]
assert prow == [tuple(r) for r in rows] and key == "table_print" and sub.startswith("2 صف — ")
assert "self.print_tree(tree)" in body("show_table_menu") and "طباعة الجدول (PDF)" in body("show_table_menu")
print("✔ أي جدول يُطبع PDF من الزر الأيمن بالقالب الموحّد (كما يظهر بترتيبه والإجمالي آخراً)، "
      "بعنوان نافذته أو الشاشة المعروضة، والجدول الفارغ تنبيه")

# ═══ منحنى أداء العامل ═══
perf = body("open_worker_performance_report")
assert 'MiniChart(trend_box, kind="line", unit="‰"' in perf and 'tree.bind("<<TreeviewSelect>>", show_trend)' in perf
assert 'iid=f"w{len(table)}"' in perf and 'tree.selection_set("w0")' in perf
assert 'state["avg"] = [self.worker_performance_rows(sec, [p])[1]["ratio"] for p in periods]' in perf
assert '("متوسط القسم", state["avg"])' in perf and "(r[\"cells\"].get(p) or (0, 0, None))[2]" in perf
print("✔ أداء العمال: تحديد عامل يرسم نسبته لكل فترة مقابل متوسط قسمه (الأول محدد تلقائياً)")

# ═══ رموز الواجهة في PDF: لا مربعات فارغة ═══
import re


def module_src(name):
    n = next(x for x in tree_ast.body if (isinstance(x, ast.FunctionDef) and x.name == name)
             or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))
    return ast.get_source_segment(src, n)


class FakeFace:
    charToGlyph = {ord(c): 1 for c in "↑↓✓‰—…▲▼ابتجدرسصطعفقكلمنهوي 0123456789.-"}


class FakeMetrics:
    @staticmethod
    def getFont(name):
        if name == "Helvetica":
            raise AttributeError("standard font")
        return type("F", (), {"face": FakeFace()})()


pns = {"re": re, "pdfmetrics": FakeMetrics, "_ARABIC_FONT_NAME": "ArFont"}
for n in ("_PDF_SYMBOL_RANGES", "_PDF_SYMBOL_SWAP", "_PDF_GLYPHS", "_pdf_font_has", "pdf_text"):
    exec(module_src(n), pns)
pt = pns["pdf_text"]
assert pt("📋 أرشيف الفواتير") == "أرشيف الفواتير"
assert pt("🖨️ طباعة") == "طباعة", "علامة الاختيار التعبيري (FE0F) تُحذف مع الرمز"
assert pt("⬆ زيادة") == "↑ زيادة" and pt("⬇ تحسن") == "↓ تحسن" and pt("✔ سليم") == "✓ سليم"
assert pt("النسبة ‰ — 12.50 …") == "النسبة ‰ — 12.50 …", "ما يرسمه الخط يبقى كما هو"
assert pt("  نص  بمسافات  ") == "  نص  بمسافات  ", "النص بلا رموز لا يُمسّ"
assert pt("▲ ▼") == "▲ ▼"
pns["_ARABIC_FONT_NAME"] = "Helvetica"
assert pt("⬆ 5") == "5", "الخط القياسي بلا ملف: الرمز يُحذف"
assert "text = pdf_text(text)" in module_src("ar")
print("✔ PDF: الرموز التي لا يرسمها الخط (📋 🖨️ 🏁 …) تُحذف بدل المربعات الفارغة، والأسهم ⬆⬇ وعلامة ✔ تُستبدل "
      "بما يرسمه الخط — في كل تقارير النظام")

print("\n✅ إضافات الواجهة سليمة")
