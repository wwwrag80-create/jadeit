# -*- coding: utf-8 -*-
"""1.96: «لا يُحذف شيءٌ نهائياً» — سلة المحذوفات ومصادر الحذف الصامت في مراحل التصنيع:
  • المشغّل في قاعدة الجهاز نفسها يحفظ كل حركة قبل حذفها (أي مسار، حتى SQL مباشر) بوقتها وسببها، والتعديل
    (INSERT OR REPLACE) لا يُحسب حذفاً، والسبب لا يعلق بحذفٍ لاحق، والتصفير كله في السلة.
  • السبب من الشاشة التي حذفت (DELETE_REASONS)، ومن الرابط المباشر يُذكر ذلك.
  • مصادر «اختفاء» صفوف المركبين والمصنعين: حذف ورقة القالب لا يحذف حركات الأقسام، وتفريغ خانة في القالب الافتراضيُّ فيه
    «لا»، والتراجع عن إضافة يسمّي حركاته والافتراضيُّ «لا»، وتصفير الصف كله «لا» افتراضياً.
  • الاستعادة بقواعد الحفظ، وفحص الصفوف، والنسخ المحلية اليومية والشهرية، والإغلاق لا يرفع للسحابة."""
import ast, io, os, re, sqlite3, sys, tempfile, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.splitlines()
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


def const(name):
    ns = {}
    exec(member(name), ns)
    return ns[name]


BIN_TABLE, BIN_CONTEXT, BIN_TRIGGER = const("BIN_TABLE_SQL"), const("BIN_CONTEXT_SQL"), const("BIN_TRIGGER_SQL")
COLS = const("INVOICE_COLUMNS")

# ═══ ١) المشغّل: كل حذفٍ محفوظ — من أي مسار ═══
tmp = tempfile.mkdtemp(prefix="bin_")
db = os.path.join(tmp, "t.db")
con = sqlite3.connect(db)
con.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT, weight REAL, "
            "before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE', trees_count REAL DEFAULT 0, "
            "set_number TEXT DEFAULT '', period TEXT DEFAULT '', row_number TEXT DEFAULT '', manual_no TEXT DEFAULT '', "
            "sale_kind TEXT DEFAULT '')")
for sql in (BIN_TABLE, BIN_CONTEXT, BIN_TRIGGER, BIN_TABLE, BIN_CONTEXT, BIN_TRIGGER):   # مرتين: آمن لإعادة التشغيل
    con.execute(sql)
row = lambda i, n, t, w, r="1", s="": (i, "2026-11-05 10:00:00", n, t, w, 0.0, 0.0, "", "ACTIVE", 0.0, s, r, "", "2026-11", "")
marks = ",".join("?" * len(COLS.split(",")))
for r in (row(1, "سالم المركب", "صرف ذهب", 33.0, "1", "9001"), row(2, "سالم المركب", "قبض ذهب", 32.5, "1", "9001"),
          row(3, "أحمد", "صرف ذهب", 40.0), row(4, "أحمد", "المفنش ٤ بالالف", 35.5)):
    con.execute(f"INSERT INTO invoices ({COLS}) VALUES ({marks})", r)
con.commit()
con.execute("INSERT OR REPLACE INTO delete_context (id, reason) VALUES (1, ?)", ("قالب رقم التشغيل 9001: فُرّغت خانة",))
con.execute("DELETE FROM invoices WHERE invoice_id = 1")
con.execute("DELETE FROM delete_context")
con.execute("DELETE FROM invoices WHERE invoice_id = 2")                    # مسارٌ لا يكتب سبباً (أو SQL مباشر)
con.execute(f"INSERT OR REPLACE INTO invoices ({COLS}) VALUES ({marks})", row(3, "أحمد", "صرف ذهب", 41.0))   # تعديل
con.commit()
bin_rows = con.execute(f"SELECT {COLS}, deleted_at, reason, restored_at FROM deleted_invoices ORDER BY bin_id").fetchall()
assert [r[:5] for r in bin_rows] == [(1, "2026-11-05 10:00:00", "سالم المركب", "صرف ذهب", 33.0),
                                     (2, "2026-11-05 10:00:00", "سالم المركب", "قبض ذهب", 32.5)], bin_rows
assert bin_rows[0][-2] == "قالب رقم التشغيل 9001: فُرّغت خانة" and bin_rows[1][-2] == "حذف", "السبب، ولا يعلق بحذفٍ لاحق"
assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", bin_rows[0][-3]) and bin_rows[0][-1] == "", "وقت الحذف"
assert bin_rows[0][10:12] == ("9001", "1") and bin_rows[0][13] == "2026-11", "الحركة كاملة (رقم التشغيل والصف والفترة)"
con.execute("DELETE FROM invoices")                                         # التصفير
con.commit()
assert con.execute("SELECT COUNT(*) FROM deleted_invoices").fetchone()[0] == 4, "التصفير: كل الحركات في السلة"
assert con.execute("SELECT weight FROM deleted_invoices WHERE invoice_id = 3").fetchone()[0] == 41.0, "بآخر قيمة لها"
con.close()
print("✔ المشغّل: كل حركة تُحذف — بسببٍ أو بلا سبب، أو بالتصفير — محفوظة كاملةً بوقتها؛ والتعديل لا يُحسب حذفاً، "
      "والسبب لا يعلق بحذفٍ لاحق، وآمن لإعادة التشغيل")

