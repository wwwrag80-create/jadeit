# -*- coding: utf-8 -*-
"""
برنامج المدير لا يلمس ملفات برنامج العميل على الجهاز نفسه (الدفعة ٢٦).

الخطأ عند المستخدم: لوحة المدير ← فتح حساب عميل:
  «تعذّر تنزيل بيانات العميل من السحابة: [WinError 5] Access is denied:
   ...\\JadeiteERP\\Data\\client_data_<id>.db.mirror_tmp -> ...\\Data\\client_data_<id>.db»
السبب: البرنامجان على جهاز واحد ومرآة المدير كانت **ملف العميل نفسه** في Data — مفتوح في
برنامج العميل فيُرفض استبداله، وإلا استبدله المدير بنسخة السحابة أو حذفه إن تعذّر التنزيل.
"""
import ast, base64, contextlib, datetime, io, lzma, os, re, sqlite3, sys, tempfile, textwrap, types, zlib

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.split("\n")


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def method(cls_name, name):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


TMP = tempfile.mkdtemp(prefix="admin_iso_")
APP = os.path.join(TMP, "JadeiteERP")
errors = []
ns = {"os": os, "sqlite3": sqlite3, "contextlib": __import__("contextlib"), "gc": __import__("gc"),
      "time": types.SimpleNamespace(sleep=lambda s: None), "base64": base64, "zlib": zlib, "lzma": lzma,
      "APP_DATA_DIR": APP, "DATA_DIR": os.path.join(APP, "Data"), "BACKUPS_DIR": os.path.join(APP, "Backups"),
      "log_cloud_error": lambda *a: errors.append(a), "re": re, "datetime": datetime}
os.makedirs(ns["DATA_DIR"]); os.makedirs(ns["BACKUPS_DIR"])
for name in ("_make_dir", "ADMIN_MIRROR_DIR", "_ADMIN_MIRROR_ACTIVE", "client_db_path", "install_admin_mirror",
             "cleanup_admin_mirror_files", "client_backup_dir", "replace_db_file",
             "_remove_db_files", "reset_local_cache", "is_sqlite_db_healthy", "MIRROR_META_SOURCE",
             "mark_mirror_source", "BACKUP_DOWNLOAD_PROBLEMS", "load_client_mirror"):
    exec(module_src(name), ns)

# ═══ ١) المسارات: العميل كما كان، والمدير في مجلد مستقل ═══
ns["IS_ADMIN_BUILD"] = False
assert ns["client_db_path"]("A1") == os.path.join(APP, "Data", "client_data_A1.db")
assert ns["client_backup_dir"]("A1") == os.path.join(APP, "Backups", "A1")
assert ns["client_backup_dir"](None) == os.path.join(APP, "Backups", "local")
print("✔ نسخة العميل: Data\\client_data_<id>.db وBackups\\<id> كما كانت تماماً")
ns["IS_ADMIN_BUILD"] = True
admin_db = ns["client_db_path"]("A1")
assert admin_db == os.path.join(APP, "AdminMirror", "client_data_A1.db")
assert ns["client_backup_dir"]("A1") == os.path.join(APP, "AdminMirror", "Backups", "A1")
assert os.path.dirname(admin_db) != ns["DATA_DIR"]
print("✔ نسخة المدير: AdminMirror\\client_data_<id>.db ونسخها في AdminMirror\\Backups — لا ملف مشترك مع العميل")


# ═══ ٢) سيناريو المستخدم: برنامج العميل على الجهاز نفسه وقاعدته في Data ═══
# كل اتصال يُغلق صراحةً: على ويندوز لا يُحذف ملف قاعدة ولا يُستبدل ما دام مفتوحاً
# («with sqlite3.connect» يحفظ فقط ولا يُغلق) — فكان هذا الفحص يفشل على ويندوز وحده فيوقف بناء exe
def make_db(path, rows):
    with contextlib.closing(sqlite3.connect(path)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY, name TEXT)")
        con.executemany("INSERT INTO invoices (name) VALUES (?)", [(f"r{i}",) for i in range(rows)])
        con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        con.commit()


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


client_db = os.path.join(ns["DATA_DIR"], "client_data_A1.db")
make_db(client_db, 50)                                   # بيانات العميل الحقيقية على جهازه
before = read_bytes(client_db)


