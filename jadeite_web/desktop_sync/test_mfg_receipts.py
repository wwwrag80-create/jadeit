# -*- coding: utf-8 -*-
"""
1.84: قبض المصنّعين (كسر، شغل 4، شغل 8، سلاسل) من مراحل التصنيع ومن قالب رقم التشغيل، و«قبل» بوليش 1 من شغل 4،
ونوع القبض في الأقسام المضافة (سبيكة/واير/لحام)، وتفصيل رصيد الخزينة.
1.85: صرف المصنّع بنوعه (ذهب / لحام / واير — كل نوع خانته في الصف)، والسدايا (شغل 4 + شغل 8 ينقص منها صرف المركبين)،
وأرصدة التفصيل متراكمة من الفترات السابقة.

  • السلاسل تُحسب مثل شغل 8 (المسموح ٨ بالألف): حركتها «المفنش ٨ بالالف» وأول بيانها «سلاسل» — والمعادلة كما هي.
  • خانة السلاسل مستقلة في الصف (قاعدة الصف والخانة) وفي التعديل والجدول.
  • شغل 4 برقم تشغيل ← «قبل» بوليش 1 للرقم بقيمته (ترحيل/تعديل/حذف)، في خطوة التراجع نفسها.
  • القبض من القالب بقواعد قسم المصنعين: رقم التشغيل يعرّف الصف، وكل خانة مرة في الصف.
  • تفصيل الخزينة: قبض الفترة المعروضة من كل نوع.
"""
import ast, io, os, re, sqlite3, sys, tempfile, textwrap, datetime

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


def module_src(name):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == name for t in n.targets):
            return ast.get_source_segment(src, n)
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(src, n)
    raise KeyError(name)


MEMBERS = ("_SET_DIGITS", "normalize_set_number", "inv_period", "inv_in_period", "clean_name", "rtl",
           "CHAINS_HEAD", "MFG_CHAINS_SLOT", "MFG_WORK_KINDS", "MFG_WORK_SLOTS", "RECEIPT_KINDS",
           "TREE_HEAD", "CAST_SARF_KINDS", "STAGE_SARF_KINDS", "ISSUE_HEADS", "NOTE_HEADS",
           "note_head", "with_note_head", "movement_slot", "slot_op_type",
           "post_casting_loss", "post_generic_stage", "is_recovery_op", "is_row_recovery", "TREE_RETURN_NAME",
           "CAST_ANALYSIS_OPS",
           "post_manufacturer_receipt", "find_row_by_set_number", "row_set_numbers", "plan_unified_values",
           "calculate_single_ledger", "worker_rows_raji", "invoices_by_name", "invoices_by_name_period",
           "MFG_SARF_KINDS", "MFG_SARF_SLOTS", "SLOT_TYPES", "SLOT_HEADS", "SADAYA", "CAST_NAME", "invoices_by_period",
           "TREASURY_KINDS", "treasury_kind_of", "treasury_kind_breakdown", "slot_kind_deltas", "sub_balance_lines",
           "_read_weight", "POLISH1_SADAYA",
           "SB_PREFIX", "SB_NUMBER_FIELDS", "SB_TEXT_FIELDS", "sb_num", "sb_new_record", "sb_load", "sb_save", "sb_all",
           "set_number_sort_key", "get_setting", "set_setting", "sb_mfg_receipts", "SB_DISMISSED_KEY", "sb_dismissed",
           "sb_set_dismissed", "_sb_undo_setting", "sb_ensure_born", "sb_record_empty", "sb_follow_set_number")


class MB:
    log, answers = [], []
    YES, NO = "yes", "no"

    @classmethod
    def showwarning(cls, title, *a, **k): cls.log.append(("warn", title, a[0] if a else ""))
    @classmethod
    def showinfo(cls, title, *a, **k): cls.log.append(("info", title, a[0] if a else ""))
    @classmethod
    def showerror(cls, title, *a, **k): cls.log.append(("error", title, a[0] if a else ""))
    @classmethod
    def askyesno(cls, title, msg, **k):
        cls.log.append(("ask", title, msg, k.get("default")))
        return cls.answers.pop(0) if cls.answers else True


ns = {"re": re, "datetime": datetime, "messagebox": MB, "log_cloud_error": lambda *a: None, "json": __import__("json"),
      "sqlite3": sqlite3}
exec("\n".join(module_src(n) for n in ("ALLOWANCE_8", "ALLOWANCE_4", "raji_ayar", "LEDGER_FIELD_BY_TYPE")), ns)
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)
M = "2026-10"


class App(ns["Base"]):
    SB_NAME = "قالب رقم التشغيل"

    def __init__(self):
        self.db_path = os.path.join(tempfile.mkdtemp(), "t.db")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        self.invoices, self.invoice_counter = {}, 0
        self.categories = {"المصنعين": ["أحمد", "خالد"], "المركبين": ["سالم"], "أقسام_خياس_إضافية": ["صب الداخلي"]}
        self.current_display_month = M
        self.undo, self.recalcs, self.view_only, self.posts = [], 0, False, []

    def mark_backup_dirty(self): self._inv_version = getattr(self, "_inv_version", 0) + 1
    def view_only_blocked(self, silent=False): self.blocked = True
    def recalculate_all(self): self.recalcs += 1
    def register_operation_period(self, d): pass
    def get_operation_datetime(self): return f"{M}-12 10:00:00"
    def get_smart_default_date(self): return f"{M}-12"
    def push_undo(self, label, auto=False):
        self.undo.append(label)
        return {"label": label}
    def get_all_stage_categories(self): return ["الكاستنج", "صب الداخلي"]
    def get_stage_config(self, cat):
        return {"الكاستنج": ("صرف كاستنج", "قبض كاستنج", "مسترجع كاستنج"),
                "صب الداخلي": ("صرف صب الداخلي", "قبض صب الداخلي", "مسترجع صب الداخلي")}[cat]
    def period_invoices(self, month): return [i for i in self.invoices.values() if self.inv_period(i) == month]

    def save_invoice_to_db(self, inv_id, inv):
        inv.setdefault("period", self.current_display_month)
        self.invoices[inv_id] = inv
        self.mark_backup_dirty()
        return True

    def delete_invoice_from_db(self, inv_id):
        self.invoices.pop(inv_id, None)
        self.mark_backup_dirty()
        return True

    # «قبل» بوليش 1 من القالب: حركة «صرف تلميع بف» باسم القالب ورقم التشغيل (sb_post الحقيقي يُختبر في test_set_builder)
    def sb_field_moves(self, key, field):
        return [i for i in self.invoices.values() if i["الاسم"] == self.SB_NAME and i["النوع"] == "صرف تلميع بف"
                and i.get("set_number") == key and i["settled_status"] == "ACTIVE"]

    def sb_post(self, key, field, value, parent=None, confirm=True, **k):
        assert field == "p1_before" and confirm is False
        self.posts.append((key, value))
        moves = self.sb_field_moves(key, field)
        if value is None:
            return self.delete_invoice_from_db(moves[0]["رقم الفاتورة"])
        if moves:
            moves[0]["الوزن"] = value
            return self.save_invoice_to_db(moves[0]["رقم الفاتورة"], moves[0])
        return self.add(self.SB_NAME, "صرف تلميع بف", value, set_no=key)

    def add(self, name, t, w, row="", set_no="", note="", period=M):
        self.invoice_counter += 1
        self.invoices[self.invoice_counter] = {
            "رقم الفاتورة": self.invoice_counter, "التاريخ": f"{period}-05 10:00:00", "الاسم": name, "النوع": t,
            "الوزن": w, "البيان": note, "settled_status": "ACTIVE", "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0,
            "set_number": set_no, "row_number": row, "period": period}
        self.mark_backup_dirty()
        return self.invoice_counter

    def polish(self, key):
        return [i["الوزن"] for i in self.sb_field_moves(key, "p1_before")]


