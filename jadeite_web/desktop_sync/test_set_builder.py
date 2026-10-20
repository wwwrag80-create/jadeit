# -*- coding: utf-8 -*-
"""
1.79: شاشة «قالب رقم التشغيل» — بناء الطقم كاملاً من قالبه، والقالب يُرحّل كل خانة لمكانها:

  • مصدر واحد: قيم المراحل من حركاتها وحدها — لا رقم ثانٍ يُحفظ في القالب:
      بوليش 1 «قبل» صرف تلميع بف و«بعد» قبضه (باسم «قالب رقم التشغيل» وبرقم التشغيل) — و٠٫٠٤٪ هو «قبل»،
      التركيب «قبل» صرف ذهب و«بعد» قبض ذهب للمركّب في صفّه (الاسم ورقم الصف يُكتبان، والصف إلزامي)،
      بوليش 2 «قبل بوليش 2» صرفٌ لصندوقه و«بعد بوليش 2» قبضٌ منه.
  • كل خانة تُرحَّل فور إدخالها بعد التأكيد (Enter يؤكّد)، وتعديلها يعدّل حركتها، وتفريغها يحذفها،
    وكل ترحيل خطوة تراجع.
  • الحسابات: الخياسات (قبل − بعد)، الوزن بعد = بعد التركيب + فصوص + أحجار + الماس، الإجمالي = الوزن بعد
    + السلسال، الصافي = النهائي (بعد بوليش 2) − فصوص − أحجار − الماس، والأحجار بعد الخصم، والمقيد.
  • «توليد الطقم» → رقمه في المبيعات يملأ سطر البيع منه، وخياس بوليش 2 لا يُرحَّل من المبيعات ثانية.
"""
import ast, datetime, io, json, os, sqlite3, sys, tempfile, textwrap

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


def module_value(name):
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name)
    return eval(compile(ast.Expression(node.value), name, "eval"), {"MEMO_STATUS": "MEMO"})


def module_src(name):
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(src, node)


class MB:
    """messagebox بديل يسجّل كل رسالة، ويجيب askyesno بما يُحدَّد"""
    YES = "yes"

    def __init__(self):
        self.log, self.answer = [], True

    def askyesno(self, title, msg, **k):
        self.log.append(("ask", title, msg, k))
        return self.answer

    def showwarning(self, title, msg, **k):
        self.log.append(("warn", title, msg, k))

    def showinfo(self, title, msg, **k):
        self.log.append(("info", title, msg, k))

    showerror = showwarning

    def last(self):
        return self.log[-1] if self.log else None


mb = MB()
MEMBERS = ("_SET_DIGITS", "ASSEMBLER_KHAYAS_STATUSES", "SALE_TYPES", "POLISH_BEFORE_PREFIX",
           "normalize_set_number", "inv_period", "inv_in_period", "assembler_set_index", "polish_before_map",
           "sale_polish_by_set", "set_number_sort_key", "get_setting", "set_setting", "clean_name",
           "row_set_numbers", "find_row_by_set_number", "set_tracking_values", "set_voucher_sections",
           "stage_types", "SB_SALE_FIELDS", "autofill_sale_from_build",
           "SB_PREFIX", "SB_NAME", "SB_P2_IN", "SB_P2_OUT", "SB_READY", "SB_PIECE_ROWS", "SB_PIECE_COLS",
           "SB_POSTED", "SB_NUMBER_FIELDS", "SB_TEXT_FIELDS", "sb_new_record", "sb_load", "sb_save", "sb_all",
           "sb_moves_index", "sb_assembler_groups", "sb_assembler_target_group", "sb_field_moves", "sb_num",
           "sb_values", "sb_polish2_khayas", "sb_polish1_posted", "sb_is_sold", "sb_status",
           "sb_check_assembler", "sb_post", "sb_set_field", "sb_set_pieces", "sb_pieces_totals", "sb_produce",
           "sb_unproduce", "sb_delete", "sb_next_set_number", "sb_sale_fill", "sb_stage_rows", "sb_ids",
           "sb_voucher_sections", "SB_FLOW", "SB_POST_CELLS")