def download_ok(cid, target):
    make_db(target, 40)                                  # نسخة السحابة (قد تكون أقدم)
    return True, None


ns["cloud_download_backup_checked"] = download_ok
ok, why = ns["load_client_mirror"]("A1", ns["client_db_path"]("A1"))
assert ok and why is None
assert read_bytes(client_db) == before, "المدير غيّر قاعدة برنامج العميل!"
with contextlib.closing(sqlite3.connect(admin_db)) as con:
    assert con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 40
print("✔ المدير نزّل نسخة العميل في مجلده هو (40 حركة)، وقاعدة برنامج العميل (50) لم تُمسّ بايت واحد")

# تعذّر التنزيل: كان المدير يمسح «النسخة السابقة» — وهي كانت قاعدة العميل نفسها
ns["cloud_download_backup_checked"] = lambda cid, target: (False, "network")
work_ns = dict(ns, load_client_mirror=ns["load_client_mirror"])
exec(method("SyncDownWindow", "_work"), work_ns)
s = types.SimpleNamespace(db_path=ns["client_db_path"]("A1"), tenant_id="A1", ok=False, error=None, mode=None,
                          mirror_error=None, _progress=lambda *a: None, _ui=lambda fn: None, destroy=lambda: None)
work_ns["_work"](s)
assert s.error and not os.path.exists(admin_db) and read_bytes(client_db) == before
print("✔ تعذّر التنزيل: تُمسح مرآة المدير وحدها — قاعدة برنامج العميل باقية كما هي")

# ═══ ٣) الملف مفتوح لحظياً (ويندوز): إعادة المحاولة، ثم سبب واضح بلا «WinError» ═══
real_replace = os.replace
calls = []


def flaky(a, b):
    calls.append(1)
    if len(calls) < 3:
        raise PermissionError(5, "Access is denied")
    return real_replace(a, b)


ns["os"] = types.SimpleNamespace(**{k: getattr(os, k) for k in dir(os) if not k.startswith("__")})
ns["os"].replace = flaky
ns["cloud_download_backup_checked"] = download_ok
ok, why = ns["load_client_mirror"]("A1", ns["client_db_path"]("A1"))
assert ok and len(calls) == 3
print("✔ الملف مشغول لحظياً (مضاد فيروسات أو اتصال لم يُغلق): يُعاد الاستبدال تلقائياً فينجح")

# ═══ ٤) المرآة مفتوحة في نافذة أو برنامج مدير آخر (مقفولة دائماً): يُفتح الحساب من ملف جديد ═══
base = admin_db
locked = {base}


def locked_replace(a, b):
    if b in locked:
        raise PermissionError(32, "The process cannot access the file because it is being used by another process")
    return real_replace(a, b)


real_remove = os.remove


def locked_remove(path):
    # ويندوز: الملف المفتوح (وملفا -wal/-shm له) لا يُحذف كما لا يُستبدل
    if any(path == x or path.startswith(x + "-") for x in locked):
        raise PermissionError(32, "The process cannot access the file because it is being used by another process")
    return real_remove(path)


ns["os"].replace = locked_replace
ns["os"].remove = locked_remove
errors.clear()
ok, why = ns["load_client_mirror"]("A1", ns["client_db_path"]("A1"))
first = ns["client_db_path"]("A1")
assert ok and why is None, why
assert first != base and os.path.dirname(first) == os.path.dirname(base)
assert os.path.basename(first).startswith("client_data_A1__") and first.endswith(".db")
with contextlib.closing(sqlite3.connect(first)) as con:
    assert con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 40
assert os.path.exists(base) and errors          # المرآة الأخرى باقية لصاحبها، والسبب مسجَّل
assert not [n for n in os.listdir(os.path.dirname(base)) if n.endswith((".mirror_tmp", ".mirror_new"))]
print("✔ المرآة مفتوحة في نافذة أو برنامج آخر: لا خطأ — نسخة العميل (40 حركة) في ملف جديد بجوارها، والبرنامج "
      "يُفتح منه (client_db_path)، والمرآة الأخرى لا تُمسّ")