a = App()

# ═══ ١) أول البيان نوع القبض: يُقرأ ويُكتب ولا يُفقد ═══
assert a.note_head({"البيان": "سلاسل — بيان"}) == "سلاسل" and a.note_head({"البيان": ""}) == ""
assert a.with_note_head("سلاسل", "بيان") == "سلاسل — بيان" and a.with_note_head("سلاسل", "") == "سلاسل"
assert a.with_note_head("واير", "زركون — بيان") == "واير — بيان", "نوعٌ آخر في أوله يُستبدل"
assert a.with_note_head("", "لحام — x") == "x" and a.with_note_head("", "بيان عادي") == "بيان عادي"
chains = {"النوع": "المفنش ٨ بالالف", "البيان": "سلاسل — x"}
assert a.movement_slot(chains) == "قبض سلاسل" and a.movement_slot({"النوع": "المفنش ٨ بالالف", "البيان": ""}) \
    == "المفنش ٨ بالالف" and a.slot_op_type("قبض سلاسل") == "المفنش ٨ بالالف"
print("✔ نوع القبض في أول البيان («سلاسل — بيان»): يُقرأ، ويُستبدل نوعٌ آخر كان في أوله، والسلاسل خانة مستقلة")

# ═══ ٢) حساب المصنّع: السلاسل مثل شغل 8 (المسموح ٨ بالألف) — المعادلة نفسها ═══
a.add("أحمد", "صرف ذهب", 100.0, row="1", set_no="5001")
a.add("أحمد", "المفنش ٨ بالالف", 40.0, row="1", set_no="5001")
a.add("أحمد", "المفنش ٤ بالالف", 30.0, row="1", set_no="5001")
a.add("أحمد", "صرف ذهب", 50.0, row="2", set_no="5002")
a.add("أحمد", "المفنش ٨ بالالف", 20.0, row="2", set_no="5002", note="سلاسل")
a.add("أحمد", "قبض ذهب", 5.0, row="2", set_no="5002", note="زركون")
L = a.calculate_single_ledger("أحمد", "المصنعين")
assert L["المفنش ٨ بالالف"] == 60.0 and L["المفنش ٤ بالالف"] == 30.0
assert L["مسموح 8"] == round(60.0 * ns["ALLOWANCE_8"], 2) and L["ذهب/باقي"] == round(150 - 5 - 60 - 30, 2)
print(f"✔ حساب المصنّع: السلاسل (20) مع شغل 8 (40) في المفنش ٨ ومسموحه ({L['مسموح 8']}) — المعادلة المعتمدة كما هي")

# ═══ ٣) قاعدة الصف والخانة: السلاسل خانة مستقلة عن قبض/٨ ═══


class Ent:
    def __init__(self, v): self.v = v
    def get(self): return self.v


a.current_win_entries = {"رقم الصف": Ent("2"), "المفنش ٨ بالالف": Ent("7"), "قبض سلاسل": Ent("3"),
                         "المفنش ٤ بالالف": Ent("4")}
plan, skipped = a.plan_unified_values("أحمد", "2")
assert plan == [("المفنش ٨ بالالف", 7.0), ("المفنش ٤ بالالف", 4.0)] and skipped == [("قبض سلاسل", 20.0)], (plan, skipped)
print("✔ قاعدة الصف والخانة: صفٌّ فيه سلاسل يقبل شغل 8 وشغل 4، والسلاسل لا تُكرَّر فيه")

# ═══ ٤) لا «قبل» بوليش 1 تلقائياً (1.86): جداول القالب تحت التصنيع تُكتب يدوياً ═══
assert "sync_work4_polish" not in src and "work4_totals" not in src, "لا ترحيل تلقائي لبوليش 1 من شغل 4"
four = next(i for i in a.invoices.values() if i["النوع"] == "المفنش ٤ بالالف")
a.delete_invoice_from_db(four["رقم الفاتورة"])
print("✔ شغل 4 لا يرحّل «قبل» بوليش 1 — يُكتب يدوياً في القالب (وما رُحِّل من قبل يبقى كما هو)")

# ═══ ٥) القبض من القالب: قواعد قسم المصنعين، والتأكيد، والحركات في مكانها ═══
MB.log.clear()
a.posts.clear()
assert a.post_manufacturer_receipt("أحمد", "5003", "3", 2.5, 41.0, "شغل 4") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "قبض/كسر: 2.5" in ask[2] and "شغل 4 (قبض/٤): 41" in ask[2] and "بوليش" not in ask[2]
row3 = sorted((i["النوع"], i["الوزن"], i["row_number"], i["set_number"], i["البيان"]) for i in a.invoices.values()
              if i["الاسم"] == "أحمد" and i["row_number"] == "3")