ns = {"sqlite3": sqlite3, "json": json, "datetime": datetime, "messagebox": mb, "log_cloud_error": lambda *a: None,
      "SALE_READ_STATUSES": ("ACTIVE", "SETTLED_INOUT", "MEMO"), "IS_ADMIN_BUILD": False,
      "KHAYAS_MARK_POLISH": module_value("KHAYAS_MARK_POLISH")}
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)
exec(module_src("sale_net_weight"), ns)
sale_net_weight = ns["sale_net_weight"]


class App(ns["Base"]):
    def __init__(self, path):
        self.db_path, self.invoices, self.invoice_counter = path, {}, 0
        self.categories = {"المركبين": ["سالم", "خالد"], "المصنعين": ["أحمد"]}
        self.current_display_month = "2026-10"
        self.undo, self.recalcs, self.view_only, self.blocked = [], 0, False, 0

    def mark_backup_dirty(self): self._inv_version = getattr(self, "_inv_version", 0) + 1
    def view_only_blocked(self, silent=False): self.blocked += 1
    def recalculate_all(self): self.recalcs += 1
    def get_smart_default_date(self): return "2026-10-12"

    def push_undo(self, label, auto=False):
        step = {"label": label}
        self.undo.append(step)
        return step

    def get_stage_config(self, cat):
        return {"خياس الطقوم": ("خياس طقوم", "قبض خياس طقوم", "مسترجع بوليش 2"),
                "التلميع/البف": ("صرف تلميع بف", "قبض تلميع بف", "مسترجع بوليش 1")}.get(cat, (None, None, None))

    def save_invoice_to_db(self, inv_id, inv):
        inv.setdefault("period", self.current_display_month)
        self.invoices[inv_id] = inv
        self.mark_backup_dirty()
        return True

    def delete_invoice_from_db(self, inv_id):
        self.invoices.pop(inv_id, None)
        self.mark_backup_dirty()
        return True

    def add(self, name, t, w, row="", set_no="", period="2026-10", day="10", status="ACTIVE", **extra):
        self.invoice_counter += 1
        self.invoices[self.invoice_counter] = dict({
            "رقم الفاتورة": self.invoice_counter, "التاريخ": f"{period}-{day} 10:{self.invoice_counter % 60:02d}:00",
            "الاسم": name, "النوع": t, "الوزن": w, "البيان": "", "settled_status": status, "trees_count": 0.0,
            "قبل": 0.0, "بعد": 0.0, "set_number": set_no, "row_number": row, "period": period}, **extra)
        self.mark_backup_dirty()
        return self.invoice_counter

    def moves(self, **match):
        return [i for i in self.invoices.values() if all(i.get(k) == v for k, v in match.items())]


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "t.db")
with sqlite3.connect(path) as c:
    c.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
a = App(path)
S = "9001"

# ═══ ١) طقم جديد: لا قيمة = خانة فارغة (لا صفر مضلّل)، وبياناته تُحفظ في قالبه وحده ═══
assert a.sb_load(S) is None
v = a.sb_values(S)
for k in ("p04", "p1_before", "p1_after", "p1_khayas", "asm_before", "asm_khayas", "weight_after", "total",
          "p2_before", "p2_khayas", "final", "net", "bound"):
    assert v[k] is None, (k, v[k])
assert a.sb_set_field(S, "customer", " عميل الطقم ") is True
assert a.sb_set_field(S, "customer", "عميل الطقم") is False            # لم يتغيّر
assert a.sb_set_field(S, "p08", "٥٠٫٤") is True and a.sb_load(S)["p08"] == 50.4
assert a.sb_load(S)["customer"] == "عميل الطقم" and [r["set_number"] for r in a.sb_all()] == [S]
assert a.invoices == {}, "بيانات القالب ليست حركات"
print("✔ طقم جديد: خاناته فارغة (لا صفر)، وبياناته (العميل، ٠٫٠٨٪…) في قالبه — لا حركة")