# ═══ ٢) البرنامج: المشغّل يُنشأ مع القاعدة، والسبب يُكتب في كل مسار حذف ═══
init = member("init_database")
assert "self.ensure_recycle_bin(cursor)" in init and init.index("ALTER TABLE monthly_archive") < init.index(
    "self.ensure_recycle_bin(cursor)"), "بعد أعمدة الحركات كلها"
ens = member("ensure_recycle_bin")
assert 'cursor.execute("DELETE FROM delete_context")' in ens, "سببٌ عالق من إغلاقٍ مفاجئ يُمسح عند الفتح"
dele = member("delete_invoice_from_db")
assert "def delete_invoice_from_db(self, inv_id, reason=None):" in dele
assert dele.index("self._bin_reason(cursor, reason)") < dele.index('DELETE FROM invoices WHERE invoice_id') < dele.index(
    "self._bin_reason(cursor, None)")
assert "self._bin_reason(cur, f\"تراجع" in member("apply_undo_step") and "self._bin_reason(cur, None)" in member("apply_undo_step")
assert "مع حركاته" in member("delete_worker_from_db") and "تصفير البيانات كلها" in member("wipe_system_data")
reasons = const("DELETE_REASONS")
for fn in ("op_ledger_delete_selected", "open_row_full_edit_dialog", "sb_post", "delete_set_move", "delete_selected_sale_invoice",
           "live_delete_any"):
    assert fn in reasons and fn in src.replace(f'"{fn}"', ""), fn
hint = member("delete_reason_hint")
assert "sys._getframe(1)" in hint and '_delete_via' in hint
assert 'over.setdefault("_delete_via", "من الرابط المباشر")' in member("live_run")
print("✔ البرنامج: السلة والمشغّل مع القاعدة، وكل مسار حذف يكتب سببه (الشاشة، التراجع، حذف الاسم، التصفير، الرابط)")

# ═══ ٣) مصادر الاختفاء الصامت في المركبين والمصنعين ═══
sbd = member("sb_delete")
assert "delete_invoice_from_db" not in sbd and "تبقى كما هي في مراحل التصنيع" in sbd and "default=messagebox.NO" in sbd, \
    "حذف ورقة القالب لا يحذف صرف/قبض المركّب ولا حركات البوليش من أقسامها"
post = member("sb_post")
assert "default=messagebox.YES if value is not None else messagebox.NO" in post, "تفريغ خانة في القالب: Enter = لا"
assert "تفريغ الخانة يحذف هذه الحركة من قسم" in post
undo = member("undo_last_action")
assert "default=messagebox.NO if (other or removed) else messagebox.YES" in undo and "ستُزال هذه الحركات من أقسامها" in undo
assert "default=messagebox.NO):" in member("open_row_full_edit_dialog"), "تصفير الصف كله: لا افتراضياً"
print("✔ مصادر الحذف الصامت: ورقة القالب تُحذف وحدها، وتفريغ خانته وCtrl+Z وتصفير الصف — الافتراضيُّ «لا» برسالةٍ تسمّي "
      "ما سيُحذف من أي قسم")

# ═══ ٤) الاستعادة، والسلة، والفحص، والنسخ المحلية ═══
rest = member("bin_restore")
assert "self.save_invoice_to_db(new_id, inv)" in rest and "self.push_undo(" in rest and "restored_at" in rest
assert "self.invoice_counter += 1" in rest, "رقمها مأخوذ ← رقمٌ جديد"
audit = member("stage_rows_audit")
for kind in ('"محذوف"', '"رقم ناقص"', '"صفّان في صف"', '"اسمٌ خارج القسم"', '"فترة أخرى"'):
    assert kind in audit, kind
assert "command=self.open_recycle_bin" in src and "🗑️ المحذوفات" in src
keep = const("LOCAL_BACKUP_KEEP")
assert dict(keep) == {"gold_backup_": 20, "daily_": 60, "monthly_": 24}
pb = member("perform_backup")
assert '("daily_", f"{now:%Y%m%d}")' in pb and '("monthly_", f"{now:%Y%m}")' in pb
close = member("on_app_closing")
assert "self.perform_backup()" in close and "if not IS_ADMIN_BUILD and CLOUD_DATA_SYNC:" in close, \
    "الإغلاق: نسخة محلية — ولا رفع للسحابة (للحسابات وحدها)"
print("✔ الاستعادة بقواعد الحفظ (ورقمٌ جديد إن أُخذ رقمها)، وفحص الصفوف بأنواعه، ونسخٌ محلية دورية ويومية (٦٠) وشهرية "
      "(٢٤)، والإغلاق ينسخ محلياً ولا يرفع للسحابة")

print("\n✅ 1.96: لا يُحذف شيءٌ نهائياً — كل حذفٍ في «المحذوفات» بوقته وسببه ويُستعاد")
