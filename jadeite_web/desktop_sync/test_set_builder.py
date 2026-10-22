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
           "sb_check_assembler", "sb_ensure_assembler", "check_name_exists", "sb_post", "sb_set_field", "sb_set_pieces", "sb_pieces_totals", "sb_produce",
           "sb_unproduce", "sb_delete", "sb_next_set_number", "sb_sale_fill", "sb_stage_rows", "sb_ids",
           "sb_voucher_sections", "SB_FLOW", "SB_POST_CELLS", "SB_PAIR_BEFORE", "sb_flow_next", "CARAT_PER_GRAM", "SALE_KIND_GOLD",
           "SALE_KIND_DIAMOND", "SALE_KINDS", "sb_p2_incomplete", "sb_sale_index", "sb_apply_sale",
           "sb_sync_from_sale", "sb_mfg_receipts", "movement_slot", "note_head", "CHAINS_HEAD", "MFG_CHAINS_SLOT",
           "RECEIPT_KINDS", "TREE_HEAD", "ISSUE_HEADS", "MFG_SARF_KINDS", "MFG_SARF_SLOTS", "SADAYA", "CAST_NAME",
           "ASSEMBLED", "PARTS", "READY_SETS", "SB_PART_FIELDS", "SB_KIND_FIELDS", "TREASURY_KINDS", "invoices_by_period",
           "treasury_kind_of", "treasury_kind_breakdown", "sub_balance_lines", "POLISH1_SADAYA",
           "treasury_set_context", "sb_kind_mark", "sb_split_exit", "treasury_kind_moves", "sb_set_kind_mark",
           "sb_p2_after_split",
           "get_operation_datetime",
           "SB_DISMISSED_KEY", "sb_dismissed", "sb_set_dismissed", "_sb_undo_setting")
ns = {"sqlite3": sqlite3, "json": json, "datetime": datetime, "messagebox": mb, "log_cloud_error": lambda *a: None,
      "SALE_READ_STATUSES": ("ACTIVE", "SETTLED_INOUT", "MEMO"), "IS_ADMIN_BUILD": False,
      "COUNTED_STATUSES": module_value("COUNTED_STATUSES"),
      "KHAYAS_MARK_POLISH": module_value("KHAYAS_MARK_POLISH"), "KHAYAS_MARK_NET": module_value("KHAYAS_MARK_NET"),
      "KHAYAS_MARK_ASSEMBLER": module_value("KHAYAS_MARK_ASSEMBLER")}
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
    def get_display_label(self, cat): return {"المصنعين": "المصنعون"}.get(cat, cat)
    def toast(self, text, kind="info"): self.toasts = getattr(self, "toasts", []) + [text]

    def save_name_to_db(self, name, category):
        self.saved_names = getattr(self, "saved_names", []) + [(name, category)]

    def push_undo(self, label, auto=False):
        step = {"label": label}
        self.undo.append(step)
        return step

    def get_all_stage_categories(self): return ["خياس الطقوم", "التلميع/البف"]

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
assert "• رصيد سدايا في الخزينة: 0.00 ← -50.00  ⚠️ يصير بالسالب" in msg, "«قبل البوليش» ينقص من السدايا (1.87)"
(inv,) = a.moves(النوع="صرف تلميع بف")
assert (inv["الاسم"], inv["set_number"], inv["الوزن"], inv["row_number"]) == ("قالب رقم التشغيل", S, 50.0, "")
assert inv["البيان"] == "قبل البوليش — رقم التشغيل 9001" and inv["التاريخ"].startswith("2026-10-12 ")
assert inv["period"] == "2026-10" and a.undo[-1]["label"] == "قبل البوليش (9001) — قالب رقم التشغيل"
assert a.recalcs == 1
v = a.sb_values(S)
assert v["p1_before"] == 50.0 and v["p04"] is None and v["mfg_khayas"] is None, \
    "1.90: ٠٫٠٤٪ = قبض شغل 4 من المصنّع وحده (لا «قبل» البوليش) — وبلا شغل 4 فارغة"
# 1.90: ٠٫٠٨٪ = شغل 8 وحده و٠٫٠٤٪ = شغل 4 وحده من قبض المصنّع — والسلاسل (قبض/سلاسل، مفنش ٨) لا تدخلهما
w4 = a.add("أحمد", "المفنش ٤ بالالف", 50.0, row="1", set_no=S)
ch = a.add("أحمد", "المفنش ٨ بالالف", 4.0, row="1", set_no=S, **{"البيان": "سلاسل"})
v = a.sb_values(S)
assert (v["p04"], v["p08"], v["mfg_w8"], v["mfg_khayas"]) == (50.0, 50.4, None, 0.4), \
    "شغل 4 ← ٠٫٠٤٪، والسلاسل وحدها ليست شغل 8 (٠٫٠٨٪ المكتوب)، وخياس التصنيع = ٠٫٠٨٪ − ٠٫٠٤٪"