# ═══ ٢) بوليش 1: كل خانة تُرحَّل فور إدخالها بعد التأكيد (Enter يؤكّد)، وخطوة تراجع ═══
assert a.sb_post(S, "p1_before", 50.0) is True
kind, title, msg, kw = mb.last()
assert kind == "ask" and title == "ترحيل «قبل البوليش»" and kw.get("default") == "yes", mb.last()
assert "Enter للتأكيد" in msg and "رقم التشغيل: 9001" in msg and "(2026-10)" in msg
(inv,) = a.moves(النوع="صرف تلميع بف")
assert (inv["الاسم"], inv["set_number"], inv["الوزن"], inv["row_number"]) == ("قالب رقم التشغيل", S, 50.0, "")
assert inv["البيان"] == "قبل البوليش — رقم التشغيل 9001" and inv["التاريخ"].startswith("2026-10-12 ")
assert inv["period"] == "2026-10" and a.undo[-1]["label"] == "قبل البوليش (9001) — قالب رقم التشغيل"
assert a.recalcs == 1
v = a.sb_values(S)
assert v["p1_before"] == v["p04"] == 50.0, "٠٫٠٤٪ في التصنيع هو «قبل» البوليش نفسه"
assert v["mfg_khayas"] == 0.4, "خياس التصنيع = ٠٫٠٨٪ − ٠٫٠٤٪ ما لم يُكتب"
print("✔ «قبل البوليش» = صرف تلميع بف باسم القالب وبرقم التشغيل، بتأكيد افتراضه «نعم» وفي الفترة المعروضة")
print("✔ و٠٫٠٤٪ في التصنيع هو «قبل» نفسه، وخياس التصنيع = ٠٫٠٨٪ − ٠٫٠٤٪ (ما لم يُكتب)")

mb.answer = False
n = len(a.invoices)
assert a.sb_post(S, "p1_after", 49.6) is False and len(a.invoices) == n
mb.answer = True
assert a.sb_post(S, "p1_after", 49.6) is True
assert "الخياس: 50.00 − 49.60 = 0.40" in mb.last()[2]
(out,) = a.moves(النوع="قبض تلميع بف")
assert out["الاسم"] == "قالب رقم التشغيل" and out["البيان"] == "بعد البوليش — رقم التشغيل 9001"
assert a.sb_values(S)["p1_khayas"] == 0.4
print("✔ «لا» في التأكيد لا يرحّل شيئاً؛ و«بعد» قبضٌ من بوليش 1 والتأكيد يذكر الخياس قبل الترحيل")

# التعديل يعدّل الحركة نفسها، والقيمة نفسها لا تسأل، والتفريغ (أو الصفر) يحذف
assert a.sb_post(S, "p1_before", 50.2) is True
assert mb.last()[1] == "تعديل «قبل البوليش»" and "القيمة المرحَّلة: 50.00" in mb.last()[2]
assert a.invoices[inv["رقم الفاتورة"]]["الوزن"] == 50.2 and len(a.moves(النوع="صرف تلميع بف")) == 1
k = len(mb.log)
assert a.sb_post(S, "p1_before", 50.2) is True and len(mb.log) == k
assert a.sb_post(S, "p1_after", 0) is True and mb.last()[1] == "حذف «بعد البوليش»"
assert a.moves(النوع="قبض تلميع بف") == [] and a.sb_values(S)["p1_after"] is None
assert a.sb_post(S, "p1_after", 49.6) is True
assert a.sb_values(S)["p1_khayas"] == 0.6
print("✔ تعديل خانة مُرحَّلة يعدّل حركتها نفسها (لا حركة ثانية)، والقيمة نفسها لا تسأل، والتفريغ أو الصفر يحذف")

# حركتان للخانة نفسها (سُجّلت إحداهما من شاشة القسم) → لا يُعدَّل من القالب
extra = a.add("قالب رقم التشغيل", "صرف تلميع بف", 1.0, set_no=S)
assert a.sb_post(S, "p1_before", 51.0) is False and mb.last()[0] == "warn" and "أكثر من حركة" in mb.last()[1]
a.delete_invoice_from_db(extra)
print("✔ خانة لها أكثر من حركة لا تُعدَّل من القالب — تنبيه بمكانها")