assert row3 == [("المفنش ٤ بالالف", 41.0, "3", "5003", ""), ("قبض ذهب", 2.5, "3", "5003", "")], row3
assert a.polish("5003") == [] and a.undo[-1] == "المصنّع (أحمد) — الصف (3) — 5003", "شغل 4 بلا «قبل» بوليش 1"
assert ask[1] == "ترحيل لحساب المصنّع" and "• رصيد سدايا في الخزينة:" in ask[2]
# رقم مسجّل: يُكمل صفّه بلا رقم صف، والسلاسل حركتها مفنش ٨ بأول بيانها «سلاسل»
assert a.post_manufacturer_receipt("أحمد", "٥٠٠١", "", 0.0, 12.0, "سلاسل") is True
ch = [i for i in a.invoices.values() if i["row_number"] == "1" and a.movement_slot(i) == "قبض سلاسل"]
assert len(ch) == 1 and ch[0]["النوع"] == "المفنش ٨ بالالف" and ch[0]["البيان"] == "سلاسل" and ch[0]["الوزن"] == 12.0
# شغل 8 مسجّل في الصف نفسه: لا يُكرَّر
MB.log.clear()
assert a.post_manufacturer_receipt("أحمد", "5001", "", 0.0, 5.0, "شغل 8") is False
assert MB.log[-1][1] == "مسجّل بالفعل"
print("✔ القبض من القالب: كسر ← قبض/كسر، وشغل 4 ← قبض/٤ و«قبل» بوليش 1، والسلاسل ← قبض/سلاسل (مفنش ٨)، "
      "ورقم التشغيل المسجّل يُكمل صفّه، والخانة المسجّلة لا تُكرَّر")
cases = ((("سالم", "5009", "1", 1.0, 0.0, "شغل 4"), "اسم المصنّع"),
         (("أحمد", "5009", "1", None, 0.0, "شغل 4"), "قيمة غير صحيحة"),
         (("أحمد", "5009", "1", -1.0, 0.0, "شغل 4"), "قيمة غير صحيحة"),
         (("أحمد", "5009", "1", 0.0, 0.0, "شغل 4"), "لا قيمة"),
         (("أحمد", "5009", "1", 0.0, 3.0, "؟"), "نوع الشغل"),
         (("أحمد", "", "", 1.0, 0.0, "شغل 4"), "رقم الصف مطلوب"),
         (("خالد", "5001", "", 1.0, 0.0, "شغل 4"), "رقم تشغيل مستخدم"),
         (("أحمد", "5001", "9", 1.0, 0.0, "شغل 4"), "رقم تشغيل مستخدم"),
         (("أحمد", "5009", "", 1.0, 0.0, "شغل 4"), "رقم الصف مطلوب"),
         (("أحمد", "5009", "2", 1.0, 0.0, "شغل 4"), "رقم تشغيل مختلف"))
n0 = len(a.invoices)
for args, title in cases:
    MB.log.clear()
    assert a.post_manufacturer_receipt(*args) is False, args
    assert MB.log and MB.log[-1][1] == title, (args, MB.log)
MB.answers[:] = [False]
assert a.post_manufacturer_receipt("أحمد", "5009", "9", 1.0, 0.0, "شغل 4") is False
a.view_only = True
assert a.post_manufacturer_receipt("أحمد", "5009", "9", 1.0, 0.0, "شغل 4") is False
a.view_only = False
assert len(a.invoices) == n0
print("✔ يُرفض: غير المصنّع، والقيمة غير الرقمية أو السالبة أو الصفر، ونوعٌ غير الثلاثة، وبلا رقم تشغيل ولا صف، ورقمٌ "
      "لمصنّع آخر أو لصف آخر، ورقمٌ جديد بلا صف، وصفٌّ برقم آخر — و«لا» في التأكيد، ووضع العرض")
# رقم التشغيل اختياري (1.86): الصف يعرّف الحركة، ورقم تشغيل الصف المسجّل يُعطى لها
MB.log.clear()
assert a.post_manufacturer_receipt("أحمد", "", "1", 1.5, 0.0, "شغل 4") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "الصف (1) — رقم التشغيل (5001)" in ask[2], ask[2]
k1 = [i for i in a.invoices.values() if i["الاسم"] == "أحمد" and i["row_number"] == "1" and i["النوع"] == "قبض ذهب"]
assert len(k1) == 1 and k1[0]["set_number"] == "5001" and k1[0]["الوزن"] == 1.5
assert a.post_manufacturer_receipt("أحمد", "", "7", 0.0, 6.0, "شغل 8") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "الصف (7) — بلا رقم تشغيل ⊘" in ask[2], ask[2]
r7 = [(i["النوع"], i["الوزن"], i["set_number"]) for i in a.invoices.values() if i["الاسم"] == "أحمد" and i["row_number"] == "7"]
assert r7 == [("المفنش ٨ بالالف", 6.0, "")], r7
print("✔ رقم التشغيل اختياري: بلا رقمٍ تُرحَّل الحركة لصفّها (برقم تشغيله المسجّل إن كان له، وإلا ⊘ بلا رقم)")

# ═══ ٥ب) صرف المصنّع بنوعه: ذهب / لحام / واير — كل نوع خانته في الصف، والحركة «صرف ذهب» نفسها ═══
MB.log.clear()
assert a.post_manufacturer_receipt("أحمد", "5003", "", 0.0, 0.0, "شغل 4", sarf=3.0, sarf_kind="لحام") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "صرف لحام (صرف/لحام): 3" in ask[2] and "• رصيد لحام في الخزينة: 0.00 ← -3.00  ⚠️ يصير بالسالب" in ask[2], ask[2]
sol = [i for i in a.invoices.values() if i["الاسم"] == "أحمد" and i["row_number"] == "3" and i["النوع"] == "صرف ذهب"]
assert len(sol) == 1 and sol[0]["البيان"] == "لحام" and sol[0]["الوزن"] == 3.0 and sol[0]["set_number"] == "5003"
assert a.movement_slot(sol[0]) == "صرف لحام" and a.slot_op_type("صرف لحام") == "صرف ذهب"
assert a.post_manufacturer_receipt("أحمد", "5003", "", 0.0, 0.0, "شغل 4", sarf=10.0, sarf_kind="ذهب") is True
gold = [i for i in a.invoices.values() if i["row_number"] == "3" and i["الاسم"] == "أحمد" and a.movement_slot(i) == "صرف ذهب"]
assert len(gold) == 1 and gold[0]["البيان"] == "" and gold[0]["الوزن"] == 10.0, "صرف الذهب خانته (لا ينقص من رصيدٍ مفصّل)"
MB.log.clear()
assert a.post_manufacturer_receipt("أحمد", "5003", "", 0.0, 0.0, "شغل 4", sarf=1.0, sarf_kind="لحام") is False
assert MB.log[-1][1] == "مسجّل بالفعل", "صرف اللحام مرة في الصف"
assert a.post_manufacturer_receipt("أحمد", "5002", "", 0.0, 0.0, "شغل 4", sarf=2.0, sarf_kind="واير") is True
for kw, title in (({"sarf": 1.0, "sarf_kind": "فضة"}, "نوع الصرف"), ({"sarf": -1.0}, "قيمة غير صحيحة"),
                  ({"sarf": None}, "قيمة غير صحيحة")):
    MB.log.clear()
    assert a.post_manufacturer_receipt("أحمد", "5003", "", 0.0, 0.0, "شغل 4", **kw) is False and MB.log[-1][1] == title
