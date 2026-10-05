# -*- coding: utf-8 -*-
"""
السحابة الخفيفة (الدفعة ٢٠) — من دوال البرنامج نفسها:

  • نسخة السحابة بلا فهارس وبلا صفحات فارغة: البيانات نفسها صفاً بصف (يرى المدير كل شيء)،
    والفهارس يعيد البرنامج بناءها عند فتح القاعدة؛ ومضغوطة بـ xz — أصغر بكثير من قبل.
  • بصمة المحتوى: لا تتغيّر بوقت اللقطة ولا بحالة المزامنة المحلية ولا بتعديل لا يغيّر قيمة،
    وتتغيّر بأي حركة — فالنسخة المطابقة لا تُرفع مرة أخرى، والرفع اليدوي يُرفع دائماً.
  • الجدولة: رفع عند أول تشغيل، ثم عند التغيير فقط وبحد أدنى ٣٠ ثانية بين رفعين،
    ونسخة يومية احتياطية، وإعادة محاولة بعد الفشل، و«آخر ظهور» مرة في الدقيقة.
"""
import ast, base64, datetime, hashlib, io, lzma, os, shutil, sqlite3, sys, tempfile, textwrap, threading, time, zlib

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.split("\n")
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def member_src(name):
    x = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
             or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    return textwrap.dedent(ast.get_source_segment(src, x))


errors = []
ns = {"os": os, "sqlite3": sqlite3, "hashlib": hashlib, "threading": threading, "time": time, "datetime": datetime,
      "base64": base64, "zlib": zlib, "lzma": lzma, "APP_VERSION": "9.9.9", "IS_ADMIN_BUILD": False,
      "CURRENT_SYNC_TOKEN": "tok", "log_cloud_error": lambda *a, **k: errors.append(a)}
for name in ("MIRROR_META_TIME", "MIRROR_META_VERSION", "BACKUP_MAGIC", "BACKUP_MAGIC_XZ", "SQLITE_HEADER",
             "_remove_db_files", "DIGEST_SKIP_TABLES", "db_content_digest", "snapshot_db_bytes",
             "encode_backup_payload", "decode_backup_payload", "rpc_missing", "_LAST_BACKUP_DIGEST",
             "BACKUP_UNCHANGED", "cloud_upload_backup"):
    exec(module_src(name), ns)

TMP = tempfile.mkdtemp(prefix="cloud_light_")
db = os.path.join(TMP, "client.db")
con = sqlite3.connect(db)
con.execute("PRAGMA journal_mode=WAL")
con.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, date_time TEXT, name TEXT, op_type TEXT, "
            "weight REAL, settled_status TEXT, note TEXT, set_number TEXT)")