# ═══ ٣) التركيب: صرف/قبض ذهب للمركّب في صفّه — الاسم من قائمة المركبين ورقم الصف إلزامي ═══
assert a.sb_post(S, "asm_before", 49.6) is False and mb.last()[1] == "اسم المركّب"
assert a.sb_post(S, "asm_before", 49.6, assembler="زيد", row="3") is False and mb.last()[1] == "اسم المركّب"
assert a.sb_post(S, "asm_before", 49.6, assembler="سالم", row="") is False and mb.last()[1] == "رقم الصف مطلوب"
a.add("خالد", "صرف ذهب", 30.0, row="5", set_no="8888")
assert a.sb_post(S, "asm_before", 49.6, assembler="خالد", row="5") is False and mb.last()[1] == "الصف مستخدم"
assert a.moves(النوع="صرف ذهب", set_number=S) == []
assert a.sb_post(S, "asm_before", 49.6, assembler="‏سالم", row="3") is True
assert "صرف ذهب للمركّب (سالم) — الصف (3)" in mb.last()[2]
(sarf,) = a.moves(النوع="صرف ذهب", set_number=S)
assert (sarf["الاسم"], sarf["row_number"], sarf["البيان"]) == ("سالم", "3", "")
rec = a.sb_load(S)
assert (rec["assembler"], rec["asm_row"]) == ("سالم", "3"), "المركّب وصفّه يُحفظان في قالبه"
# رقم التشغيل لصفٍّ واحد ولمركّب واحد: مركّب آخر للرقم نفسه يُرفض
assert a.sb_check_assembler(S, "خالد", "6") is None and mb.last()[1] == "رقم تشغيل مستخدم"
assert a.sb_post(S, "asm_after", 49.0, assembler="سالم", row="3") is True
(qabd,) = a.moves(النوع="قبض ذهب", الاسم="سالم")
assert qabd["row_number"] == "3" and qabd["set_number"] == S
v = a.sb_values(S)
assert (v["asm_before"], v["asm_after"], v["asm_khayas"]) == (49.6, 49.0, 0.6)
assert (v["assembler"], v["asm_row"], v["asm_period"]) == ("سالم", "3", "2026-10")
idx = a.assembler_set_index()
assert (idx[S]["sarf"], idx[S]["qabd"]) == (49.6, 49.0), "التركيب في كشف المركّب نفسه (مصدر خياس المركب)"
# تعديله من القالب يعدّل حركة المركّب نفسها في صفّه (لا يسأل عن الاسم ثانية)
assert a.sb_post(S, "asm_after", 49.1) is True and len(a.moves(النوع="قبض ذهب", الاسم="سالم")) == 1
assert a.sb_values(S)["asm_khayas"] == 0.5
print("✔ التركيب: المركّب من القائمة والصف إلزامي، والصف المستخدم برقمٍ آخر يُرفض، والرقم لمركّب واحد")
print("✔ «قبل» صرف ذهب و«بعد» قبض ذهب في صف المركّب نفسه — فيظهر في كشفه ويحسب خياس المركب منه")

t = a.set_tracking_values(S)
assert (t["polish_before"], t["polish_after"], t["polish_khayas"]) == (50.2, 49.6, 0.6)
assert a.sb_polish1_posted(S) is True and a.sb_polish1_posted("8888") is False
print("✔ «تتبع رقم التشغيل» يقرأ قبل/بعد البوليش من حركتي القالب لطقمٍ مبنيٍّ فيه")

# ═══ ٤) الفصوص والأحجار والماس والسلسال، والأوزان المحسوبة ═══
for f, val in (("gems", "2"), ("stones", "1.5"), ("stones_pct", "80"), ("diamond", "0.5"), ("chain", "3")):
    assert a.sb_set_field(S, f, val) is True
v = a.sb_values(S)
assert v["weight_after"] == 53.1, "الوزن بعد = بعد التركيب + فصوص + أحجار + الماس"
assert v["total"] == 56.1, "الوزن الإجمالي = الوزن بعد + السلسال"
assert v["stones_disc"] == 1.2 and v["final"] is None and v["net"] is None
print("✔ الوزن بعد = بعد التركيب + فصوص + أحجار + الماس (53.10)، والإجمالي = + السلسال (56.10)")