w8 = a.add("أحمد", "المفنش ٨ بالالف", 51.0, row="1", set_no=S)
v = a.sb_values(S)
assert (v["p08"], v["mfg_w8"], v["mfg_khayas"]) == (51.0, 51.0, 1.0), "شغل 8 بلا السلاسل (55 − 4)"
assert v["mfg"]["w8"] == 55.0 and v["mfg"]["chains"] == 4.0, "في حساب المصنّع (مفنش ٨) كما هي"
for i in (w4, ch, w8):
    a.delete_invoice_from_db(i)
print("✔ «قبل البوليش» = صرف تلميع بف باسم القالب وبرقم التشغيل، بتأكيد افتراضه «نعم» وفي الفترة المعروضة")
print("✔ ٠٫٠٨٪ = قبض شغل 8 وحده و٠٫٠٤٪ = قبض شغل 4 وحده (السلاسل لا تدخلهما)، وخياس التصنيع = ٠٫٠٨٪ − ٠٫٠٤٪")

mb.answer = False
n = len(a.invoices)
assert a.sb_post(S, "p1_after", 49.6) is False and len(a.invoices) == n
mb.answer = True
assert a.sb_post(S, "p1_after", 49.6) is True
assert "الخياس: 50.00 − 49.60 = 0.40" in mb.last()[2]
assert "• رصيد سدايا في الخزينة: -50.00 ← -0.40  ⚠️ يصير بالسالب" in mb.last()[2], "«بعد البوليش» يزيد السدايا (1.87)"
(out,) = a.moves(النوع="قبض تلميع بف")
assert out["الاسم"] == "قالب رقم التشغيل" and out["البيان"] == "بعد البوليش — رقم التشغيل 9001"
assert a.sb_values(S)["p1_khayas"] == 0.4
print("✔ «لا» في التأكيد لا يرحّل شيئاً؛ و«بعد» قبضٌ من بوليش 1 والتأكيد يذكر الخياس قبل الترحيل")

# التعديل يعدّل الحركة نفسها، والقيمة نفسها لا تسأل، والتفريغ (أو الصفر) يحذف
assert a.sb_post(S, "p1_before", 50.2) is True
assert mb.last()[1] == "تعديل «قبل البوليش»" and "القيمة المرحَّلة: 50.00" in mb.last()[2]
assert "• رصيد سدايا في الخزينة: -0.40 ← -0.60" in mb.last()[2], "التعديل بفرقه وحده"
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

# ═══ ٣) التركيب: صرف/قبض ذهب للمركّب في صفّه — الاسم يُكتب (وحسابه يُفتح إن لم يوجد) ورقم الصف إلزامي ═══
assert a.sb_post(S, "asm_before", 49.6) is False and mb.last()[1] == "اسم المركّب"
# 1.81: اسم مركّبٍ جديد ← يُفتح له حساب في المركبين مباشرة (فيظهر في قسم المركبين وصناديق خياسهم)
assert a.sb_ensure_assembler("‏زيد") is True and "زيد" in a.categories["المركبين"]
assert a.saved_names == [("زيد", "المركبين")] and "زيد" in a.toasts[-1]
assert a.sb_ensure_assembler("زيد") is True and len(a.saved_names) == 1, "الحساب الموجود لا يُفتح ثانية"
assert a.sb_ensure_assembler("أحمد") is False and mb.last()[1] == "الاسم مستخدم" and "المصنعون" in mb.last()[2], \
    "اسم حسابٍ آخر (مصنّع) لا يصير مركّباً"