L = a.calculate_single_ledger("أحمد", "المصنعين")
assert L["الصرف"] == 165.0, f"حساب المصنّع: كل الصرف بأنواعه في «الصرف» (100 + 50 + 3 + 10 + 2) — {L['الصرف']}"
# صرف الشجر للمصنّع (1.86): خانته «صرف/شجر»، وينقص من رصيد الشجر
MB.log.clear()
assert a.post_manufacturer_receipt("أحمد", "5002", "", 0.0, 0.0, "شغل 4", sarf=4.0, sarf_kind="شجر") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "صرف شجر (صرف/شجر): 4" in ask[2] and "• رصيد شجر في الخزينة: 0.00 ← -4.00" in ask[2], ask[2]
tree_mv = [i for i in a.invoices.values() if a.movement_slot(i) == "صرف شجر"]
assert len(tree_mv) == 1 and tree_mv[0]["البيان"] == "شجر" and tree_mv[0]["row_number"] == "2"
# صرف المركّب ببيان «لحام» ليس صرف لحامٍ للمصنّع (خانته صرف ذهب)
assert a.movement_slot({"النوع": "صرف ذهب", "البيان": "لحام", "الاسم": "سالم"}) == "صرف ذهب"
# خطة الصف في مراحل التصنيع: خانة الصرف حسب نوعه المختار
a.current_op_cat = "المصنعين"
a.selected_sarf_type = "لحام"
a.current_win_entries = {"رقم الصف": Ent("3"), "صرف ذهب": (Ent("5"), None)}
assert a.plan_unified_values("أحمد", "3") == ([], [("صرف لحام", 3.0)])
a.selected_sarf_type = "واير"
assert a.plan_unified_values("أحمد", "3") == ([("صرف واير", 5.0)], [])
a.selected_sarf_type = "ذهب"
assert a.plan_unified_values("أحمد", "3") == ([], [("صرف ذهب", 10.0)])
print("✔ صرف المصنّع بنوعه: ذهب ← صرف، ولحام ← صرف/لحام، وواير ← صرف/واير، وشجر ← صرف/شجر (حركة صرف ذهب بنوعها "
      "في أول البيان)، وكلٌّ مرة في الصف، وكل الصرف في حساب المصنّع؛ والتأكيد برصيد النوع قبل وبعد (وتنبيه السالب)")

# ═══ ٥ج) الكاستنج والأقسام المضافة — بمحرّك مراحل التصنيع نفسه (الذي يرحّل منه القالب) ═══
MB.log.clear()
assert a.post_casting_loss("1", 10.0, 9.0, 3.0, 0.5, sarf_kind="كسر") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "• الصرف — كسر: 10" in ask[2] and "• القبض (شجر): 9" in ask[2] and "• مسترجع الأشجار: 0.5" in ask[2], ask[2]
assert "• رصيد كسر في الخزينة: 9.00 ← -1.00  ⚠️ يصير بالسالب" in ask[2] and "• رصيد شجر في الخزينة: -4.00 ← 5.00" in ask[2]
cast = sorted((i["الاسم"], i["النوع"], i["الوزن"], i["البيان"], i["row_number"], i["trees_count"])
              for i in a.invoices.values() if i["الاسم"] in ("كاستنج", "مسترجع الأشجار"))
assert cast == [("كاستنج", "صرف كاستنج", 10.0, "كسر", "1", 3.0), ("كاستنج", "قبض كاستنج", 9.0, "", "1", 3.0),
                ("مسترجع الأشجار", "قبض كاستنج", 0.5, "مسترجع الأشجار", "1", 0.0)], cast
MB.log.clear()
assert a.post_casting_loss("1", 5.0, 0.0, 0.0, 0.0, sarf_kind="سبيكة") is False and MB.log[0][1] == "عملية مكررة"
assert a.post_casting_loss("2", 4.0, 0.0, 0.0, 0.0, sarf_kind="سبيكة") is True
assert a.post_casting_loss("3", 2.0, 0.0, 0.0, 0.0) is True, "صرفٌ عام (بلا نوع) كما في مراحل التصنيع"
for args, title in ((("", 1.0, 0.0, 0.0, 0.0), "رقم الصف مطلوب"), (("4", None, 0.0, 0.0, 0.0), "قيمة غير صحيحة"),
                    (("4", -1.0, 0.0, 0.0, 0.0), "تنبيه"), (("4", 0.0, 0.0, 0.0, 0.0), "تنبيه")):
    MB.log.clear()
    assert a.post_casting_loss(*args) is False and MB.log[-1][1] == title, (args, MB.log)
notes = sorted((i["row_number"], i["البيان"]) for i in a.invoices.values() if i["النوع"] == "صرف كاستنج")
assert notes == [("1", "كسر"), ("2", "سبيكة"), ("3", "")], notes
MB.log.clear()
assert a.post_generic_stage("صب الداخلي", "5", 3.0, 0.0, sarf_kind="شجر") is True
assert a.post_generic_stage("صب الداخلي", "6", 2.0, 1.0, sarf_kind="سبيكة", qabd_kind="لحام", note="x") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "• الصرف — سبيكة: 2" in ask[2] and "• القبض — لحام: 1" in ask[2] and "• رصيد لحام في الخزينة:" in ask[2]
gen = sorted((i["row_number"], i["النوع"], i["الوزن"], i["البيان"]) for i in a.invoices.values() if i["الاسم"] == "صب الداخلي")
assert gen == [("5", "صرف صب الداخلي", 3.0, "شجر"), ("6", "صرف صب الداخلي", 2.0, "سبيكة — x"),
               ("6", "قبض صب الداخلي", 1.0, "لحام — x")], gen