# ═══ ٥) بوليش 2: «قبل» صرفٌ لصندوقه و«بعد» قبضٌ منه — والوزن النهائي آخر «بعد» ═══
assert a.sb_post(S, "p2_before", 56.1) is True and mb.last()[1] == "ترحيل «قبل بوليش 2»"
assert a.sb_post(S, "p2_after", 55.8) is True
(p2i,) = a.moves(النوع="قبل بوليش 2")
(p2o,) = a.moves(النوع="بعد بوليش 2")
assert p2i["الاسم"] == p2o["الاسم"] == "قالب رقم التشغيل" and p2i["set_number"] == S
v = a.sb_values(S)
assert (v["p2_before"], v["p2_after"], v["p2_khayas"], v["final"]) == (56.1, 55.8, 0.3, 55.8)
assert v["net"] == 51.8, "الصافي = النهائي − فصوص − أحجار − الماس"
assert v["bound"] == 55.5, "المقيد = الصافي + الفصوص + الأحجار بعد الخصم + الماس"
assert a.sb_polish2_khayas(S) == 0.3 and a.sb_polish2_khayas("8888") is None
madin, qabd_t = a.stage_types("خياس الطقوم")
assert madin == {"خياس طقوم", "قبل بوليش 2"} and qabd_t == {"قبض خياس طقوم", "بعد بوليش 2"}
assert a.stage_types("التلميع/البف") == ({"صرف تلميع بف"}, {"قبض تلميع بف"})
print("✔ بوليش 2: «قبل بوليش 2» صرفٌ و«بعد بوليش 2» قبضٌ في صندوقه (أنواع المرحلة)، والخياس الفرق (0.30)")
print("✔ الوزن النهائي = بعد بوليش 2 (55.80)، والصافي = النهائي − فصوص − أحجار − الماس (51.80)، والمقيد 55.50")

# ═══ ٦) كشف أرقام التشغيل في بوليش 1 وبوليش 2 (صفٌّ واحد في جدول القسم، وكشفٌ لكل رقم) ═══
a.sb_post("9002", "p1_before", 20.0)
a.add("قالب رقم التشغيل", "صرف تلميع بف", 7.0, set_no="9003", period="2026-09")
rows = a.sb_stage_rows("p1")
assert [(r["set_number"], r["before"], r["after"], r["khayas"]) for r in rows] == [
    ("9001", 50.2, 49.6, 0.6), ("9002", 20.0, None, 20.0)], rows
assert [r["set_number"] for r in a.sb_stage_rows("p1", "2026-09")] == ["9003"]
assert [r["set_number"] for r in a.sb_stage_rows("p1", query="٩٠٠٢")] == ["9002"]
assert [(r["set_number"], r["khayas"]) for r in a.sb_stage_rows("p2")] == [("9001", 0.3)]
assert a.sb_ids([inv["رقم الفاتورة"], p2i["رقم الفاتورة"]]) is True
assert a.sb_ids([inv["رقم الفاتورة"], sarf["رقم الفاتورة"]]) is False and a.sb_ids([]) is False
print("✔ كشف أرقام القالب لكل فترة (بحثٌ بالرقم، والأرقام الهندية كاللاتينية): قبل وبعد وخياس كل رقم")

# ═══ ٧) جدول القطع (١–١٨) ═══
pieces = [["2", "S", "فص زركون", "1.2", ""], ["1", "", "أحجار", "0.8", ""], ["1", "", "الماس", "0.5", ""],
          ["1", "", "سلسال", "3", "طول 45"], ["", "", "", "", ""]]
assert a.sb_set_pieces(S, pieces) is True and len(a.sb_load(S)["pieces"]) == 4, "الصفوف الفارغة في آخره لا تُحفظ"
assert a.sb_set_pieces(S, pieces) is False
assert a.sb_pieces_totals(a.sb_load(S)["pieces"]) == (1.2, 0.8, 0.5, 5.5)
print("✔ جدول القطع يُحفظ في القالب بلا صفوفه الفارغة، ومجموع أوزانه حسب النوع (فص/حجر/الماس)")

# ═══ ٨) سند رقم التشغيل من القالب كله ═══
sec = a.set_voucher_sections({"set_number": S, "invoice_no": None})
assert sec["mfg"] == (50.4, 50.2, 0.2) and sec["polish"] == (50.2, 49.6, 0.6)
assert sec["assembly"] == (49.6, 49.1, 0.5) and sec["polish2"] == (56.1, 55.8, 0.3)
assert (sec["weight_after"], sec["chain"], sec["total"], sec["net"], sec["bound"]) == (53.1, 3.0, 56.1, 51.8, 55.5)
assert sec["assemblers"] == "سالم" and sec["name"] == "عميل الطقم" and len(sec["pieces"]) == 4
assert sec["final_values"] == [("الوزن النهائي", 55.8), ("ناقص فصوص", 2.0), ("ناقص احجار", 1.5),
                               ("ناقص الماس", 0.5), ("الوزن الصافي", 51.8)]