a.view_only = True
assert a.sb_ensure_assembler("جديد") is False and "جديد" not in a.categories["المركبين"]
a.view_only = False
a.categories["المركبين"].remove("زيد")
print("✔ اسم مركّب جديد في القالب: يُفتح له حساب في المركبين مباشرة؛ والموجود لا يتكرر؛ واسم حسابٍ آخر يُرفض")
assert a.sb_post(S, "asm_before", 49.6, assembler="سالم", row="") is False and mb.last()[1] == "رقم الصف مطلوب"
a.add("خالد", "صرف ذهب", 30.0, row="5", set_no="8888")
assert a.sb_post(S, "asm_before", 49.6, assembler="خالد", row="5") is False and mb.last()[1] == "الصف مستخدم"
assert a.moves(النوع="صرف ذهب", set_number=S) == []
assert a.sb_post(S, "asm_before", 49.6, assembler="‏سالم", row="3") is True
assert "صرف ذهب للمركّب (سالم) — الصف (3)" in mb.last()[2]
_sad = a.treasury_kind_breakdown()["سدايا"]
assert "• رصيد سدايا في الخزينة: -30.60 ← -80.20  ⚠️ يصير بالسالب" in mb.last()[2], mb.last()[2]
assert (_sad["in"], _sad["out"]) == (49.6, 129.8), \
    "صرف المركّب من القالب ينقص من السدايا (1.85) — بعد صرف خالد 30، وبوليش 1: قبل 50.2 (خارج) وبعد 49.6 (داخل)"
(sarf,) = a.moves(النوع="صرف ذهب", set_number=S)
assert (sarf["الاسم"], sarf["row_number"], sarf["البيان"]) == ("سالم", "3", "")
rec = a.sb_load(S)
assert (rec["assembler"], rec["asm_row"]) == ("سالم", "3"), "المركّب وصفّه يُحفظان في قالبه"
# رقم التشغيل لصفٍّ واحد ولمركّب واحد: مركّب آخر للرقم نفسه يُرفض
assert a.sb_check_assembler(S, "خالد", "6") is None and mb.last()[1] == "رقم تشغيل مستخدم"
assert a.sb_post(S, "asm_after", 49.0, assembler="سالم", row="3") is True
assert "• رصيد أطقم مركبة في الخزينة: 0.00 ← 49.00" in mb.last()[2], "1.90: قبض المركّب ← أطقم مركبة (في التأكيد)"
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
br = a.treasury_kind_breakdown()
assert (br["فصوص وأحجار والماس"]["balance"], br["سلاسل"]["balance"], br["أطقم مركبة"]["balance"]) == (4.0, -3.0, 52.1), \
    "1.90/1.91: الفصوص والأحجار والماس في القالب ← نوعها، والسلسال ← من السلاسل إلى أطقم مركبة (49.1 + 3)"
assert a.sb_post(S, "p2_before", 56.1) is True and mb.last()[1] == "ترحيل «قبل بوليش 2»"
assert "• رصيد أطقم مركبة في الخزينة: 52.10 ← 0.00" in mb.last()[2] and \
    "• رصيد فصوص وأحجار والماس في الخزينة: 4.00 ← 0.00" in mb.last()[2], mb.last()[2]
assert "سلاسل" not in mb.last()[2], "قبل بوليش 2 = الفصوص + المركّب (بسلساله)"
assert a.sb_post(S, "p2_after", 55.8) is True
assert "• رصيد فصوص وأحجار والماس في الخزينة: 0.00 ← 4.00" in mb.last()[2] and \
    "• رصيد أطقم جاهزة للبيع في الخزينة: 0.00 ← 51.80" in mb.last()[2], mb.last()[2]
br = a.treasury_kind_breakdown()
assert [br[k]["balance"] for k in ("أطقم مركبة", "فصوص وأحجار والماس", "سلاسل", "أطقم جاهزة للبيع")] == \
    [0.0, 4.0, -3.0, 51.8], "1.91: بعد بوليش 2 ← الفصوص ترجع بوزنها والصافي (الخياس من المركبة) ← الجاهزة"
assert a.sb_values(S)["net"] == br["أطقم جاهزة للبيع"]["balance"], "«الوزن الصافي» في القالب = ما دخل الجاهزة"
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
a.add("أحمد", "المفنش ٤ بالالف", 50.0, row="1", set_no=S)
sec = a.set_voucher_sections({"set_number": S, "invoice_no": None})
assert sec["mfg"] == (50.4, 50.0, 0.4) and sec["polish"] == (50.2, 49.6, 0.6)
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
assert [getattr(a, attr).get() for attr, _k in a.SB_SALE_FIELDS] == ["51.8", "2", "1.5", "0.5", "1.2", "0.6", "0.3"]
assert a.sale_khayas.get() == "0.3" and "من القالب (مُرحَّل منه" in text and a._polish_set_fetched == S, \
    "1.82: خانة خياس بوليش 2 في المبيعات تُظهر خياس القالب (مُرحَّل منه — لا يُرحَّل ثانية)"
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
stage = member("stage_sale_row")
assert "if self.sb_p2_incomplete(set_num):" in stage and "khayas_v = sb_p2" in stage
assert stage.index("khayas_v = sb_p2") < stage.index('"خياس": khayas_v'), "السطر يحمل خياس بوليش 2 من القالب (للعرض)"
print("✔ خياس بوليش 2 لطقم القالب: يظهر في خانته وسطره وصافيه، ولا يُرحَّل من المبيعات ثانية (post_sale_rows)")
inv_data = member("get_invoice_group_data")
assert "sb_p2 = self.sb_polish2_khayas(set_number)" in inv_data and 'data["khayas"] = sb_p2' in inv_data
brk = member("get_set_khayas_breakdown")
assert "sb_p2 = self.sb_polish2_khayas(key)" in brk
print("✔ وفاتورة المبيعات وتفصيل خياس الطقم يعرضان خياس بوليش 2 المُرحَّل من القالب")