con.execute("CREATE TABLE names (name TEXT, category TEXT, UNIQUE(name, category))")
con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
con.execute("CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT)")
con.execute("CREATE INDEX idx_inv_date ON invoices(date_time)")
con.execute("CREATE INDEX idx_inv_name ON invoices(name)")
con.execute("CREATE INDEX idx_inv_status ON invoices(settled_status)")
con.executemany("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)",
                [(i, f"2026-{1 + i % 9:02d}-{1 + i % 27:02d} 10:{i % 60:02d}:00", f"عامل {i % 25}",
                  ("صرف ذهب", "قبض ذهب", "مبيعات ذهب")[i % 3], round(i * 0.37 % 97, 2), "ACTIVE", "",
                  str(70000 + i // 4)) for i in range(1, 12001)])
con.executemany("INSERT INTO names VALUES (?,?)", [(f"عامل {i}", "المصنعين") for i in range(25)])
con.execute("INSERT INTO settings VALUES ('theme', 'light')")
con.execute("INSERT INTO sync_state VALUES ('last_pull', '1')")
con.commit()                      # الاتصال يبقى مفتوحاً: آخر الحركات في ملف ‎-wal‎ كما أثناء العمل

# ═══ ١) النسخة النحيفة: البيانات نفسها بلا فهارس ═══
full = ns["snapshot_db_bytes"](db)
slim, d1 = ns["snapshot_db_bytes"](db, slim=True, with_digest=True)
out = os.path.join(TMP, "slim.db")
open(out, "wb").write(slim)
s = sqlite3.connect(out)
assert [r[0] for r in s.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")] == []
for table, order in (("invoices", "invoice_id"), ("names", "name"), ("sync_state", "key")):
    assert s.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall() == \
        con.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall(), table
meta = dict(s.execute("SELECT key, value FROM settings"))
assert meta["theme"] == "light" and ns["MIRROR_META_TIME"] in meta, "الإعدادات ووقت اللقطة"
assert s.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and s.execute("PRAGMA freelist_count").fetchone()[0] == 0
s.close()
assert len(slim) < len(full) * 0.75, (len(slim), len(full))
old_payload = base64.b64encode(ns["BACKUP_MAGIC"] + zlib.compress(full, 6)).decode()     # ما كان يُرفع
new_payload = ns["encode_backup_payload"](slim)
assert ns["decode_backup_payload"](new_payload) == slim
saving = 1 - len(new_payload) / len(old_payload)
assert saving > 0.45, saving
print(f"✔ نسخة السحابة: كل الصفوف كما هي (١٢٬٠٠٠ حركة والأسماء والإعدادات) بلا فهارس ولا صفحات فارغة — "
      f"المرفوع {len(new_payload) // 1024} ك.ب بدل {len(old_payload) // 1024} ك.ب (أخف {saving:.0%})")

# ═══ ٢) بصمة المحتوى ═══
_, d2 = ns["snapshot_db_bytes"](db, slim=True, with_digest=True)
assert d1 == d2, "لقطتان لنفس البيانات (بوقتين مختلفين) ببصمة واحدة"
con.execute("UPDATE sync_state SET value='2' WHERE key='last_pull'"); con.commit()
assert ns["snapshot_db_bytes"](db, slim=True, with_digest=True)[1] == d1, "حالة المزامنة المحلية لا تُعدّ تغييراً"
con.execute("UPDATE invoices SET weight = weight WHERE invoice_id = 5"); con.commit()
assert ns["snapshot_db_bytes"](db, slim=True, with_digest=True)[1] == d1, "تعديل لا يغيّر القيمة ليس تغييراً"
con.execute("UPDATE invoices SET weight = 1.23 WHERE invoice_id = 5"); con.commit()
d3 = ns["snapshot_db_bytes"](db, slim=True, with_digest=True)[1]
assert d3 != d1
con.execute("INSERT INTO names VALUES ('جديد', 'المركبين')"); con.commit()
assert ns["snapshot_db_bytes"](db, slim=True, with_digest=True)[1] != d3
print("✔ البصمة تتغيّر بأي تعديل حقيقي (وزن، اسم)، ولا تتغيّر بوقت اللقطة ولا بحالة المزامنة ولا بتعديل لا يغيّر قيمة")


# ═══ ٣) الرفع عند التغيير فقط ═══
class Q:
    def __init__(self, c, fn, args): self.c, self.fn, self.args = c, fn, args
    def execute(self):
        self.c.calls.append((self.fn, len(self.args.get("p_backup_data", ""))))
        if self.c.fail:
            raise RuntimeError("timeout")
        return type("R", (), {"data": []})()


class Client:
    def __init__(self): self.calls, self.fail = [], False
    def rpc(self, fn, args): return Q(self, fn, args)


c = Client()
ns["get_supabase_public_client"] = lambda: c
up = ns["cloud_upload_backup"]
assert up("C1", db) is True and len(c.calls) == 1
assert up("C1", db) == ns["BACKUP_UNCHANGED"] and len(c.calls) == 1, "النسخة المطابقة لا تُرفع"
assert up("C1", db, force=True) is True and len(c.calls) == 2, "الرفع اليدوي/اليومي يُرفع دائماً"
con.execute("INSERT INTO invoices (invoice_id, name, op_type, weight, settled_status) VALUES (99999, 'x', 'صرف ذهب', 1, 'ACTIVE')")
con.commit()
c.fail = True
assert up("C1", db) is False and len(c.calls) == 3
c.fail = False
assert up("C1", db) is True and len(c.calls) == 4, "بعد فشل الرفع يُعاد (البصمة لم تُحفظ)"
assert up("C2", db) is True and len(c.calls) == 5, "كل عميل ببصمته"
assert all(fn == "upload_backup_secure" for fn, _ in c.calls)
print("✔ الرفع عند التغيير فقط: النسخة المطابقة لا تُرفع، والرفع اليدوي يُرفع دائماً، والفاشل يُعاد")

# ═══ ٤) الجدولة ═══
clock = {"now": datetime.datetime(2026, 10, 5, 9, 0, 0)}


class FakeDT(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return clock["now"]


fake_datetime = type("M", (), {"datetime": FakeDT, "timezone": datetime.timezone})
sns = {"datetime": fake_datetime, "BACKUP_UNCHANGED": "unchanged"}
exec("class Base:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in (
    "CLOUD_CHECK_MS", "CLOUD_UPLOAD_MIN_GAP", "CLOUD_FORCED_EVERY", "CLOUD_TOUCH_EVERY",
    "auto_cloud_backup_trigger", "update_cloud_sync_ui")), sns)


class App(sns["Base"]):
    client_id = "C1"

    def __init__(self):
        self.cycles, self.scheduled = [], 0

    def run_cloud_sync_cycle(self, upload=True, force=False, touch=True):
        self.cycles.append((upload, force, touch))

    def schedule_cloud_backup(self):
        self.scheduled += 1


def tick(app, seconds=10):
    clock["now"] += datetime.timedelta(seconds=seconds)
    app.auto_cloud_backup_trigger()
    return app.cycles.pop() if app.cycles else None


a = App()
a.auto_cloud_backup_trigger()
assert a.cycles.pop() == (True, True, True), "أول تشغيل: رفع (مع البصمة) وظهور"
assert tick(a) is None and tick(a) is None, "بلا تغيير: لا رفع ولا طلبات"
a._backup_dirty = True
assert tick(a) == (True, False, False), "تغيير بعد ٣٠ ثانية من آخر رفع: يُرفع"
a._backup_dirty = True
assert tick(a) is None and a._backup_dirty, "تغيير جديد بعد ١٠ ثوانٍ: ينتظر"
assert tick(a) is None
assert tick(a) == (True, False, True), "بعد ٣٠ ثانية يُرفع (ومعه الظهور كل دقيقة)"
seen = [tick(a) for _ in range(12)]
assert [s for s in seen if s] == [(False, False, True), (False, False, True)], "بلا تغيير: ظهور كل دقيقة فقط"
a._last_forced_cloud_upload -= datetime.timedelta(hours=24)
assert tick(a)[:2] == (True, True), "نسخة يومية احتياطية ولو بلا تغيير"
assert a.scheduled >= 16
a.update_cloud_sync_ui(False, True)
assert a._backup_dirty, "فشل الرفع: يُعاد في الدورة التالية"
a._backup_dirty = False
a.update_cloud_sync_ui("unchanged", True)
assert not a._backup_dirty and not hasattr(a, "_last_cloud_sync_ok"), "«لم يتغيّر» ليس رفعاً جديداً في المؤشر"
print("✔ الجدولة: رفع عند التشغيل، ثم عند التغيير فقط (٣٠ ثانية على الأقل بين رفعين)، ونسخة يومية، "
      "وإعادة بعد الفشل، و«آخر ظهور» مرة في الدقيقة بدل كل ١٠ ثوانٍ")

# ═══ ٥) الربط ═══
assert "self.run_cloud_sync_cycle(upload=need_upload, force=force_due, touch=touch_due)" in member_src(
    "auto_cloud_backup_trigger")
assert "cloud_upload_backup(self.client_id, self.db_path, force=True)" in src, "زر «رفع للسحابة الآن» يُرفع دائماً"
init = member_src("init_database")
for idx in ("idx_inv_date", "idx_inv_name", "idx_inv_status", "idx_arch_date", "idx_arch_cat"):
    assert f"CREATE INDEX IF NOT EXISTS {idx}" in init, idx
assert "import lzma" in src
print("✔ الفهارس يعيد البرنامج بناءها عند فتح القاعدة (init_database)، وزر الرفع اليدوي يُرفع دائماً")

con.close()
shutil.rmtree(TMP, ignore_errors=True)
assert not errors or all("فشل رفع" in str(e[0]) for e in errors), errors
print("\n✅ السحابة الخفيفة سليمة")