old = a.set_voucher_sections({"set_number": "8888", "invoice_no": None})
assert "final_values" not in old, "رقمٌ ليس في القالب: سند التتبع والمبيعات كما كان"
print("✔ سند رقم التشغيل لطقمٍ في القالب من قالبه كله (المراحل، الأوزان، القطع، الوزن النهائي)؛ وغيره كما كان")

# ═══ ٩) توليد الطقم ═══
assert a.sb_produce("9002") is False and mb.last()[1] == "الوزن النهائي مطلوب"
assert a.sb_status(S) == "قيد التشغيل" and a.sb_sale_fill(S) is None
mb.answer = False
assert a.sb_produce(S) is False and a.sb_status(S) == "قيد التشغيل"
mb.answer = True
assert a.sb_produce(S) is True
msg = mb.last()[2]
assert "الوزن النهائي: 55.80" in msg and "الوزن الصافي: 51.80" in msg and "خياس بوليش 2: 0.30" in msg
assert "لم يُسجَّل بعد" not in msg
step = a.undo[-1]
assert step["label"] == "توليد الطقم (9001)" and "set_build:9001" in step["settings"], "التوليد خطوة تراجع"
assert a.sb_status(S) == "جاهز للبيع" and a.sb_load(S)["produced"]
assert a.sb_unproduce(S) is True and a.sb_status(S) == "قيد التشغيل"
assert a.sb_produce(S) is True
print("✔ «توليد الطقم»: يُرفض بلا وزن نهائي، ورسالة ملخّصه بالأوزان والخياسات، وخطوة تراجع، ويُلغى توليده")

fill = a.sb_sale_fill(S)
assert fill == {"ذهب": 51.8, "فصوص": 2.0, "أحجار": 1.5, "الماس": 0.5, "أحجار بعد الخصم": 1.2,
                "خياس البوليش": 0.6, "p2_khayas": 0.3, "stones_pct": 80.0}, fill
print("✔ الطقم المولَّد يملأ سطر البيع: الذهب = الصافي، والفصوص والأحجار وبعد خصمها والماس وخياس البوليش")


# ═══ ١٠) المبيعات: رقم الطقم يملأ الخانات مرة لكل رقم، ورقمٌ آخر يمسح ما مُلئ ═══
class Entry:
    def __init__(self, text=""): self.text = text
    def get(self): return self.text
    def delete(self, a_, b_=None): self.text = ""
    def insert(self, i, s): self.text = s + self.text


for attr, _k in a.SB_SALE_FIELDS:
    setattr(a, attr, Entry())
a.sale_khayas = Entry("0.3")
a.sale_discount_pct = Entry("30%")
a.sale_discount_pct.set = lambda t: setattr(a.sale_discount_pct, "text", t)
text = a.autofill_sale_from_build(S)
assert a.sale_discount_pct.get() == "80%", "نسبة خصم الأحجار في المبيعات = نسبة القالب (لا يعيد «إضافة» حسابها بغيرها)"
assert [getattr(a, attr).get() for attr, _k in a.SB_SALE_FIELDS] == ["51.8", "2", "1.5", "0.5", "1.2", "0.6"]
assert a.sale_khayas.get() == "" and "مُرحَّل من القالب" in text and a._polish_set_fetched == S
a.sale_gold.text = "51.9"                       # تعديلٌ يدوي بعد الملء
assert a.autofill_sale_from_build("٩٠٠١") == text and a.sale_gold.get() == "51.9", "الرقم نفسه لا يُعاد ملؤه"
assert "لم يُولَّد بعد" in a.autofill_sale_from_build("9002")
assert all(getattr(a, attr).get() == "" for attr, _k in a.SB_SALE_FIELDS), "رقمٌ آخر يمسح ما مُلئ من القالب"
assert a.autofill_sale_from_build("8888") == ""
print("✔ المبيعات: رقم الطقم المولَّد يملأ خانات البيع مرة (التعديل اليدوي يبقى)، ورقمٌ آخر يمسحها")