# ═══ ١١) المباع: لا يُلغى توليده ولا يُحذف قالبه ═══
a.add("عميل الطقم", "مبيعات ذهب", 51.8, set_no=S)
assert a.sb_status(S) == "مباع"
br = a.treasury_kind_breakdown()
assert (br["أطقم جاهزة للبيع"]["balance"], br["فصوص وأحجار والماس"]["balance"]) == (0.0, 4.0), \
    "1.91: البيع يخرج ذهبه (51.8) وحده من الجاهزة — والفصوص لا تُخصم بالبيع"
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

# ═══ ١٥أ) 1.82: الفصوص والأحجار بالقيراط (الجرام × ٥) — والعكس ═══
K = "9300"
a.sb_set_field(K, "gems", "2.5")
assert a.sb_values(K)["gems_ct"] == 12.5 and a.sb_values(K)["stones_ct"] is None
a.sb_set_field(K, "gems", 12.37 / 5)                 # ما يفعله «قيراط ← جرام» عند الكتابة في الجدول الأيمن
a.sb_set_field(K, "gems_ct", "12.37")
v = a.sb_values(K)
assert (v["gems"], v["gems_ct"]) == (2.47, 12.37), "القيراط المكتوب يبقى كما كُتب، وجرامه = ÷ ٥"
a.sb_set_field(K, "gems", "3")
assert a.sb_values(K)["gems_ct"] == 15.0, "تغيير الجرام يعيد القيراط = الجرام × ٥"
a.sb_set_field(K, "stones", "1.2")
assert a.sb_values(K)["stones_ct"] == 6.0
commit = member("sb_commit_cell")
assert 'grams_key = {"gems_ct": "gems", "stones_ct": "stones"}[key]' in commit and "ct / self.CARAT_PER_GRAM" in commit
assert a.set_voucher_sections({"set_number": K, "invoice_no": None})["carats"] == (15.0, 6.0)
assert 'carats = sec.get("carats")' in member("draw_set_voucher_page"), "السند المطبوع: الاجمالي فصوص/احجار بالقيراط"
print("✔ الاجمالي (فصوص / احجار) بالقيراط = الجرام × ٥، والمكتوب فيه بالقيراط ÷ ٥ في خانتيهما بالجرام — والسند كذلك")

# ═══ ١٥ب) 1.82: المبيعات ⇄ القالب — طقمٌ بيع من شاشة المبيعات يُحفظ قالبه مولَّداً بقيم فاتورته ═══
D = {"التاريخ": "2026-10-15 11:00:00"}
for t, w, extra in (("مبيعات ذهب", 30.0, {}), ("مبيعات فصوص وأحجار", 2.0, {}),
                    ("مبيعات فصوص وأحجار", 2.4, {"trees_count": 3.0, "قبل": 3.0}), ("مبيعات الماس", 0.5, {}),
                    ("خياس طقوم", 0.4, {}), ("خياس طقوم", 0.3, {"trees_count": 7.0, "settled_status": "MEMO"})):
    a.add("عميل س", t, w, set_no="9400", **dict(D, **extra))
sale = a.sb_sale_index()["9400"]
assert (sale["gold"], sale["gems"], sale["stones"], sale["stones_discount"], sale["diamond"], sale["khayas"],
        sale["khayas_polish"], sale["name"], sale["date"]) == (30.0, 2.0, 3.0, 2.4, 0.5, 0.4, 0.3, "عميل س", "2026-10-15")
