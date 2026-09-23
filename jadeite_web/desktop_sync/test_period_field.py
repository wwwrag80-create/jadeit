# -*- coding: utf-8 -*-
"""
اختبار فصل (تاريخ العملية) عن (الفترة المحاسبية):
العملية تُعرض بتاريخها الحيّ، وتُثبَّت في الفترة التي سُجّلت فيها.
"""
import ast, datetime, io, os, sqlite3, tempfile, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def seg(name):
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == name))


# ═══ ١) دوال قراءة الفترة ═══
ns = {}
exec("class S:\n"
     + "    @staticmethod\n" + textwrap.indent(textwrap.dedent(seg("inv_period")), "    ")
     + "\n    @classmethod\n" + textwrap.indent(textwrap.dedent(seg("inv_in_period")), "    "), ns)
S = ns["S"]

# حركة بتاريخ ٩/١ لكنها مثبّتة في فترة ٨
inv = {"التاريخ": "2026-09-01 14:30:00", "period": "2026-08"}
assert S.inv_period(inv) == "2026-08"
assert S.inv_in_period(inv, "2026-08") is True
assert S.inv_in_period(inv, "2026-09") is False
print("✔ حركة بتاريخ 2026-09-01 مثبّتة في فترة 2026-08:")
print("   • تظهر في فترة ٨ ✓   • ولا تظهر في فترة ٩ ✓")

# حركة قديمة بلا عمود فترة → تُشتق من تاريخها (توافق تام)
old = {"التاريخ": "2026-07-15 09:00:00"}
assert S.inv_period(old) == "2026-07"
assert S.inv_in_period(old, "2026-07") is True
print("✔ الحركات القديمة بلا فترة: تُشتق من تاريخها — نفس السلوك السابق حرفياً")

assert S.inv_in_period(inv, None) is True and S.inv_in_period(inv, "") is True
print("✔ فترة فارغة = بلا تقييد")

assert S.inv_period({"التاريخ": "2026-09-01", "period": "   "}) == "2026-09"
print("✔ فترة فارغة نصياً تُعامل كغائبة")

# ═══ ٢) التاريخ الافتراضي = اليوم الحقيقي دائماً ═══
ns2 = {"datetime": datetime, "calendar": __import__("calendar")}
exec("class S2:\n" + textwrap.indent(textwrap.dedent(seg("get_smart_default_date")), "    "), ns2)
app = ns2["S2"]()
today = datetime.datetime.now().strftime("%Y-%m-%d")
for period in ("2026-08", "2026-01", datetime.datetime.now().strftime("%Y-%m")):
    app.current_display_month = period
    assert app.get_smart_default_date() == today, (period, app.get_smart_default_date())
print(f"✔ التاريخ الافتراضي = اليوم الحقيقي ({today}) مهما كانت الفترة المعروضة")

# ═══ ٣) لا فلاتر قديمة متبقية ═══
import re
leftovers = re.findall(r'\["التاريخ"\]\[:7\]|get\("التاريخ", ""\)\[:7\]|\["التاريخ"\]\.startswith|get\("التاريخ", ""\)\.startswith', src)
assert not leftovers, f"فلاتر لم تُحوَّل: {len(leftovers)}"
print("✔ كل فلاتر الفترة تقرأ العمود الصريح — لا فلتر يعتمد على التاريخ")

n_uses = src.count("self.inv_in_period(") + src.count("self.inv_period(")
print(f"✔ عدد مواضع استخدام دوال الفترة: {n_uses}")

# ═══ ٤) الختم المركزي ═══
sv = seg("save_invoice_to_db")
assert 'inv_data["period"] = existing_period or self.current_display_month' in sv
print("✔ كل حركة جديدة تُختم بالفترة المعروضة تلقائياً (ختم مركزي)")
assert "existing_period or" in sv
print("✔ الحركة القائمة تحتفظ بفترتها الأصلية عند التعديل")

# ═══ ٥) الترحيل على قاعدة عميل قديمة ═══
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "old.db")
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT,
    weight REAL, before_w REAL, after_w REAL, note TEXT, settled_status TEXT DEFAULT 'ACTIVE',
    trees_count REAL DEFAULT 0, set_number TEXT DEFAULT '', row_number TEXT DEFAULT '', manual_no TEXT DEFAULT '');
""")
rows = [(1, "2026-07-15 09:00:00", "أحمد", "صرف ذهب", 100.0, 0, 0, "", "ACTIVE", 0, "", "", ""),
        (2, "2026-08-03 10:00:00", "سالم", "قبض ذهب", 50.0, 0, 0, "", "ACTIVE", 0, "", "", "")]
con.executemany("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
con.commit()

# محاكاة الترحيل كما في init_database
cur = con.cursor()
cols = [c[1] for c in cur.execute("PRAGMA table_info(invoices)")]
if "period" not in cols:
    cur.execute("ALTER TABLE invoices ADD COLUMN period TEXT DEFAULT ''")
cur.execute("UPDATE invoices SET period = substr(date_time,1,7) WHERE period IS NULL OR period = ''")
con.commit()

got = dict(cur.execute("SELECT invoice_id, period FROM invoices").fetchall())
assert got == {1: "2026-07", 2: "2026-08"}, got
print("✔ ترحيل قاعدة العميل: كل حركة قديمة أخذت فترة = شهر تاريخها")
print("  → أرقام الفترات السابقة لا تتغيّر بعد التحديث إطلاقاً")

# إعادة الترحيل آمنة
cur.execute("UPDATE invoices SET period = substr(date_time,1,7) WHERE period IS NULL OR period = ''")
con.commit()
assert dict(cur.execute("SELECT invoice_id, period FROM invoices").fetchall()) == got
print("✔ إعادة تشغيل الترحيل لا تُغيّر شيئاً")
con.close()

print("\n✅ التاريخ حيّ والفترة مستقلة — كل شيء سليم")