# خياس بوليش 2 مُرحَّل من القالب: صافي الطقم يحسبه، ولا يُرحَّل من المبيعات ثانية
row = {"فصوص": 2.0, "أحجار بعد الخصم": 1.2, "خياس": 0.0, "خياس البوليش": 0.6, "خياس المركب": 0.5}
assert sale_net_weight(dict(row, **{"خياس": a.sb_polish2_khayas(S)})) == round(2.0 + 1.2 - 0.3 - 0.6 - 0.5, 2)
post = member("post_sale_rows")
assert "sb_p2 = self.sb_polish2_khayas(set_num)" in post and "khayas_v = 0.0" in post
assert 'net_v = sale_net_weight(dict(row, **{"خياس": sb_p2}))' in post
seg_all = src[src.index("sb_p2 = self.sb_polish2_khayas(set_num)\n        if sb_p2 is not None and khayas_v > 0:"):][:600]
assert "لن يُرحَّل من المبيعات مرة ثانية" in seg_all and "khayas_v = 0.0" in seg_all
print("✔ خياس بوليش 2 لطقم القالب: يدخل صافيه، ولا يُرحَّل من المبيعات ثانية (الإضافة تنبّه وتصفّره، والترحيل كذلك)")
inv_data = member("get_invoice_group_data")
assert "sb_p2 = self.sb_polish2_khayas(set_number)" in inv_data and 'data["khayas"] = sb_p2' in inv_data
brk = member("get_set_khayas_breakdown")
assert "sb_p2 = self.sb_polish2_khayas(key)" in brk
print("✔ وفاتورة المبيعات وتفصيل خياس الطقم يعرضان خياس بوليش 2 المُرحَّل من القالب")

# ═══ ١١) المباع: لا يُلغى توليده ولا يُحذف قالبه ═══
a.add("عميل الطقم", "مبيعات ذهب", 51.8, set_no=S)
assert a.sb_status(S) == "مباع"
assert a.sb_unproduce(S) is False and mb.last()[1] == "طقم مباع"
assert a.sb_delete(S) is False and mb.last()[1] == "طقم مباع" and a.sb_load(S) is not None
print("✔ الطقم المباع: حاله «مباع»، ولا يُلغى توليده، ولا يُحذف قالبه")

# ═══ ١٢) حذف قالب طقم: وحركاته المرحَّلة منه بعد التأكيد (خطوة تراجع) ═══
assert a.sb_post("9002", "asm_before", 20.0, assembler="خالد", row="7") is True
assert a.sb_delete("9002") is True
assert "2 حركة" in mb.log[-1][2] and "(خالد — الصف 7)" in mb.log[-1][2]
assert a.sb_load("9002") is None and a.moves(set_number="9002") == [] and "9002" not in a.assembler_set_index()
assert a.undo[-1]["label"] == "حذف قالب الطقم (9002)" and "set_build:9002" in a.undo[-1]["settings"]
print("✔ حذف قالب طقم يحذف حركاته المرحَّلة منه (بوليش 1 وصرف المركّب) بعد التأكيد، وخطوة تراجع")

# ═══ ١٣) اقتراح رقم طقم جديد، والتنقّل من أول طقم لآخرها، ووضع العرض ═══
assert a.sb_next_set_number() == "9002", a.sb_next_set_number()       # أكبر رقم (9001) + ١
a.sb_set_field("9100", "customer", "ثانٍ")
assert [r["set_number"] for r in a.sb_all()] == [S, "9100"], "الترتيب من أول طقم عُمل عليه إلى آخرها"
assert a.sb_next_set_number() == "9101"
a.view_only = True
n = len(a.invoices)
assert a.sb_post("9100", "p1_before", 5.0) is False and a.blocked and len(a.invoices) == n
assert a.sb_produce(S) is False
a.view_only = False
print("✔ «طقم جديد» يقترح أكبر رقم + ١، والطقوم مرتّبة من أولها لآخرها للسهمين، ووضع العرض لا يرحّل شيئاً")