row = {"set_number": "9400", "فصوص": 2.0, "أحجار": 3.0, "أحجار بعد الخصم": 2.4, "الماس": 0.5}
a._undo_open = step = {}
assert a.sb_sync_from_sale(row, "عميل س", "2026-10-15 11:00:00", "ذهب") is True
a._undo_open = None
assert "set_build:9400" in step["settings"] and step["settings"]["set_build:9400"] is None, "Ctrl+Z يعيده (لم يكن له قالب)"
rec = a.sb_load("9400")
assert (rec["source"], rec["status"], rec["gems"], rec["stones"], rec["stones_pct"], rec["diamond"], rec["customer"],
        rec["date"], rec["kind"]) == ("sale", "ready", 2.0, 3.0, 80.0, 0.5, "عميل س", "2026-10-15", "ذهب"), rec
v = a.sb_values("9400")
assert (v["p2_before"], v["p2_after"], v["p2_khayas"], v["final"], v["net"], v["p1_khayas"]) == (
    35.9, 35.5, 0.4, 35.5, 30.0, 0.3), v
assert v["ext"] == {"p2_before", "p2_after"} and a.sb_status("9400") == "مباع"
assert a.sb_polish2_khayas("9400") is None, "بوليش 2 لطقم المبيعات مُرحَّل من المبيعات وحدها — لا ازدواج"
assert a.sb_values(S)["ext"] == set(), "طقم القالب: مراحله من حركات القالب"
# 1.90/1.91: طقمٌ بيع من المبيعات ولم يمرّ ببوليش 2 في القالب ← فصوصه (التي كتبها البيع في قالبه) تدخل نوعها في فترة
# البيع (والبيع لا يخصمها)، وذهبه وخياسه يخرجان من المركبة — والجاهزة لا تمسّ
assert rec["kind_marks"]["gems"] == {"at": "2026-10-15 11:00:00", "period": "2026-10"}
br = a.treasury_kind_breakdown()
mv = sorted((n, w, sg) for k in ("أطقم مركبة", "فصوص وأحجار والماس", "أطقم جاهزة للبيع")
            for i, sg, w, n in br[k]["moves"] if i.get("set_number") == "9400")
assert mv == [("أحجار — من القالب", 3.0, 1), ("الماس — من القالب", 0.5, 1),
              ("بيع بلا بوليش 2 — المركّب", 30.4, -1), ("فصوص — من القالب", 2.0, 1)], mv
print("✔ بيع رقمٍ من المبيعات ← قالبه يُحفظ مولَّداً بقيم الفاتورة (الفصوص والأحجار ونسبة خصمها والماس والعميل والتاريخ)")
print("✔ وقالبه يعرض بوليش 2 من الفاتورة (بعد = الذهب + الفصوص + الأحجار + الماس، قبل = بعد + خياسه) والصافي = الذهب — للعرض")
# تحديث قالبٍ موجود من فاتورة بيعه: القيم المباعة فعلاً
a._undo_open = None
assert a.sb_sync_from_sale({"set_number": "9300", "فصوص": 3.0, "أحجار": 1.5, "أحجار بعد الخصم": 1.05, "الماس": 0},
                           "عميل ص", "2026-10-16 09:00:00", "ذهب") is True
r9300 = a.sb_load("9300")
assert (r9300["gems"], r9300["stones"], r9300["stones_pct"], r9300["diamond"], r9300["status"]) == (3.0, 1.5, 70.0, None, "ready")
assert r9300.get("source", "") != "sale"
post = member("post_sale_rows")
assert "self.sb_sync_from_sale(row, name, full_dt, kind, period=period)" in post
search = member("sb_open_search")
assert "sale = self.sb_sale_index().get(key)" in search and "self.sb_apply_sale(rec" in search
render = member("sb_render")
assert 'self.sb_put(cell_key, f(posted), "ext")' in render and "يخالف الوزن الصافي في القالب" in render
assert 'if key in st["ext"]:' in commit, "خانات المبيعات في القالب لا تُرحَّل منه ثانية"
print("✔ والقالب الموجود يأخذ قيم فاتورة بيعه، والبحث برقمٍ مباع ينشئ قالبه منها، والتنبيه إن خالف ذهبُ البيع صافيَ القالب")
# بوليش 2 ناقص («قبل» بلا «بعد») ← لا يُضاف سطر بيعه
assert a.sb_post("9500", "p2_before", 10.0) is True and a.sb_p2_incomplete("9500") is True
assert a.sb_post("9500", "p2_after", 9.8) is True and a.sb_p2_incomplete("9500") is False
assert "if self.sb_p2_incomplete(set_num):" in member("stage_sale_row")
print("✔ وطقمٌ «قبل» بوليش 2 له بلا «بعد» لا يُضاف سطر بيعه حتى يكتمل")
mfg = member("build_mfg_ui")
assert "command=lambda: self.quick_add_worker()" in mfg
qa = member("quick_add_worker")
assert "self.save_name_to_db(name, cat)" in qa and "self.check_name_exists(name)" in qa and "self.update_op_names(cat)" in qa
assert "win.grab_set()" in qa and "win.focus_force()" in qa     # تأخذ لوحة المفاتيح فوراً: Enter فيها لا في الشاشة خلفها
print("✔ مراحل التصنيع: زر «➕» بجانب الاسم في المصنعين والمركبين يضيف عاملاً للقسم مباشرة ويختاره")

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
assert flow == ["customer", "model", "label", "date", "assembler", "asm_row", "kind", "p08", "p04", "mfg_khayas",
                "p1_before", "p1_after", "asm_before", "asm_after", "gems", "stones", "stones_pct", "diamond",
                "chain", "p2_before", "p2_after", "gems_ct", "stones_ct"], flow
