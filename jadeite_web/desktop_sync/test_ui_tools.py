# -*- coding: utf-8 -*-
"""
أدوات الواجهة (الدفعة ١٦) — من دوال البرنامج نفسها:

  • كل جدول: النقر على العنوان يرتّب (الأرقام رقمياً ولو فيها فواصل أو «جم»، والنص أبجدياً)
    وصف الإجمالي يبقى آخراً؛ والجداول التي يُعدَّل اسم عمودها بالنقر تُرتَّب من القائمة.
  • زر الفأرة الأيمن: نسخ المحدد/الكل (يُلصق في Excel)، تصدير CSV بترميز تقرؤه Excel بالعربية، بحث.
  • مركز التنبيهات: المتأخر عند العمال، الفترات غير المُقفلة، عمر النسخة الاحتياطية — وكل تنبيه يفتح شاشته.
  • F1 للاختصارات، وتلميحات للأزرار، وإشعار عابر بدل «موافق» للرسائل القصيرة.
"""
import ast, csv, io, os, re, sys, tempfile, textwrap, time

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


ns = {"re": re, "os": os, "time": time, "IS_ADMIN_BUILD": False}
MEMBERS = ["_NUM_CLEAN", "SORT_ARROWS", "cell_number", "table_headers", "_on_tree_header_click", "sort_tree_by",
           "tree_rows", "copy_tree_rows", "write_table_csv", "find_in_tree", "BACKUP_ALERT_DAYS",
           "local_backup_age_days", "home_alerts", "WORKER_SECTIONS"]
