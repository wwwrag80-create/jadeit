# -*- coding: utf-8 -*-
"""1.97 مراجعة شاملة قبل البيع — «البرنامج يحذف الأسطر» وما يشبهه:
  • تعديل صفٍّ (المصنعين/المركبين، والكاستنج وبقية الأقسام): لا يجمع حركات العملية الواحدة في حركة ولا يوحّد تواريخها
    وبياناتها — الفرق على أحدث حركة (row_slot_plan)، والتاريخ والبيان يتغيّران حين يغيّرهما المستخدم وحدهما.
  • كل تأكيد حذفٍ افتراضيه «لا» (البرنامج يُدار بـ Enter).
  • رقم الحركة لا يُعاد: العدّاد فوق أرقام المحذوفات، ولا يتأخر عن رقمٍ كُتب (استعادة برقمها).
  • لا رقم غير صالح (nan/inf/ضخم) يدخل الحسابات — الحارس في save_invoice_to_db الذي تمرّ به كل حركة.
  • نسخةٌ واحدة من البرنامج على الحساب الواحد (قفل ملف بجوار القاعدة)."""
import ast, io, os, subprocess, sys, tempfile, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
methods = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}


def member(name):
    node = methods.get(name) or next(m for m in cls.body if isinstance(m, ast.Assign)
                                     and getattr(m.targets[0], "id", "") == name)
    return textwrap.dedent(ast.get_source_segment(src, node))


def module_src(name):
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    return ast.get_source_segment(src, node)


# ═══ ١) تعديل الصف لا يحذف أسطراً ═══
ns = {}
exec(member("row_slot_plan").replace("@staticmethod\n", ""), ns)
plan = ns["row_slot_plan"]
a = {"رقم الفاتورة": 1, "التاريخ": "2026-11-03 10:00:00", "الوزن": 10.0}
b = {"رقم الفاتورة": 2, "التاريخ": "2026-11-07 10:00:00", "الوزن": 5.0}
assert plan([a], 9.0) is None and plan([a, b], 0) is None, "حركة واحدة أو تصفير: المسار العادي"
p = plan([b, a], 15.0)
assert [(x["رقم الفاتورة"], w) for x, w in p] == [(1, 10.0), (2, 5.0)], "بلا تغيير: الحركتان كما هما (بترتيب التاريخ)"
p = plan([a, b], 20.0)
assert [w for _x, w in p] == [10.0, 10.0], "الزيادة على أحدث حركة"
assert [w for _x, w in plan([a, b], 12.0)] == [10.0, 2.0], "والنقص منها ما بقيت موجبة"
assert plan([a, b], 9.0) is None and plan([a, b], 10.0) is None, "وإن صارت صفراً أو أقل: حركة واحدة (والزائد للمحذوفات)"
worker = member("open_row_full_edit_dialog")
assert "keep = None if slot == \"العيار بعد الفحص\" else self.row_slot_plan(existing_list, value)" in worker
assert "date_changed = new_date != str(ref_dt)[:10]" in worker and "note_changed = new_note != cur_note" in worker
assert worker.count("if date_changed") >= 3 and "default=messagebox.NO" in worker
stage = member("open_stage_op_edit_dialog")
assert "keep = self.row_slot_plan(existing_list, value)" in stage and "trees_changed" in stage
assert "if date_changed:" in stage and "note_changed = new_note != common_note" in stage
assert "default=messagebox.NO" in stage, "تصفير صف الكاستنج: الافتراضي «لا»"
print("✔ تعديل الصف: حركات العملية كلها تبقى بتواريخها وبياناتها (الفرق على أحدثها)، ولا توحيد للتاريخ والبيان")

# ═══ ٢) كل تأكيد حذفٍ افتراضيه «لا» ═══
for name, m in methods.items():
    body = ast.get_source_segment(src, m)
    if "delete_invoice_from_db(" not in body or name == "delete_invoice_from_db":
        continue
    for node in ast.walk(m):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "askyesno":
            seg = ast.get_source_segment(src, node)
            if "تأكيد الحفظ" in seg:
                continue
            kw = {k.arg: ast.get_source_segment(src, k.value) for k in node.keywords}
            assert "default" in kw and "NO" in kw["default"], f"{name}: تأكيد حذفٍ افتراضيه «نعم» ({seg[:60]})"
assert "default=messagebox.YES if value is not None else messagebox.NO" in member("sb_post_local_asm") \
    if "sb_post_local_asm" in methods else True
print("✔ كل تأكيد حذفٍ في البرنامج افتراضيه «لا» — Enter عابرٌ لا يحذف")

# ═══ ٣) رقم الحركة لا يُعاد ═══
load = member("load_data_from_db")
assert 'SELECT MAX(invoice_id) FROM deleted_invoices' in load, "العدّاد فوق أرقام المحذوفات"
save = member("save_invoice_to_db")
assert "if isinstance(inv_id, int) and inv_id > getattr(self, \"invoice_counter\", 0):" in save
print("✔ العدّاد فوق أرقام المحذوفات، ولا يتأخر عن رقمٍ كُتب")