MB.log.clear()
assert a.post_generic_stage("صب الداخلي", "6", 1.0, 0.0, sarf_kind="شجر") is False and MB.log[0][1] == "عملية مكررة"
for args, title in ((("صب الداخلي", "", 1.0, 0.0), "رقم الصف مطلوب"), (("صب الداخلي", "9", None, 0.0), "قيمة غير صحيحة"),
                    (("صب الداخلي", "9", 0.0, 0.0), "تنبيه")):
    MB.log.clear()
    assert a.post_generic_stage(*args) is False and MB.log[-1][1] == title, (args, MB.log)
print("✔ الكاستنج: الصرف بنوعه (كسر/سبيكة/عام) والقبض شجرٌ ومسترجع الأشجار وعددها، وكل خانة مرة في الصف؛ "
      "وصب الداخلي: الصرف بنوعه (سبيكة/شجر) والقبض بنوعه — كلٌّ في أول بيان حركته، والتأكيد بأرصدتها")

# ═══ ٦) تفصيل الخزينة: أرصدة متراكمة — السدايا (شغل 4 + شغل 8 − صرف المركبين)، والسلاسل، والسبيكة، والواير واللحام ═══
a.add("صب الداخلي", "قبض صب الداخلي", 6.0, row="1", note="واير — شحنة")
a.add("صب الداخلي", "قبض صب الداخلي", 2.0, row="2", note="لحام")
a.add("صب الداخلي", "قبض صب الداخلي", 9.0, row="3", note="سبيكة")
a.add("صب الداخلي", "قبض صب الداخلي", 4.0, row="4")                        # بلا نوع: لا يُعدّ
a.add("سالم", "صرف ذهب", 15.0, row="1", set_no="5001")                      # صرفٌ للمركّب ← ينقص من السدايا
a.add("سالم", "قبض ذهب", 14.0, row="1", set_no="5001")                      # القبض منه لا يمسّها
# الفترة السابقة: تدخل في «ما قبل الفترة»
a.add("أحمد", "المفنش ٤ بالالف", 7.0, row="1", set_no="4001", period="2026-09")
a.add("سالم", "صرف ذهب", 4.0, row="1", set_no="4001", period="2026-09")
a.add("صب الداخلي", "قبض صب الداخلي", 1.5, row="1", note="واير", period="2026-09")
# الفترة التالية: لا تدخل
a.add("أحمد", "المفنش ٨ بالالف", 100.0, row="1", set_no="6001", period="2026-11")
br = a.treasury_kind_breakdown(M)
got = {k: (v["opening"], v["in"], v["out"], v["balance"]) for k, v in br.items()}
assert got == {"سدايا": (3.0, 87.0, 15.0, 75.0), "سلاسل": (0.0, 32.0, 0.0, 32.0), "كسر": (0.0, 9.0, 10.0, -1.0),
               "سبيكة": (0.0, 9.0, 6.0, 3.0), "شجر": (0.0, 9.0, 7.0, 2.0), "واير": (1.5, 6.0, 2.0, 5.5),
               "لحام": (0.0, 3.0, 3.0, 0.0)}, got
assert [k for k, _s in a.TREASURY_KINDS] == ["سدايا", "سلاسل", "كسر", "سبيكة", "شجر", "واير", "لحام"]
assert sorted((i["الوزن"], sg) for i, sg in br["سدايا"]["moves"]) == [(6.0, 1), (15.0, -1), (40.0, 1), (41.0, 1)]
assert sorted((i["الوزن"], sg) for i, sg in br["شجر"]["moves"]) == [(3.0, -1), (4.0, -1), (9.0, 1)], "مسترجع الأشجار لا يدخل"
prev = a.treasury_kind_breakdown("2026-09")
assert (prev["سدايا"]["balance"], prev["واير"]["balance"]) == (3.0, 1.5) and prev["سدايا"]["opening"] == 0.0
assert a.treasury_kind_breakdown("2026-11")["سدايا"]["opening"] == 75.0
assert a.slot_kind_deltas("المصنعين", [("صرف لحام", 3), ("المفنش ٤ بالالف", 41), ("قبض سلاسل", 12), ("صرف واير", 2),
                                        ("المفنش ٨ بالالف", 5), ("قبض ذهب", 1), ("صرف ذهب", 9)]) \
    == {"لحام": -3, "سدايا": 46, "سلاسل": 12, "واير": -2, "كسر": 1}
assert a.slot_kind_deltas("المركبين", [("صرف ذهب", 10), ("قبض ذهب", 9)]) == {"سدايا": -10}
assert a.sub_balance_lines({"سدايا": -10}) == ["• رصيد سدايا في الخزينة: 75.00 ← 65.00"]
assert a.sub_balance_lines({}) == [] and a.sub_balance_lines({"سدايا": 0.0}) == []
print(f"✔ تفصيل الخزينة (متراكم): {got} — السدايا = شغل 4 + شغل 8 − صرف المركبين، والكسر = قبض/كسر − صرف الكاستنج "
      "كسراً، والشجر = قبض الكاستنج − صرفه، والسبيكة والواير واللحام = قبض الأقسام − صرفها، والفترة التالية لا تدخل")

# ═══ ٦ب) 1.87: «قبل البوليش» ينقص من السدايا و«بعده» يزيدها، والكسر في صرف الأقسام، وولادة الطقم من الشغل ═══
assert a.sb_load("5003") is not None and a.sb_load("5003")["date"] == f"{M}-12", "شغل 4 من اللوحة برقمه ← قالبه"
assert a.sb_load("5001")["created"] == f"{M}-05 10:00:00", "تاريخ ولادة الطقم = أول قبض شغلٍ له"
assert a.sb_load("5002") is not None, "صرفٌ برقم طقمٍ له شغل (سلاسل) ← قالبه"
assert not any(r["set_number"] == "" for r in a.sb_all()) and a.sb_load("7") is None, "بلا رقم تشغيل لا قالب"
a.add("التلميع/البف", "صرف تلميع بف", 20.0, row="1")
a.add("التلميع/البف", "قبض تلميع بف", 18.0, row="1")
a.add(a.SB_NAME, "صرف تلميع بف", 5.0, set_no="5003")                       # «قبل البوليش» من القالب
a.add("ليزر البوليش", "صرف تلميع بف", 1.0, row="2")                        # الليزر لا يدخل
a.add("مسترجع بوليش 1", "قبض تلميع بف", 2.0)                                # حسابٌ آخر لا يدخل
br2 = a.treasury_kind_breakdown(M)
assert br2["سدايا"]["balance"] == round(75.0 - 20 - 5 + 18, 2), br2["سدايا"]
assert sorted((i["الوزن"], sg) for i, sg in br2["سدايا"]["moves"] if i["النوع"].endswith("تلميع بف")) \
    == [(5.0, -1), (18.0, 1), (20.0, -1)]