exec("class Base:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in MEMBERS), ns)


class FakeTree:
    def __init__(self, cols, rows, totals=()):
        self.cols, self.order, self.data, self.heads, self.sel = list(cols), [], {}, {}, []
        for c in cols:
            self.heads[c] = c
        for n, r in enumerate(list(rows) + list(totals)):
            iid = f"I{n}"
            self.order.append(iid)
            self.data[iid] = {"values": list(r), "tags": ("total_tag",) if n >= len(rows) else ()}

    def __getitem__(self, k):
        return tuple(self.cols)

    def get_children(self, _p=""):
        return tuple(self.order)

    def set(self, iid, col):
        return self.data[iid]["values"][self.cols.index(col)]

    def item(self, iid, key):
        return self.data[iid][key]

    def move(self, iid, parent, idx):
        self.order.remove(iid)
        self.order.insert(idx, iid)

    def heading(self, col, text=None):
        if text is None:
            return {"text": self.heads[col]}
        self.heads[col] = text

    def selection(self):
        return tuple(self.sel)

    def selection_set(self, items):
        self.sel = list(items)

    def see(self, i): pass
    def focus(self, i): pass
    def identify_region(self, x, y): return "heading" if y < 20 else "cell"
    def identify_column(self, x): return f"#{x // 100 + 1}"
    def winfo_toplevel(self): return None


class App(ns["Base"]):
    def __init__(self):
        self.toasts, self.clip = [], ""

    def wrap_header(self, h):
        return h

    def toast(self, text, kind="info", ms=0, parent=None):
        self.toasts.append((kind, text))

    def clipboard_clear(self):
        self.clip = ""

    def clipboard_append(self, t):
        self.clip += t


app = App()
assert [app.cell_number(v) for v in ("1,234.50", "‎66,702.75 جم", "-12.5", "372.63 ‰", "—", "-", "", "2026-09", "أحمد")] \
    == [1234.5, 66702.75, -12.5, 372.63, None, None, None, None, None]
print("✔ قيمة الخلية رقماً رغم الفواصل والوحدات وعلامات الاتجاه، والتاريخ والنص ليسا رقماً")

rows = [("سالم", "1,200.00", "2026-09-03"), ("أحمد", "95.50", "2026-09-01"), ("خالد", "-", "2026-08-30"),
        ("بدر", "1,005.25", "2026-09-02")]
t = FakeTree(("الاسم", "الوزن", "التاريخ"), rows, totals=[("الإجمالي", "2,300.75", "")])
app.sort_tree_by(t, "الوزن", descending=True)
order = [t.set(i, "الاسم") for i in t.get_children()]
assert order == ["سالم", "بدر", "أحمد", "خالد", "الإجمالي"], order
assert t.heads["الوزن"] == "الوزن ▼" and t.heads["الاسم"] == "الاسم"
app.sort_tree_by(t, "الوزن", descending=False)
assert [t.set(i, "الاسم") for i in t.get_children()] == ["أحمد", "بدر", "سالم", "خالد", "الإجمالي"]
app.sort_tree_by(t, "التاريخ")
assert [t.set(i, "الاسم") for i in t.get_children()][:4] == ["خالد", "أحمد", "بدر", "سالم"]
assert t.heads["الوزن"] == "الوزن" and t.heads["التاريخ"] == "التاريخ ▲", "السهم ينتقل للعمود المرتَّب"
print("✔ الترتيب: الأرقام رقمياً (1,200 > 1,005 > 95.5)، الفارغ آخراً، التاريخ زمنياً، والإجمالي يبقى آخر صف")


class E:
    def __init__(self, x, y): self.x, self.y = x, y


t2 = FakeTree(("الاسم", "الوزن"), rows[:2])
app._on_tree_header_click(t2, E(150, 5))                # عمود الوزن
assert t2._sort_state == ("الوزن", False)
app._on_tree_header_click(t2, E(150, 5))
assert t2._sort_state == ("الوزن", True), "النقرة الثانية تعكس"
app._on_tree_header_click(t2, E(150, 50))               # نقرة داخل الصفوف لا ترتّب
assert t2._sort_state == ("الوزن", True)
t2._rename_bound = True
app._on_tree_header_click(t2, E(50, 5))
assert t2._sort_state == ("الوزن", True), "جدول يُعدَّل اسم عموده بالنقر لا يُرتَّب بالنقر (من القائمة)"
print("✔ النقر على العنوان يرتّب والثانية تعكس؛ والجداول التي يُعدَّل اسم عمودها بالنقر تُرتَّب من القائمة")

t3 = FakeTree(("الاسم", "الوزن"), rows)
t3._total_tree = FakeTree(("الاسم", "الوزن"), [("الإجمالي", "2,300.75")])
assert app.copy_tree_rows(t3, selected=True) == 0 and app.toasts[-1][0] == "warn"
t3.selection_set(["I0", "I2"])
assert app.copy_tree_rows(t3, selected=True) == 2
assert app.clip == "الاسم\tالوزن\nسالم\t1,200.00\nخالد\t-"
assert app.copy_tree_rows(t3) == 5 and app.clip.endswith("الإجمالي\t2,300.75")
print("✔ النسخ: المحدد أو الجدول كله (مع الإجمالي الملاصق) بعناوينه، مفصولاً بجدولة فيُلصق في Excel أعمدةً")

path = os.path.join(tempfile.mkdtemp(), "t.csv")
heads, data = app.tree_rows(t3)
app.write_table_csv(path, heads, data)
raw = open(path, "rb").read()
assert raw.startswith(b"\xef\xbb\xbf"), "بلا BOM يفتح Excel العربية رموزاً"
with open(path, encoding="utf-8-sig") as f:
    got = list(csv.reader(f))
assert got[0] == ["الاسم", "الوزن"] and got[1] == ["سالم", "1,200.00"] and got[-1] == ["الإجمالي", "2,300.75"]
print("✔ التصدير إلى Excel: CSV بترميز UTF-8 مع BOM (العربية سليمة في Excel)، والقيم كما تُعرض")

hits = app.find_in_tree(t3, "خالد")
assert hits == ["I2"] and t3.selection() == ("I2",)
assert app.find_in_tree(t3, "غير موجود") == [] and app.toasts[-1][0] == "warn"
print("✔ البحث يحدّد كل صف يحتوي النص ويعرض أولها")

# ═══ مركز التنبيهات ═══
class AlertsApp(ns["Base"]):
    backup_dir = "x"
    actions = []

    def __init__(self, unclosed, backups):
        self._unclosed, self._backups = unclosed, backups

    def get_unclosed_periods(self, cat): return self._unclosed.get(cat, [])
    def list_local_backups(self): return self._backups
    def open_backup_manager(self): pass
    def navigate_to_screen(self, n): AlertsApp.actions.append(n)


tmp = tempfile.mkdtemp()
fresh = os.path.join(tmp, "new.db")
old = os.path.join(tmp, "old.db")
open(fresh, "w").close()
open(old, "w").close()
os.utime(old, (time.time() - 5 * 86400, time.time() - 5 * 86400))
a = AlertsApp({"المصنعين": [("2026-08", 5.0)], "المركبين": [("2026-08", 1.0), ("2026-07", 2.0)]}, [old])
al = a.home_alerts()
assert [x[0] for x in al] == ["warn", "info"], al
assert "3 فترة سابقة" in al[0][1] and "2026-07، 2026-08" in al[0][1]
assert "منذ 5 يوم" in al[1][1]
assert not any("متأخر" in x[1] for x in al), "تنبيه الطقوم المتأخرة أُزيل"
al[0][2]()
assert AlertsApp.actions == ["صناديق الخياس"], "تنبيه الفترات يفتح صناديق الخياس"
assert AlertsApp({}, [fresh]).home_alerts() == []
assert "لا توجد نسخة احتياطية" in AlertsApp({}, []).home_alerts()[0][1]
ns["IS_ADMIN_BUILD"] = True
assert AlertsApp({}, []).home_alerts() == [], "نسخة المدير لا تنبّه على نسخ جهاز العميل"
ns["IS_ADMIN_BUILD"] = False
print("✔ التنبيهات: الفترات غير المُقفلة وعمر النسخة الاحتياطية — وكل تنبيه يفتح شاشته")

# ═══ الربط ═══
std = body("create_standard_treeview")
assert "self.enable_table_tools(tree)" in std
assert src.count("self.enable_table_tools(data_tree)") == 2
assert "main_tree._no_sort = True" in body("create_two_pane_ledger_tree")
tools = body("enable_table_tools")
assert '"<Button-3>"' in tools and '"<Control-c>"' in tools and '"<ButtonRelease-1>"' in tools
assert 'self.bind_all("<F1>", lambda e: self.open_shortcuts_help(), add="+")' in src
keys = [k for k, _w in ast.literal_eval(ast.get_source_segment(src, node("SHORTCUTS")).split("=", 1)[1].strip())]
for k in ("F1", "F2", "Ctrl + Z", "Ctrl + B", "Ctrl + C", "Esc"):
    assert k in keys, k
assert "self.refresh_home_alerts()" in body("refresh_home_stats")
assert "self.home_alerts_frame = " in body("build_home_screen") and "HoverTip(b, tip)" in body("build_home_screen")
hover = next(n for n in tree_ast.body if isinstance(n, ast.ClassDef) and n.name == "HoverTip")
assert "wm_overrideredirect(True)" in ast.get_source_segment(src, hover)
assert src.count("HoverTip(") >= 9
assert "host.after(ms" in body("toast")
assert 'EXPORTS_DIR = _make_dir(os.path.join(APP_DATA_DIR, "Exports"))' in src
print("✔ كل الجداول (القياسية والمثبَّتة الإجمالي ونافذة العرض الكامل) فيها الأدوات، وF1 للاختصارات، "
      "وتلميحات للأزرار، ومركز التنبيهات وإجراءات سريعة في الرئيسية")

print("\n✅ أدوات الواجهة سليمة")