assert a.sb_flow_next("stones_ct") == "piece:0:0" and a.sb_flow_next("p1_after") == "asm_before", \
    "1.82: Enter بترتيب الورقة — من «بعد» البوليش إلى «قبل» التركيب (لا رجوع إلى اسم المركّب)، وآخرها ← جدول القطع"
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

# ═══ ١٥) 1.80: الشاشة هي القالب الورقي نفسه — هندسة سند رقم التشغيل، والإدخال في خاناته ═══
pns = {}
exec("class Paper:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in (
    "VOUCHER_MARGIN_MM", "set_voucher_layout", "SB_CELL_KINDS", "SB_PIECE_ROWS", "SB_PIECE_COLS",
    "sb_paper_spec", "sb_neighbor")), pns)
paper = pns["Paper"]()
spec = paper.sb_paper_spec()
L = paper.set_voucher_layout(compact=True)
P = paper.set_voucher_layout()
MM = P["MM"]
assert (P["head"], round(P["body_bottom"], 3), round(P["sig_line"], 3)) == (
    (P["M"], P["M"] + 24 * MM), round(P["PH"] - P["M"] - 20 * MM, 3), round(P["PH"] - P["M"] - 9 * MM, 3)), \
    "السند المطبوع بهندسته نفسها"
assert L["r"] > P["r"] * 1.15 and L["p"] > P["p"] * 1.15 and L["body_bottom"] < L["sig_line"] < L["PH"]
print(f"✔ الشاشة: الأقسام نفسها بمسافات بيضاء أقل — الصف {L['r'] / MM:.1f} مم (المطبوع {P['r'] / MM:.1f} مم)")
cells = [el for el in spec if el[0] == "cell"]
keys = [el[1] for el in cells]
assert len(keys) == len(set(keys)), "كل خانة إدخال مرة واحدة على الورقة"
pieces = {k for k in keys if k.startswith("piece:")}
assert set(keys) - pieces == set(paper.SB_CELL_KINDS) | {"set_no"}, set(keys) ^ (set(paper.SB_CELL_KINDS) | {"set_no"})
assert len(pieces) == a.SB_PIECE_ROWS * len(a.SB_PIECE_COLS) == 90
calcs = {el[1] for el in spec if el[0] == "calc"}
assert calcs == {"p1_khayas", "asm_khayas", "weight_after", "total", "p2_khayas", "final", "minus_gems", "minus_stones",
                 "minus_diamond", "net", "net2", "gems2", "stones_disc", "bound", "pct2"}, calcs
titles = {el[3] for el in spec if el[0] == "text"}
assert {"مصنع جاديت", "NO:", "التصنيع", "البوليش", "التركيب", "بوليش 2", "الوزن النهائي", "الاجمالي", "الأجمالي",
        "اسم العميل:", "رقم الموديل:", ":NAME", ":DATE", "اسم المركب:", "النوع:", "الوزن بعد", "السلسال",
        "الوزن الأجمالي:", "ناقص فصوص", "الوزن الصافي", "الوزن المقيد", "توقيع المدير", "توقيع المحاسب",
        "توقيع مدير الانتاج"} <= titles
print(f"✔ الورقة: كل خانات القالب ({len(keys) - 90} خانة + جدول القطع ٩٠) مرة واحدة، و{len(calcs)} خانة محسوبة، وعناوين القالب")