# دخول ثانٍ والملف البديل نفسه مفتوح أيضاً: ملف ثالث، والمفتوح يبقى لصاحبه
locked.add(first)
open(first + "-wal", "wb").close()
ok, why = ns["load_client_mirror"]("A1", ns["client_db_path"]("A1"))
second = ns["client_db_path"]("A1")
assert ok and second not in (base, first) and os.path.exists(first) and os.path.exists(first + "-wal")
# أُغلقت النوافذ الأخرى: الدخول التالي يعود للملف الأصلي، وتُحذف البدائل كلها — لا تراكم ملفات
locked.clear()
ns["_ADMIN_MIRROR_ACTIVE"].clear()
ok, why = ns["load_client_mirror"]("A1", ns["client_db_path"]("A1"))
assert ok and ns["client_db_path"]("A1") == base
left = sorted(n for n in os.listdir(os.path.dirname(base)) if n.startswith("client_data_A1__"))
assert left == [], left
print("✔ وإن كان البديل نفسه مفتوحاً: ملف آخر؛ وحين تُغلق النوافذ الأخرى يعود للملف الأصلي وتُحذف البدائل")

# التحديث التلقائي داخل البرنامج (كل دقيقة) على الطريقة نفسها
apply_src = method("GoldSystemApp", "_apply_admin_mirror")
assert "self.db_path = install_admin_mirror(tmp_path, self.client_id, self.db_path)" in apply_src
print("✔ التحديث التلقائي من العميل يضع النسخة الجديدة بالطريقة نفسها (ولا يتوقف إن قُفل الملف لحظتها)")

# لا يمكن الكتابة إطلاقاً (القرص ممتلئ مثلاً): رسالة واضحة بلا «WinError» ولا ملفات مؤقتة
ns["os"].replace = lambda a, b: (_ for _ in ()).throw(PermissionError(5, "Access is denied"))
ns["os"].remove = real_remove
errors.clear()
ok, why = ns["load_client_mirror"]("A1", ns["client_db_path"]("A1"))
assert not ok and "تعذّر حفظ نسخة العميل" in why and "WinError" not in why and errors
assert not [n for n in os.listdir(os.path.dirname(base)) if n.endswith(".mirror_tmp")]
print("✔ وإن تعذّرت الكتابة كلياً: رسالة واضحة بدل [WinError]، ولا ملفات مؤقتة")
ns["os"] = os
ns["_ADMIN_MIRROR_ACTIVE"].clear()

# ═══ ٥) كل المسارات في البرنامج من الدالتين ═══
init = method("GoldSystemApp", "__init__")
assert "self.db_path = client_db_path(client_id) if client_id else old_generic_path" in init
assert "self.backup_dir = client_backup_dir(client_id)" in init
assert __import__("re").search(r"if client_id and not IS_ADMIN_BUILD:\s+migrate_legacy_file\(", init)
assert 'os.path.join(DATA_DIR, f"client_data_' not in src
# استبدال قواعد البيانات كله عبر replace_db_file (بإعادة المحاولة) — os.replace المباشر خارجها لملفات
# التحديث السريع وحدها (مؤشّر الإصدار ومجلده في App، لا قاعدة بيانات)
import ast as _ast
_lines = src.split("\n")
_funcs = []
for _n in _ast.parse(src).body:
    for _m in ([_n] if isinstance(_n, _ast.FunctionDef) else _n.body if isinstance(_n, _ast.ClassDef) else []):
        if isinstance(_m, _ast.FunctionDef):
            _funcs.append((_m.name, "\n".join(_lines[_m.lineno - 1:_m.end_lineno])))
_direct = {name for name, seg in _funcs if "os.replace(" in seg}
assert _direct <= {"replace_db_file", "write_hot_pointer", "install_hot_package"}, _direct
assert "replace_db_file(tmp, dst)" in src and "replace_db_file(tmp, final)" in src
if "class AdminPanel" in src:
    assert "db_path = client_db_path(client_id)" in method("AdminPanel", "open_as_client")
assert "db_path = client_db_path(client_id)" in method("LoginWindow", "try_login")
print("✔ البرنامج ونافذتا الدخول (باسم العميل ومن لوحة المدير) والتحديث التلقائي — كلها من المسار نفسه وبإعادة المحاولة")

print("\n✅ برنامج المدير ومرآته منفصلان عن ملفات برنامج العميل على الجهاز نفسه")