# ═══ ٤) لا رقم غير صالح ═══
ns = {}
exec("class C:\n" + textwrap.indent(member("MOVEMENT_NUMBER_FIELDS") + "\n" + member("MOVEMENT_NUMBER_LIMIT") + "\n\n@classmethod\n"
                                     + member("invalid_movement_numbers"), "    "), ns)
bad = ns["C"].invalid_movement_numbers
assert bad({"الوزن": 12.5, "قبل": 0.0, "بعد": 750, "trees_count": 3}) == []
assert bad({"الوزن": float("nan")}) == ["الوزن"] and bad({"الوزن": float("inf")}) == ["الوزن"]
assert bad({"الوزن": -float("inf")}) == ["الوزن"] and bad({"الوزن": 2e6}) == ["الوزن"]
assert bad({"الوزن": "abc", "trees_count": float("nan")}) == ["الوزن", "عدد الأشجار"]
assert bad({"الوزن": -5.0}) == [], "السالب له معناه في بعض الحركات (الرصيد الافتتاحي…) — لا يُمنع هنا"
assert save.index("bad = self.invalid_movement_numbers(inv_data)") < save.index("INSERT OR REPLACE INTO invoices"), \
    "الحارس قبل الكتابة"
print("✔ nan وinf والقيم الضخمة لا تدخل الحسابات (الحارس قبل الكتابة، لكل الشاشات والرابط)")

# ═══ ٥) نسخةٌ واحدة على الحساب ═══
ns = {"os": os, "sys": sys}
exec(module_src("acquire_db_lock").replace("def acquire_db_lock", "_DB_LOCKS = {}\n\ndef acquire_db_lock"), ns)
tmp = tempfile.mkdtemp(prefix="jadeite_lock_")
dbp = os.path.join(tmp, "client.db")
assert ns["acquire_db_lock"](dbp) is True and ns["acquire_db_lock"](dbp) is True, "العملية نفسها: مرةً بعد مرة"
other = subprocess.run([sys.executable, "-c", "import sys\nexec(sys.stdin.read())\nprint(acquire_db_lock(sys.argv[1]))", dbp],
                       input="import os\n_DB_LOCKS = {}\n" + module_src("acquire_db_lock"), capture_output=True, text=True)
assert other.stdout.strip() == "False", ("نسخةٌ أخرى من البرنامج لا تأخذ القفل", other.stdout, other.stderr)
init = ast.get_source_segment(src, methods["__init__"])
assert "if not getattr(self, \"view_only\", False) and not acquire_db_lock(self.db_path):" in init
assert init.index("acquire_db_lock(self.db_path)") < init.index("self.init_database()"), "القفل قبل أي كتابة"
print("✔ نسخةٌ واحدة من البرنامج على الحساب الواحد (الثانية تُبلَّغ وتُغلق)")

# ═══ ٦) نسخة في مكانٍ آخر (فلاش/OneDrive) ═══
import sqlite3
ns = {"os": os, "sqlite3": sqlite3}
exec(module_src("replace_db_file").replace("gc.collect()", "pass"), dict(ns, time=__import__("time")))
ns["replace_db_file"] = lambda a, b: os.replace(a, b)
exec("class C:\n" + textwrap.indent(member("export_backup_copy"), "    "), ns)
c = ns["C"]()
c.db_path = os.path.join(tmp, "live.db")
con = sqlite3.connect(c.db_path)
con.execute("PRAGMA journal_mode=WAL")
con.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, weight REAL)")
con.executemany("INSERT INTO invoices VALUES (?, ?)", [(i, i * 1.5) for i in range(1, 51)])
con.commit()                                  # يبقى مفتوحاً: النسخة أثناء العمل (WAL)
out = os.path.join(tmp, "usb", "copy.db")
os.makedirs(os.path.dirname(out))
done, why = c.export_backup_copy(out)
chk = sqlite3.connect(out)
assert done and chk.execute("SELECT COUNT(*), SUM(weight) FROM invoices").fetchone() == (50, 1912.5), (done, why)
assert chk.execute("PRAGMA quick_check").fetchone()[0] == "ok" and not os.path.exists(out + ".partial")
chk.close(); con.close()
assert c.export_backup_copy(c.db_path) == (False, "اختر مكاناً آخر غير قاعدة البيانات نفسها"), "لا تُكتب النسخة فوق القاعدة"
bad, why = c.export_backup_copy(os.path.join(tmp, "no", "such", "dir", "x.db"))
assert bad is False and "تعذّر الحفظ" in why
assert "📤 حفظ نسخة في مكان آخر" in member("open_backup_manager") and "self.export_backup_copy(path)" in member("open_backup_manager")
print("✔ «📤 حفظ نسخة في مكان آخر»: نسخة كاملة سليمة (ولو أثناء العمل) إلى فلاش أو OneDrive")

print("\n✅ 1.97: لا يُحذف سطرٌ بتعديل الصف، والحذف افتراضيه «لا»، ولا رقمٌ يُعاد، ولا قيمة غير صالحة، ولا نسختان على الحساب")