# ═══ ١٤) الشاشة: مسجّلة، وترتيب الخانات بـ Enter كالقالب الورقي، وكل خانة مرحلة لمكانها ═══
prim = next(ast.literal_eval(n.value) for n in ast.walk(cls) if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "SIDEBAR_PRIMARY" for t in n.targets))
assert prim[-1][0] == "قالب رقم التشغيل" and len(prim) == 7
assert 'self.tabview.add("قالب رقم التشغيل")' in src
assert '"قالب رقم التشغيل": self.build_set_builder_tab,' in src
assert '"قالب رقم التشغيل": ("refresh_set_builder",),' in src
assert '"7": 6' in src and '"٧": 6' in src and '"Ctrl + 1 … 7"' in src
print("✔ الشاشة في الشريط الجانبي (السابعة، Ctrl+7) وتُبنى عند أول فتح وتُحدَّث بالحساب الشامل")

flow = list(a.SB_FLOW)
assert flow.index("p04") < flow.index("p1_before") < flow.index("p1_after") < flow.index("assembler") \
    < flow.index("asm_row") < flow.index("asm_before") < flow.index("asm_after") < flow.index("gems") \
    < flow.index("chain") < flow.index("p2_before") < flow.index("p2_after") == len(flow) - 1
assert set(a.SB_POST_CELLS.values()) == set(a.SB_POSTED) and a.SB_POST_CELLS["p04"] == "p1_before"
enter = member("sb_on_enter")
assert "self.sb_commit_cell(key)" in enter and 'st["btn_produce"].focus_set()' in enter
commit = member("sb_commit_cell")
assert "self.sb_post(set_key, field, num" in commit and "self.sb_set_field(set_key, field, text)" in commit
assert 'st["pending"].pop(key, None)' in commit
print("✔ Enter ينتقل بين الخانات بترتيب القالب الورقي، وكل خانة مرحلة تُرحَّل بالتأكيد، وآخرها ← «توليد الطقم»")

ref = member("refresh_set_builder")
assert 'max(sets, key=lambda r: str(r.get("updated") or ""))' in ref, "أول فتح: آخر طقم عُمل عليه"
step_src = member("sb_step")
assert "self.sb_show(keys[j], edit=False)" in step_src
search = member("sb_open_search")
assert "self.scanned_set_number(raw)" in search and "إنشاء قالب طقمٍ جديد بهذا الرقم؟" in search
assert 'self.sb_show(key, edit=rec.get("status") != self.SB_READY and not self.sb_is_sold(key))' in search
render = member("sb_render")
assert '"p2_before": v["total"]' in render and '"asm_before": v["p1_after"]' in render, "المقترح من الخانة فوقها"
assert "يختلف عن الوزن الإجمالي" in render and "سالب" in render
print("✔ أول فتح يعرض آخر طقم، والسهمان من أول طقم لآخرها، والبحث (أو الباركود) يفتح الطقم أو ينشئه بعد التأكيد")
print("✔ المقترح: «قبل» التركيب = «بعد» البوليش و«قبل» بوليش 2 = الوزن الإجمالي (بحافة تنبيه حتى يُؤكَّد)")

# بوليش 1 في قسمه: أرقام القالب صفٌّ واحد بكشفٍ لكل رقم؛ وتعديله/حذفه من القالب
ops = member("collect_stage_ops_rows")
assert 'g.setdefault("sb_sets", set()).add(' in ops
details = member("show_selected_stage_details")
assert "self.sb_ids(ids)" in details and "self.open_sb_stage_statement(kind)" in details
assert "self.open_sb_stage_statement(\"p1\")" in member("edit_selected_polish_buff_row")
p2 = member("polish2_month_parts")
assert "self.SB_P2_IN" in p2 and "self.SB_P2_OUT" in p2 and '"khayas": round(sales + before - after, 2)' in p2
print("✔ بوليش 1: أرقام القالب صفٌّ واحد بكشفٍ لكل رقم؛ وصندوق بوليش 2: قبل/بعد/خياس من القالب + المبيعات القديمة")

print("\n✅ قالب رقم التشغيل: كل خانة تُرحَّل لمكانها، والأوزان محسوبة، والتوليد يملأ المبيعات بلا ازدواج")