assert a.slot_kind_deltas("التلميع/البف", [("صرف تلميع بف", 20), ("قبض تلميع بف", 18)]) == {"سدايا": -2}
assert a.TREASURY_KINDS[0] == ("سدايا", "شغل 4/8 − قبل البوليش + بعده − صرف المركبين")
assert "كسر" in a.STAGE_SARF_KINDS and a.STAGE_SARF_KINDS[0] == "سبيكة"
MB.log.clear()
assert a.post_generic_stage("صب الداخلي", "8", 2.0, 0.0, sarf_kind="كسر") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "• الصرف — كسر: 2" in ask[2] and "• رصيد كسر في الخزينة: -1.00 ← -3.00  ⚠️ يصير بالسالب" in ask[2], ask[2]
assert a.treasury_kind_breakdown(M)["كسر"]["balance"] == -3.0
print("✔ السدايا: «قبل البوليش» (صرف بوليش 1 من مراحل التصنيع أو القالب) ينقص منها و«بعده» يزيدها — والليزر لا يدخل؛ "
      "وصرف صب الداخلي «كسر» ينقص من رصيد الكسر")

# الشغل بلا رقم في صفٍّ له رقم: يُحسب لرقم الصف
a.add("أحمد", "المفنش ٨ بالالف", 3.0, row="3")
assert a.sb_mfg_receipts()["5003"]["w8"] == 3.0, "شغل 8 بلا رقم في صف 5003 ← لـ 5003"
# رقم تشغيلٍ يُعطى لصفٍّ له شغل (تعديل الصف): يولد قالبه
for inv in a.invoices.values():
    if inv["الاسم"] == "أحمد" and inv["row_number"] == "7":
        inv["set_number"] = "5007"
a.mark_backup_dirty()
assert a.sb_ensure_born({"5007"}, revive=True) == ["5007"] and a.sb_load("5007")["date"] == f"{M}-12"
assert a.sb_ensure_born({"5007"}) == [], "مرة واحدة"
# عند فتح القالب: كل شغل الفترة المعروضة له قالبه (والفترات الأخرى لا)
a.add("خالد", "المفنش ٤ بالالف", 9.0, row="1", set_no="5100")
assert a.sb_ensure_born(month=M) == ["5100"]
assert a.sb_load("6001") is None and a.sb_load("4001") is None
# قالبٌ حذفه المستخدم لا يعود وحده — إلا إذا أُعطي رقمه لصفٍّ صراحةً
a.sb_set_dismissed({"5200"})
a.add("خالد", "المفنش ٤ بالالف", 1.0, row="2", set_no="5200")
assert a.sb_ensure_born(month=M) == [] and a.sb_ensure_born({"5200"}) == []
assert a.sb_ensure_born({"5200"}, revive=True) == ["5200"] and "5200" not in a.sb_dismissed()
# وضع العرض لا يكتب، والولادة في خطوة التراجع المفتوحة
a.add("خالد", "المفنش ٨ بالالف", 2.0, row="3", set_no="5300")
a.view_only = True
assert a.sb_ensure_born(month=M) == []
a.view_only = False
a._undo_open = step = {}
assert a.sb_ensure_born({"5300"}) == ["5300"] and step["settings"] == {a.SB_PREFIX + "5300": None}
a._undo_open = None
print("✔ ولادة الطقم: الشغل (4/8/سلاسل) برقم تشغيل ← قالبه بتاريخ أول قبض — من اللوحة، أو رقمٌ يُعطى للصف لاحقاً، أو "
      "عند فتح القالب لشغل الفترة؛ والمحذوف لا يعود وحده، ووضع العرض لا يكتب، والتراجع يشملها")

# رقم تشغيل الصف يتغيّر: القالب ينتقل بما كُتب فيه ما لم يبقَ للرقم القديم شيء
r = a.sb_load("5100")
r["customer"] = "عميل"
a.sb_save(r)
for inv in a.invoices.values():
    if inv["set_number"] == "5100":
        inv["set_number"] = "5150"
a.mark_backup_dirty()
assert a.sb_follow_set_number("5100", "5150") is True
assert a.sb_load("5100") is None and a.sb_load("5150")["customer"] == "عميل"
assert a.sb_follow_set_number("5001", "5999") is False and a.sb_load("5001") is not None, "للقديم حركاتٌ باقية"
for inv in a.invoices.values():
    if inv["set_number"] == "5300":
        inv["set_number"] = "5150"
a.mark_backup_dirty()
assert a.sb_record_empty(a.sb_load("5300")) and not a.sb_record_empty(a.sb_load("5150"))
assert a.sb_follow_set_number("5300", "5150") is True and a.sb_load("5300") is None, "قالبٌ فارغ والجديد له قالبه ← يُحذف"
print("✔ رقم تشغيل الصف يتغيّر: قالب الرقم القديم ينتقل إلى الجديد بما كُتب فيه (ويبقى إن بقيت للقديم حركات)، والفارغ "
      "يُحذف إن كان للجديد قالبه")

# ═══ ٧) الواجهة والمصادر ═══
ruf = member("render_unified_fields")
assert '(self.MFG_CHAINS_SLOT, "قبض/سلاسل")' in ruf
sub = member("submit_unified_op")
assert "op_type = self.slot_op_type(slot)" in sub and "بوليش" not in sub
assert '("قبض سلاسل", "قبض/سلاسل")' in member("ROW_EDIT_FIELDS")
row_edit = member("open_row_full_edit_dialog")
assert "self.movement_slot(inv)" in row_edit and "move_note = self.with_note_head(head, new_note)" in row_edit