rects = {el[1]: el[2:6] for el in cells}
lx0, lx1 = L["col_left"]
rx0, rx1 = L["col_right"]
for k, (x0, t0, x1, t1) in rects.items():
    assert L["left"] - 0.01 <= x0 < x1 <= L["right"] + 0.01 and L["head"][0] <= t0 < t1 <= L["body_bottom"] + 0.01, k
    if k.startswith("piece:") or k in ("gems_ct", "stones_ct"):
        assert rx0 - 0.01 <= x0 and x1 <= rx1 + 0.01, k
    elif k in ("p08", "p04", "mfg_khayas", "p1_before", "p1_after", "asm_before", "asm_after", "gems", "stones",
               "stones_pct", "diamond", "chain", "p2_before", "p2_after"):
        assert lx0 - 0.01 <= x0 and x1 <= lx1 + 0.01, k
    else:
        assert t1 <= L["info"][1][1] + 0.01, k                       # الرأس وسطرا البيانات
items = list(rects.items())
for i, (k1, r1) in enumerate(items):
    for k2, r2 in items[i + 1:]:
        assert not (r1[0] < r2[2] - 0.01 and r2[0] < r1[2] - 0.01 and r1[1] < r2[3] - 0.01 and r2[1] < r1[3] - 0.01), (k1, k2)
print("✔ وهندسة سند رقم التشغيل نفسها: المراحل في العمود الأيسر، والقطع في الأيمن، والبيانات في الرأس — بلا تداخل")

paper._sb_state = {"rects": rects}
nb = paper.sb_neighbor
assert nb("p1_before", "left") == "p1_after" and nb("p1_after", "right") == "p1_before"
assert nb("p1_after", "down") == "asm_after" and nb("asm_after", "up") == "p1_after"
assert nb("customer", "down") == "assembler" and nb("p08", "up") == "kind" and nb("date", "up") == "set_no"
assert nb("customer", "up") is None, "لا خانة فوق «اسم العميل» في عموده (NO فوق التاريخ وNAME)"
assert nb("piece:0:0", "down") == "piece:1:0" and nb("piece:0:0", "left") == "piece:0:1"
assert nb("piece:17:0", "down") == "gems_ct" and nb("stones", "right") == "stones_pct"
assert nb("gems_ct", "left") == "stones_ct" and nb("gems_ct", "up") in ("piece:17:0", "piece:17:1")
print("✔ الأسهم على الورقة: ← → في السطر نفسه، و↑ ↓ في العمود نفسه (لا قفز للعمود الآخر)، وجدول القطع خانةً خانة")

flow = list(a.SB_FLOW)
assert flow[:7] == ["customer", "model", "label", "date", "assembler", "asm_row", "kind"] \
    and set(flow) <= set(paper.SB_CELL_KINDS)
arrow = member("sb_arrow")
assert 'cell["kind"] != "post" or key in st["pending"]' in arrow, "المقترح (بالأصفر) لا يُرحَّل بالمرور عليه"
assert "self.sb_commit_cell(key)" in arrow and "self.sb_neighbor(key, direction)" in arrow
enter = member("sb_on_enter")
assert 'if key == "set_no":' in enter and 'self.sb_open_search(self.sb_cell_text("set_no"))' in enter
keyh = member("sb_on_key")
assert 'text != st["shown"].get(key, "")' in keyh, "الأسهم وEnter لا تعلّم الخانة «لم تُرحَّل» — الكتابة فقط"
commit = member("sb_commit_cell")
assert 'key in st["auto"] and text == st["auto"][key]' in commit, "المحسوب المعروض (خياس التصنيع) لا يُحفظ كأنه مكتوب"
esc = member("sb_cancel_cell")
assert 'st["pending"].pop(key, None)' in esc and "return None" in esc
focus = member("sb_focus")
assert 'self.sb_ensure_visible(key)' in focus and 'update_idletasks()' in focus, "تُمرَّر الورقة للخانة قبل التركيز"
print("✔ Enter بترتيب العمل (البيانات ← النوع ← المراحل)، وفي NO يفتح الرقم؛ والأسهم تحفظ ما كُتب ثم تنتقل؛ وEsc يلغيه")

