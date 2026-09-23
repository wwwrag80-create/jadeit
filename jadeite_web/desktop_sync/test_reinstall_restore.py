# -*- coding: utf-8 -*-
"""
اختبار سلوكي: بيانات العميل بعد حذف البرنامج وإعادة تثبيته.

القاعدة (RECOVERY_AR.md): نسخة العميل **ترفع للسحابة فقط ولا تسحب منها أبداً**،
وتستعيد بياناتها من مجلد التخزين على جهازها نفسه.

  ١) أسماء المجلدات والملفات على جهاز العميل لم تتغيّر:
       %LOCALAPPDATA%\\JadeiteERP\\Data\\client_data_<id>.db
       %LOCALAPPDATA%\\JadeiteERP\\Backups\\<id>\\gold_backup_*.db
  ٢) إعادة التثبيت ومجلد البيانات باقٍ ← تُفتح البيانات كما هي، بلا أي نسخ.
  ٣) ملف القاعدة مفقود ← يُسترجع من أحدث نسخة احتياطية سليمة **على الجهاز**.
  ٤) نسخة العميل لا تنزّل من السحابة إطلاقاً (لا عند الفتح ولا عند التلف).
  ٥) شاشة الرفع عند الدخول لا تُنشئ ملفاً فارغاً (كان يمنع الاسترجاع المحلي).
"""
import ast, io, os, shutil, sqlite3, tempfile, textwrap, time

SRC = "rageh-1-34-14-cloud.py"
src = io.open(SRC, encoding="utf-8").read()
lines = src.split("\n")
tree = ast.parse(src)


def top_func(name):
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def method(cls_name, name):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


# ═══ ١) المسارات على جهاز العميل كما هي ═══
for line in ('APP_FOLDER_NAME = "JadeiteERP"',
             'DATA_DIR = _make_dir(os.path.join(APP_DATA_DIR, "Data"))',
             'BACKUPS_DIR = _make_dir(os.path.join(APP_DATA_DIR, "Backups"))',
             'self.db_path = os.path.join(DATA_DIR, f"client_data_{client_id}.db") if client_id else old_generic_path',
             'self.backup_dir = _make_dir(os.path.join(BACKUPS_DIR, str(client_id) if client_id else "local"))',
             'backup_path = os.path.join(self.backup_dir, f"gold_backup_{timestamp}.db")'):
    assert line in src, f"تغيّر مسار على جهاز العميل: {line}"
print("✔ مجلد البيانات ومجلد النسخ وأسماء الملفات على جهاز العميل كما هي تماماً")

# ═══ تجهيز: البرنامج على جهاز فيه نسخ احتياطية ═══
tmp = tempfile.mkdtemp()
data_dir = os.path.join(tmp, "JadeiteERP", "Data")
backup_dir = os.path.join(tmp, "JadeiteERP", "Backups", "A")
os.makedirs(data_dir)
os.makedirs(backup_dir)


def make_db(path, n):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS invoices (invoice_id INTEGER PRIMARY KEY, weight REAL)")
    con.executemany("INSERT INTO invoices VALUES (?, ?)", [(i, i * 1.5) for i in range(1, n + 1)])
    con.commit()
    con.close()