led = member("refresh_op_ledger_table")
assert 'field = "سلاسل"' in led and "- data['سلاسل']" in led and "(data['مفنش 8'] + data['سلاسل']) * ALLOWANCE_8" in led
assert '"سلاسل"' in member("build_op_ledger_columns")
stage_edit = member("open_stage_op_edit_dialog")
assert "self.with_note_head(qabd_head, new_note)" in stage_edit
gen = member("build_generic_stage_ui")
assert '("qabd_kind", "نوع القبض")' in gen and 'kind_buttons={"sarf": ("عام",) + self.STAGE_SARF_KINDS}' in gen
gen_post = member("post_generic_stage")
assert "self.with_note_head(qabd_kind, note) if qabd_kind in self.RECEIPT_KINDS" in gen_post
assert "self.with_note_head(sarf_kind, note) if sarf_kind" in gen_post
assert "self.post_generic_stage(stage_name," in member("submit_generic_stage_op")
assert "self.post_casting_loss(" in member("submit_casting_loss_op")
assert 'toggles={"qabd_kind": ("عام",) + self.RECEIPT_KINDS}' in gen
assert 'kind_buttons={"sarf": ("عام",) + self.CAST_SARF_KINDS}' in member("build_casting_ui")
bsp = member("build_stage_panel")
assert 'w.setdefault("fields", {})[f"{k}_kind"] = kb' in bsp and "cell = holders.get(k, widget_of[k])" in bsp
assert "weight=0 if k in toggles else 1" in bsp, "خانة الاختيار لا تأخذ عرضاً موحّداً بعد تبديل العملية"
edit_dlg = member("open_stage_op_edit_dialog")
assert "note=self.with_note_head(sarf_head, new_note) if sarf_head else new_note" in edit_dlg, "نوع الصرف يبقى بالتعديل"
assert 'self.lbl_live_treasury.bind("<Button-1>", lambda e: self.show_treasury_breakdown())' in src
assert "self.tabview.treasury_click_callback = self.show_treasury_breakdown" in src
panel = member("sb_build_mfg_panel")
assert 'chain = [m["name"]._entry, m["sarf"]._entry, m["sarf_kinds"], m["kasr"]._entry, m["work"]._entry, kinds,' in panel
assert 'options(grid, self.MFG_SARF_KINDS, "sarf", 40)' in panel and 'placeholder_text="⊘"' in panel and 'options(krow, self.MFG_WORK_KINDS, "work", 48)' in panel
for k in ('"<Return>"', "for seq, d in self.SB_NAV_KEYS.items():", 'frame.bind("<space>"'):
    assert k in panel, k
assert member("SB_NAV_KEYS").strip().endswith('{"<Down>": 1, "<Left>": 1, "<Up>": -1, "<Right>": -1}'), \
    "1.87: الأسهم الأربعة بين الخانات (← التالية و→ السابقة)، والمسافة تغيّر الخيار"
assert '"Right": -1, "Left": 1' not in panel and '"Right": -1, "Left": 1' not in member("sb_build_stage_form")
assert "for seq, d in self.SB_NAV_KEYS.items():" in member("sb_build_stage_form")
assert "self.post_manufacturer_receipt(" in member("sb_mfg_submit")
assert 'self.sb_mfg_fill_owner(st["key"] or "")' in member("sb_show")
print("✔ الواجهة: «قبض/سلاسل» في المصنعين وتعديل الصف وجدوله، ونوع القبض في الأقسام المضافة (ويبقى بالتعديل)، "
      "والنقر على رصيد الخزينة، ولوحة المصنّع في القالب بـ Enter والأسهم وخيارات الشغل")

# 1.84 (بعد التجربة على البرنامج الحقيقي): التتبع ⇄ القالب، ولا تبديل صامت للمصنّع، وللرقم قالبه
track = member("set_tracking_values")
assert "before = p1b if p1b is not None else before" in track and "after = p1a if p1a is not None else after" in track, \
    "«بعد البوليش» ما لم يُرحَّل من القالب = صرف المركّب (لا يضيع بترحيل «قبل» من شغل 4)"
assert 'done = self.sb_post(key, "p1_before", value, parent=tree.winfo_toplevel(), confirm=False)' in src, \
    "تعديل «قبل البوليش» من التتبع لطقمٍ في القالب يعدّل حركة بوليش 1 نفسها"
assert 'v = self.set_tracking_values(key)["polish_before"]' in src
fill = member("sb_mfg_fill_owner")
assert 'if set_number is not None or cur not in self.categories.get("المصنعين", []):' in fill and "if cur == owner:" in fill, \
    "مصنّعٌ اختاره المستخدم لا يُبدَّل بصمت بصاحب الرقم"
assert "self.sb_save(self.sb_new_record(key))" in member("sb_mfg_submit"), "الترحيل من لوحة القالب ← للرقم قالبه"
assert "or key in self.sb_mfg_receipts())" in member("sb_open_search")
assert 'krow.grid(row=4, column=0, columnspan=2' in panel and 'm["sarf_kinds"].grid(row=2, column=0, columnspan=2' in panel, \
    "خيارات الصرف والشغل بأسمائها كاملة في صفٍّ بعرض اللوحة (خيارات الصرف تحت خانته فلا تضيّقها)"
sub_mfg = member("sb_mfg_submit")
assert 'sarf=self._read_weight(m["sarf"]), sarf_kind=m["sarf_kind"]' in sub_mfg
assert 'self.sb_mfg_set_kind(self.MFG_SARF_KINDS[0], group="sarf")' in sub_mfg, "نوع الصرف يعود ذهب بعد الترحيل"
assert 'elif key == "صرف ذهب" and cat == "المصنعين":' in ruf and "self.choose_sarf_type(b)" in ruf
assert 'self.MFG_SARF_SLOTS.get(getattr(self, "selected_sarf_type", "ذهب"), "صرف ذهب")' in member("plan_unified_values")
assert 'else self.SLOT_HEADS.get(slot, ""))' in sub and "self.sub_balance_lines(self.slot_kind_deltas(cat, plan))" in sub
assert 'self.set_sarf_type(sarf_ent[1], "ذهب")' in sub
assert '("صرف لحام", "صرف/لحام"), ("صرف واير", "صرف/واير")' in member("ROW_EDIT_FIELDS")
assert "head = (self.SLOT_HEADS.get(slot)" in row_edit
sbp = member("sb_post")
assert 'if field in ("asm_before", "p1_before", "p1_after"):' in sbp and \
    "self.sub_balance_lines({self.SADAYA: sign * round((value or 0.0) - (old or 0.0), 2)})" in sbp, \
    "صرف المركّب و«قبل البوليش» ينقصان من السدايا و«بعده» يزيدها — في التأكيد"