shown = member("sb_on_screen_shown")
assert 'self.sb_focus("set_no")' in shown and 'self.sb_status(key) == "قيد التشغيل"' in shown
assert "self.sb_first_empty()" in shown and 'st.pop("explicit", False)' in shown
assert 'SCREEN_ON_SHOW = {"قالب رقم التشغيل": "sb_on_screen_shown"}' in src
nav = member("navigate_to_screen")
assert nav.index("self.tabview.show(name)") < nav.index("self.SCREEN_ON_SHOW.get(name)")
assert "self.after_idle(getattr(self, hook))" in nav
build = member("build_set_builder_tab")
assert "tk.Canvas(holder" in build and 'canvas.bind("<Configure>", lambda e: self.sb_layout_paper()' in build
lay = member("sb_layout_paper")
assert "self.set_voucher_layout(compact=True)" in lay and "self.sb_paper_spec()" in lay
assert "canvas.create_window" not in lay
assert "sy = max(0.5, (height - 2 * pad - 4) / PH)" in lay, "القالب كاملاً بارتفاع المساحة — بلا تمرير"
assert "sy * 1.9" in lay and "box_h * sy * 0.66" in lay, "العرض حتى ١٫٩ من مقياس الارتفاع، والخط بقدر الصف"
assert 'scroll.pack_forget()' in lay, "شريط التمرير لا يظهر إلا إن لم تتسع الورقة"
assert "self.set_voucher_layout(compact=True)" in member("sb_paper_spec")
leave = member("sb_on_focus_out")
assert 'self.after(60, lambda: self.sb_post_on_leave(key))' in leave and 'not st.get("posting")' in leave
on_leave = member("sb_post_on_leave")
assert "focus.winfo_toplevel() is not self" in on_leave and "self.sb_commit_cell(key)" in on_leave
commit = member("sb_commit_cell")
assert 'st["posting"] = True' in commit and "self.sb_ensure_assembler(text, parent=parent)" in commit
assert 'SB_PAIR_BEFORE = {"p1_after": "p1_before", "asm_after": "asm_before", "p2_after": "p2_before"}' in src
assert "before_cell = self.SB_PAIR_BEFORE.get(key)" in commit and "self.sb_commit_cell(before_cell)" in commit
assert commit.index("self.sb_commit_cell(before_cell)") < commit.index("ok = self.sb_post(set_key, field, num"), \
    "«بعد» يُرحّل «قبل» المقترح أو المكتوب أولاً — فلا يظهر «بعد» وحده في الصندوق أو كشف المركّب"
produce = member("sb_produce_current")
assert 'st["pending"]' in produce and "لم تُرحَّل بعد" in produce
print("✔ مغادرة خانة مرحلة كُتب فيها (بالنقر أو غيره) تُرحّلها بالتأكيد — ولا توليد وفيه خانة لم تُرحَّل")
print("✔ عند فتح الشاشة: القالب ظاهر والإدخال في خاناته — آخر طقم قيد التشغيل مفتوحاً في أول خانة فارغة، وبلا طقوم في NO")

# بوليش 1 في قسمه: أرقام القالب صفٌّ واحد بكشفٍ لكل رقم؛ وتعديله/حذفه من القالب
ops = member("collect_stage_ops_rows")
assert 'g.setdefault("sb_sets", set()).add(' in ops
details = member("show_selected_stage_details")
assert "self.sb_ids(ids)" in details and "self.open_sb_stage_statement(kind)" in details
assert "self.open_sb_stage_statement(\"p1\")" in member("edit_selected_polish_buff_row")
p2 = member("polish2_month_parts")
assert "self.SB_P2_IN" in p2 and "self.SB_P2_OUT" in p2 and '"khayas": round(sales + before - after, 2)' in p2
print("✔ بوليش 1: أرقام القالب صفٌّ واحد بكشفٍ لكل رقم؛ وصندوق بوليش 2: قبل/بعد/خياس من القالب + المبيعات القديمة")

# 1.84: «قبل» بوليش 1 مُرحَّل (من شغل 4 تلقائياً) و«بعد» لم يُرحَّل ← «بعد البوليش» في التتبع صرف المركّب (لا يضيع)
S3 = "9077"
assert a.sb_post(S3, "p1_before", 30.0) is True
assert a.sb_post(S3, "asm_before", 29.5, assembler="سالم", row="11") is True
t = a.set_tracking_values(S3)
assert (t["polish_before"], t["polish_after"], t["polish_khayas"]) == (30.0, 29.5, 0.5), t
assert a.sb_post(S3, "p1_after", 29.6) is True
t = a.set_tracking_values(S3)
assert (t["polish_before"], t["polish_after"], t["polish_khayas"]) == (30.0, 29.6, 0.4), t
print("✔ التتبع: «قبل» من القالب و«بعد» ما لم يُرحَّل من القالب = صرف المركّب (ثم المرحَّل منه)")

print("\n✅ قالب رقم التشغيل: كل خانة تُرحَّل لمكانها، والأوزان محسوبة، والتوليد يملأ المبيعات بلا ازدواج")