def count(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    finally:
        con.close()


def cloud_forbidden(*a, **k):
    raise AssertionError("نسخة العميل حاولت التنزيل من السحابة!")


shown = []
ns = {"os": os, "shutil": shutil, "sqlite3": sqlite3, "datetime": __import__("datetime"),
      "IS_ADMIN_BUILD": False, "cloud_download_backup": cloud_forbidden,
      "log_cloud_error": lambda *a: None,
      "messagebox": type("M", (), {"showinfo": staticmethod(lambda *a, **k: shown.append(a)),
                                   "showwarning": staticmethod(lambda *a, **k: shown.append(a))})}
exec(top_func("is_sqlite_db_healthy"), ns)
exec("class App:\n"
     + textwrap.indent(method("GoldSystemApp", "list_local_backups"), "    ") + "\n"
     + textwrap.indent(method("GoldSystemApp", "restore_missing_db_from_local_backup"), "    ") + "\n"
     + textwrap.indent(method("GoldSystemApp", "recover_corrupt_database"), "    ") + "\n"
     "    def after(self, ms, fn): fn()\n", ns)


def app(db_path):
    a = ns["App"]()
    a.db_path, a.backup_dir, a.client_id = db_path, backup_dir, "A"
    return a


# نسخ احتياطية على جهاز العميل: قديمة (٢٠٠) ثم أحدث (٣٥٠) ثم أحدث منها لكنها تالفة
old_b = os.path.join(backup_dir, "gold_backup_20260901_100000.db")
new_b = os.path.join(backup_dir, "gold_backup_20260920_100000.db")
bad_b = os.path.join(backup_dir, "gold_backup_20260921_100000.db")
make_db(old_b, 200)
make_db(new_b, 350)
open(bad_b, "wb").write(b"not a database")
now = time.time()
os.utime(old_b, (now - 300, now - 300))
os.utime(new_b, (now - 200, now - 200))
os.utime(bad_b, (now - 100, now - 100))
files_before = sorted(os.listdir(backup_dir))

# ═══ ٢) إعادة التثبيت ومجلد البيانات باقٍ ═══
db = os.path.join(data_dir, "client_data_A.db")
make_db(db, 450)
init = method("GoldSystemApp", "__init__")
assert "if self.client_id and not os.path.exists(self.db_path):" in init
print("✔ إعادة التثبيت ومجلد البيانات باقٍ: القاعدة موجودة فتُفتح كما هي (لا نسخ ولا تنزيل)")

# ═══ ٣) ملف القاعدة مفقود ← من أحدث نسخة سليمة على الجهاز ═══
os.remove(db)
restored = app(db).restore_missing_db_from_local_backup()
assert restored == new_b and count(db) == 350, restored
print("✔ ملف البيانات مفقود: استُرجع من أحدث نسخة سليمة على الجهاز (٣٥٠ حركة) وتُخطّيت التالفة")
assert sorted(os.listdir(backup_dir)) == files_before
print("✔ لم يُحذف ولم يُعد تسمية أي ملف في مجلد النسخ")
assert shown, "لم يُبلَّغ العميل بالاسترجاع"

# حساب جديد بلا نسخ: يبدأ جديداً بلا تنزيل من السحابة
empty_dir = os.path.join(tmp, "JadeiteERP", "Backups", "NEW")
os.makedirs(empty_dir)
fresh = ns["App"]()
fresh.db_path, fresh.backup_dir, fresh.client_id = os.path.join(data_dir, "client_data_NEW.db"), empty_dir, "NEW"
assert fresh.restore_missing_db_from_local_backup() is None
assert not os.path.exists(fresh.db_path)
print("✔ حساب جديد بلا نسخ على الجهاز: يبدأ جديداً — بلا تنزيل من السحابة")

# ═══ ٤) نسخة العميل لا تنزّل من السحابة إطلاقاً ═══
i_branch = init.index("if self.client_id and not os.path.exists(self.db_path):")
branch = init[i_branch:i_branch + 900]
assert branch.index("if not IS_ADMIN_BUILD:") < branch.index("self.restore_missing_db_from_local_backup()") \
    < branch.index("cloud_download_backup(")
assert "elif not cloud_download_backup(" in branch
print("✔ عند الفتح: نسخة العميل تسترجع من جهازها، والتنزيل من السحابة لنسخة المدير وحدها")

# قاعدة تالفة بلا نسخ سليمة: لا تنزيل من السحابة في نسخة العميل
for f in os.listdir(backup_dir):
    if f != os.path.basename(bad_b):
        os.remove(os.path.join(backup_dir, f))
open(db, "wb").write(b"corrupt")
app(db).recover_corrupt_database()           # cloud_forbidden يرفع خطأ لو استُدعي
print("✔ عند تلف القاعدة: نسخة العميل لا تلجأ للسحابة")

# ═══ ٥) شاشة الرفع عند الدخول لا تُنشئ ملفاً فارغاً ═══
created = []
ns2 = {"os": os, "IS_ADMIN_BUILD": False,
       "install_sync_schema": lambda p: (created.append(p), make_db(p, 0)),
       "CloudSync": None, "APP_VERSION": "t", "sync_down": None, "reset_local_cache": None}
exec("class W:\n" + textwrap.indent(method("SyncDownWindow", "_work"), "    ") + "\n"
     "    def _progress(self, *a): pass\n"
     "    def _ui(self, fn): pass\n"
     "    def destroy(self): pass\n", ns2)
w = ns2["W"]()
w.db_path, w.error = os.path.join(data_dir, "client_data_D.db"), None
w._work()
assert w.ok and w.error is None and not created and not os.path.exists(w.db_path)
print("✔ شاشة الرفع لا تُنشئ ملفاً فارغاً (كان يمنع الاسترجاع من مجلد النسخ)")

# والدخول لا يحوي أي تنزيل للعميل
login = method("LoginWindow", "try_login")
assert "cloud_download_backup" not in login and "download_backup" not in login
print("✔ تسجيل الدخول لا ينزّل شيئاً من السحابة لجهاز العميل")

# ═══ ٦) اتجاه واحد في النسخة الاحتياطية الكاملة أيضاً ═══
calls = []
ns3 = {"os": os, "base64": __import__("base64"), "log_cloud_error": lambda *a: None,
       "get_supabase_public_client": lambda: calls.append("connect") or None}
exec(top_func("cloud_upload_backup"), ns3)
ns3["IS_ADMIN_BUILD"] = True
assert ns3["cloud_upload_backup"]("A", __file__) is False and not calls
print("✔ نسخة المدير لا ترفع نسختها للسحابة (كانت تطمس نسخة العميل الاحتياطية كل ١٠ دقائق)")
ns3["IS_ADMIN_BUILD"] = False
ns3["cloud_upload_backup"]("A", __file__)
assert calls == ["connect"]
print("✔ نسخة العميل ترفع نسختها كالمعتاد")

mgr = method("GoldSystemApp", "open_backup_manager")
i_restore_btn = mgr.index('text="⬇️ استرجاع آخر نسخة من السحابة"')
assert "if IS_ADMIN_BUILD:" in mgr[i_restore_btn - 300:i_restore_btn]
i_upload_btn = mgr.index('text="⬆️ رفع للسحابة الآن"')
assert "if not IS_ADMIN_BUILD:" in mgr[i_upload_btn - 200:i_upload_btn]
print("✔ شاشة النسخ: زر (استرجاع من السحابة) مخفي في نسخة العميل، وزر الرفع مخفي في نسخة المدير")

closing = method("GoldSystemApp", "on_app_closing")
assert "if not IS_ADMIN_BUILD:" in closing
assert "if not IS_ADMIN_BUILD:" in init[init.index("self.schedule_backup()"):]
print("✔ الرفع الدوري وعند الإغلاق لنسخة العميل وحدها")

print("\n✅ العميل يرفع للسحابة فقط، ويستعيد بياناته من جهازه — والمجلدات كما هي")
