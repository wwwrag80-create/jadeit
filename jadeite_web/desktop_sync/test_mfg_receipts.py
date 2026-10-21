# -*- coding: utf-8 -*-
"""
1.84: قبض المصنّعين (كسر، شغل 4، شغل 8، سلاسل) من مراحل التصنيع ومن قالب رقم التشغيل، و«قبل» بوليش 1 من شغل 4،
ونوع القبض في الأقسام المضافة (سبيكة/واير/لحام)، وتفصيل رصيد الخزينة.

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
           "CHAINS_HEAD", "MFG_CHAINS_SLOT", "MFG_WORK_KINDS", "MFG_WORK_SLOTS", "RECEIPT_KINDS", "NOTE_HEADS",
           "note_head", "with_note_head", "movement_slot", "slot_op_type", "work4_totals", "sync_work4_polish",
           "post_manufacturer_receipt", "find_row_by_set_number", "row_set_numbers", "plan_unified_values",
           "calculate_single_ledger", "worker_rows_raji", "invoices_by_name", "invoices_by_name_period",
           "TREASURY_KINDS", "treasury_kind_breakdown", "_read_weight")


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


ns = {"re": re, "datetime": datetime, "messagebox": MB, "log_cloud_error": lambda *a: None}
exec("\n".join(module_src(n) for n in ("ALLOWANCE_8", "ALLOWANCE_4", "raji_ayar", "LEDGER_FIELD_BY_TYPE")), ns)
exec("class Base:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)
M = "2026-10"


class App(ns["Base"]):
    SB_NAME = "قالب رقم التشغيل"

    def __init__(self):
        self.invoices, self.invoice_counter = {}, 0
        self.categories = {"المصنعين": ["أحمد", "خالد"], "المركبين": ["سالم"], "أقسام_خياس_إضافية": ["صب الداخلي"]}
        self.current_display_month = M
        self.undo, self.recalcs, self.view_only, self.posts = [], 0, False, []

    def mark_backup_dirty(self): self._inv_version = getattr(self, "_inv_version", 0) + 1
    def view_only_blocked(self, silent=False): self.blocked = True
    def recalculate_all(self): self.recalcs += 1
    def register_operation_period(self, d): pass
    def get_operation_datetime(self): return f"{M}-12 10:00:00"
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

# ═══ ٤) شغل 4 ← «قبل» بوليش 1 لرقم التشغيل: ترحيل وتعديل وحذف ═══
before = {}
assert a.sync_work4_polish(before) == ["5001"] and a.polish("5001") == [30.0], a.polish("5001")
four = next(i for i in a.invoices.values() if i["النوع"] == "المفنش ٤ بالالف")
before = a.work4_totals()
four["الوزن"] = 29.5
assert a.sync_work4_polish(before) == ["5001"] and a.polish("5001") == [29.5]
before = a.work4_totals()
assert a.sync_work4_polish(before) == [] and a.posts[-1] == ("5001", 29.5), "بلا تغيير لا ترحيل"
before = a.work4_totals()
a.delete_invoice_from_db(four["رقم الفاتورة"])
assert a.sync_work4_polish(before) == ["5001"] and a.polish("5001") == []
# «قبل» كُتب بغير قيمة شغل 4: لا يُحذف بحذف شغل 4
f2 = a.add("أحمد", "المفنش ٤ بالالف", 10.0, row="1", set_no="5001")
a.sync_work4_polish({})
next(i for i in a.sb_field_moves("5001", "p1_before"))["الوزن"] = 10.4
before = a.work4_totals()
a.delete_invoice_from_db(f2)
assert a.sync_work4_polish(before) == [] and a.polish("5001") == [10.4]
print("✔ شغل 4 برقم تشغيل ← «قبل» بوليش 1 بقيمته (ترحيل، تعديل، حذف) — و«قبل» كُتب بغير قيمته يبقى")

# ═══ ٥) القبض من القالب: قواعد قسم المصنعين، والتأكيد، والحركات في مكانها ═══
MB.log.clear()
a.posts.clear()
assert a.post_manufacturer_receipt("أحمد", "5003", "3", 2.5, 41.0, "شغل 4") is True
ask = [x for x in MB.log if x[0] == "ask"][-1]
assert "قبض/كسر: 2.5" in ask[2] and "شغل 4 (قبض/٤): 41" in ask[2] and "«قبل» بوليش 1 لرقم التشغيل (5003)" in ask[2]
row3 = sorted((i["النوع"], i["الوزن"], i["row_number"], i["set_number"], i["البيان"]) for i in a.invoices.values()
              if i["الاسم"] == "أحمد" and i["row_number"] == "3")
assert row3 == [("المفنش ٤ بالالف", 41.0, "3", "5003", ""), ("قبض ذهب", 2.5, "3", "5003", "")], row3
assert a.polish("5003") == [41.0] and a.undo[-1] == "قبض المصنّع (أحمد) — الصف (3) — 5003"
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
         (("أحمد", "", "1", 1.0, 0.0, "شغل 4"), "رقم التشغيل"),
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
print("✔ يُرفض: غير المصنّع، والقيمة غير الرقمية أو السالبة أو الصفر، ونوعٌ غير الثلاثة، وبلا رقم تشغيل، ورقمٌ لمصنّع "
      "آخر أو لصف آخر، ورقمٌ جديد بلا صف، وصفٌّ برقم آخر — و«لا» في التأكيد، ووضع العرض")

# ═══ ٦) تفصيل الخزينة: قبض الفترة المعروضة من كل نوع ═══
a.add("صب الداخلي", "قبض صب الداخلي", 6.0, row="1", note="واير — شحنة")
a.add("صب الداخلي", "قبض صب الداخلي", 2.0, row="2", note="لحام")
a.add("صب الداخلي", "قبض صب الداخلي", 9.0, row="3", note="سبيكة")
a.add("صب الداخلي", "قبض صب الداخلي", 4.0, row="4")                        # بلا نوع: لا يُعدّ
a.add("أحمد", "المفنش ٤ بالالف", 7.0, row="1", set_no="4001", period="2026-09")  # فترة أخرى
br = a.treasury_kind_breakdown(M)
got = {k: v[0] for k, v in br.items()}
assert got == {"شغل 4": 41.0, "شغل 8": 40.0, "سلاسل": 32.0, "سبيكة": 9.0, "واير": 6.0, "لحام": 2.0}, got
assert [k for k, _s in a.TREASURY_KINDS] == ["شغل 4", "شغل 8", "سلاسل", "سبيكة", "واير", "لحام"]
assert a.treasury_kind_breakdown("2026-09")["شغل 4"][0] == 7.0
print(f"✔ تفصيل الخزينة (قبض الفترة): {got} — من المصنعين ومن خانة القبض في الأقسام المضافة، والفترة وحدها")

# ═══ ٧) الواجهة والمصادر ═══
ruf = member("render_unified_fields")
assert '(self.MFG_CHAINS_SLOT, "قبض/سلاسل")' in ruf
sub = member("submit_unified_op")
assert "op_type = self.slot_op_type(slot)" in sub and "self.sync_work4_polish(work4_before)" in sub
assert "«قبل» بوليش 1 لرقم التشغيل" in sub
assert '("قبض سلاسل", "قبض/سلاسل")' in member("ROW_EDIT_FIELDS")
row_edit = member("open_row_full_edit_dialog")
assert "self.movement_slot(inv)" in row_edit and "move_note = self.with_note_head(head, new_note)" in row_edit
assert "self.sync_work4_polish(work4_before, parent=win)" in row_edit
assert "self.sync_work4_polish(work4_before)" in member("op_ledger_delete_selected")
assert "self.sync_work4_polish(work4_before)" in member("rename_op_ledger_set_number")
led = member("refresh_op_ledger_table")
assert 'field = "سلاسل"' in led and "- data['سلاسل']" in led and "(data['مفنش 8'] + data['سلاسل']) * ALLOWANCE_8" in led
assert '"سلاسل"' in member("build_op_ledger_columns")
stage_edit = member("open_stage_op_edit_dialog")
assert "self.with_note_head(qabd_head, new_note)" in stage_edit
gen = member("build_generic_stage_ui")
assert '("qabd_kind", "نوع القبض")' in gen and 'toggles={"qabd_kind": ("عام",) + self.RECEIPT_KINDS}' in gen
assert "self.with_note_head(kind, note) if kind in self.RECEIPT_KINDS" in member("submit_generic_stage_op")
assert 'self.lbl_live_treasury.bind("<Button-1>", lambda e: self.show_treasury_breakdown())' in src
assert "self.tabview.treasury_click_callback = self.show_treasury_breakdown" in src
panel = member("sb_build_mfg_panel")
assert "chain = [m[\"name\"]._entry, m[\"kasr\"]._entry, m[\"work\"]._entry, kinds, m[\"set\"]._entry, m[\"row\"]._entry]" in panel
for k in ('"<Return>"', '"<Down>"', '"<Up>"', '"Right": -1, "Left": 1, "space": 1'):
    assert k in panel, k
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
assert 'text=kd, width=48' in panel and 'krow.grid(row=2, column=0, columnspan=2' in panel, \
    "خيارات الشغل بأسمائها كاملة في صفٍّ بعرض اللوحة"
assert 'specs += [(k, label, 0 if k in toggles else 1) for k, label in fields]' in member("build_stage_panel")
bar = member("refresh_stage_buttons")
assert bar.index("self.lbl_op_status.pack(side=\"left\", padx=6)") > bar.index("self.stage_buttons[key] = b"), \
    "رسالة الترحيل بعد أزرار المراحل (لا تضيّقها)"
assert 'w["note"].focus_set()' in member("build_stage_panel"), "اختيار نوع القبض ← البيان"
print("✔ التتبع ⇄ القالب ⇄ المركبين، والمصنّع لا يُبدَّل بصمت، وللرقم المرحَّل من اللوحة قالبه، وأزرار المراحل كاملة")

print("\n✅ قبض المصنّعين وشغل 4 وبوليش 1 والسلاسل ونوع القبض وتفصيل الخزينة: كل قيمة إلى مكانها")