assert "self.slot_kind_deltas(\"التلميع/البف\", [(\"صرف تلميع بف\", sarf_v), (\"قبض تلميع بف\", qabd_v)])" in \
    member("submit_polish_buff_op")
# 1.87: ولادة الطقم من كل طريق، ورقم التشغيل يتبعه قالبه، و٠٫٠٤٪ = «قبل البوليش»
assert "self.sb_ensure_born({key}, revive=bool(self.normalize_set_number(set_number)))" in \
    member("post_manufacturer_receipt")
assert "self.sb_ensure_born({typed} if typed else self.row_set_numbers(name, row_key), revive=bool(typed))" in sub
row_edit_src = member("open_row_full_edit_dialog")
assert "self.sb_follow_set_number(cur_set, new_set_no)" in row_edit_src and \
    "self.sb_ensure_born({new_set_no}, revive=changed)" in row_edit_src
ren = member("rename_op_ledger_set_number")
assert "self.sb_follow_set_number(old, new_val)" in ren and "self.sb_ensure_born({new_val}, revive=True)" in ren
assert "self.sb_ensure_born(month=self.current_display_month)" in member("refresh_set_builder")
assert "self.sb_set_dismissed(self.sb_dismissed() | {key})" in member("sb_delete")
assert 'self._inv_edits = getattr(self, "_inv_edits", 0) + 1' in member("save_invoice_to_db")
for fn in ("sb_mfg_receipts", "sb_moves_index", "sb_sale_index", "sb_is_sold", "assembler_set_index"):
    assert 'getattr(self, "_inv_edits", 0)' in member(fn), f"{fn}: تعديلٌ في مكانه (رقم تشغيل الصف) يحدّث الفهرس"
assert "p04 = p1b\n" in member("sb_values") and 'cell_key == "p04" and v["mfg"]' not in member("sb_render")
tb = member("show_treasury_breakdown")
assert '("النوع", "المصدر", "رصيد سابق", "داخل", "خارج", "الرصيد")' in tb and '"داخل" if sign > 0 else "خارج"' in tb
assert 'text=f"الطقم {key} — {status}' not in member("sb_render"), "معلومات الطقم سطران (يتّسع العمود للوحة)"
assert 'specs += [(k, label, 0 if k in toggles else 1) for k, label in fields]' in member("build_stage_panel")
bar = member("refresh_stage_buttons")
assert bar.index("self.lbl_op_status.pack(side=\"left\", padx=6)") > bar.index("self.stage_buttons[key] = b"), \
    "رسالة الترحيل بعد أزرار المراحل (لا تضيّقها)"
assert 'w["note"].focus_set()' in member("build_stage_panel"), "اختيار نوع القبض ← البيان"
print("✔ التتبع ⇄ القالب ⇄ المركبين، والمصنّع لا يُبدَّل بصمت، وللرقم المرحَّل من اللوحة قالبه، وأزرار المراحل كاملة")

# 1.86: جانب القالب بسيط — بلا سجل حركات ولا نصوص ثابتة (التفاصيل ومفتاح الألوان في تلميح الشارة)، وبطاقة المرحلة
# وأزرار المراحل تحتها (المصنعين دائماً، و＋ يضيف الكاستنج أو قسماً مضافاً، والزر الأيمن يزيله)
sbt = member("build_set_builder_tab")
assert 'st["chip_tip"] = HoverTip(st["chip"], "")' in sbt and "self.sb_build_stage_bar()" in sbt
assert 'self.sb_select_stage(self.SB_MFG_STAGE, focus=False)' in sbt and 'self.sb_build_mfg_panel(st["stage_card"])' in sbt
assert "ttk.Treeview" not in sbt and "sb_fill_log" not in src and "log_title" not in src, "لا سجل حركات في جانب القالب"
assert "tip.text = (text + \"\\n\\n\" if text else \"\") + self.SB_HELP" in member("sb_set_info")
bar186 = member("sb_build_stage_bar")
assert 'items = [self.SB_MFG_STAGE] + self.sb_side_stages() + ["+"]' in bar186
assert 'b.bind("<Button-3>", lambda e, k=key: self.sb_stage_context(e, k), add="+")' in bar186
assert 'self.set_setting(self.SB_STAGES_KEY, json.dumps(list(stages), ensure_ascii=False))' in member("sb_set_side_stages")
assert 'return ["الكاستنج"] + [c for c in self.categories.get("أقسام_خياس_إضافية", []) if c != "الكاستنج"]' in \
    member("sb_side_stage_options")
form186 = member("sb_build_stage_form")
assert 'line(1, "صرف", one("sarf"))' in form186 and 'kinds(2, "sarf", self.CAST_SARF_KINDS, 50)' in form186
assert 'line(3, "قبض شجر", pair("qabd", "مسترجع", "recover"))' in form186
assert 'kinds(2, "sarf", self.STAGE_SARF_KINDS, 50)' in form186
assert 'kinds(4, "qabd", ("عام",) + self.RECEIPT_KINDS, 44)' in form186
sub186 = member("sb_stage_submit")
assert "ok = self.post_casting_loss(row, rw(e[\"sarf\"]), rw(e[\"qabd\"]), rw(e[\"trees\"]), rw(e[\"recover\"])," in sub186
assert "ok = self.post_generic_stage(stage, row, rw(e[\"sarf\"]), rw(e[\"qabd\"]), sarf_kind=g[\"sarf\"][\"sel\"]," in sub186
assert 'self.sb_stage_set_option(sf, group, gg["values"][0])' in sub186, "الخيارات تعود لأولها بعد الترحيل"
print("✔ جانب القالب البسيط: الشارة بتلميحها، وبطاقة المرحلة، وأزرار المراحل (＋ والإزالة)، والكاستنج وصب الداخلي "
      "بمحرّك مراحل التصنيع")

print("\n✅ قبض المصنّعين وشغل 4 وبوليش 1 والسلاسل ونوع القبض وتفصيل الخزينة: كل قيمة إلى مكانها")
