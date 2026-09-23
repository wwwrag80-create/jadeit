# -*- coding: utf-8 -*-
"""
اختبار سلوكي: استرجاع بيانات العميل بعد حذف البرنامج وإعادة تثبيته.

  ١) إعادة التثبيت ومجلد البيانات باقٍ على القرص (LOCALAPPDATA\\JadeiteERP\\Data)
     ← تُفتح البيانات كما هي، بلا أي تنزيل.
  ٢) جهاز جديد أو حُذف مجلد البيانات ← تُسترجع آخر نسخة من السحابة.
  ٣) شاشة الرفع عند الدخول لا تُنشئ ملفاً فارغاً (كان وجوده يُلغي الاسترجاع
     ثم تُرفع القاعدة الفارغة فوق آخر نسخة سليمة على السحابة).
  ٤) تعذّر الاتصال ← سؤال: إعادة المحاولة، أو البدء فارغاً بموافقة صريحة فقط.
"""
import ast, base64, io, os, sqlite3, tempfile, textwrap

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


tmp = tempfile.mkdtemp()
DATA_DIR = os.path.join(tmp, "Data")
APP_DIR = os.path.join(tmp, "Program")
os.makedirs(DATA_DIR)
os.makedirs(APP_DIR)
os.chdir(APP_DIR)


class FakeCloud:
    def __init__(self, backup=None, fail_times=0):
        self.backup, self.fail_times, self.calls = backup, fail_times, 0

    def rpc(self, name, params):
        assert name == "download_backup"
        cloud = self

        class Q:
            def execute(self_inner):
                cloud.calls += 1
                if cloud.fail_times > 0:
                    cloud.fail_times -= 1
                    raise ConnectionError("no internet")
                data = [{"out_backup_data": cloud.backup}] if cloud.backup else []
                return type("R", (), {"data": data})()
        return Q()


cloud = FakeCloud()
ns = {"os": os, "base64": base64, "DATA_DIR": DATA_DIR,
      "get_app_base_dir": lambda: APP_DIR,
      "get_supabase_public_client": lambda: cloud,
      "log_cloud_error": lambda *a: None}
for fn in ("cloud_fetch_backup", "cloud_download_backup", "local_client_data_exists",
           "restore_client_database"):
    exec(top_func(fn), ns)
restore = ns["restore_client_database"]


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


never = lambda: (_ for _ in ()).throw(AssertionError("لا يجب أن يُسأل المستخدم"))

# نسخة العميل على السحابة: ٣٠٠ حركة
cloud_db = os.path.join(tmp, "cloud.db")
make_db(cloud_db, 300)
cloud.backup = base64.b64encode(open(cloud_db, "rb").read()).decode()

# ═══ ١) إعادة تثبيت ومجلد البيانات باقٍ ═══
db = os.path.join(DATA_DIR, "client_data_A.db")
make_db(db, 450)          # بياناته الأحدث على جهازه
assert restore("A", db, never, never) is True
assert cloud.calls == 0 and count(db) == 450
print("✔ إعادة التثبيت ومجلد البيانات باقٍ: تُفتح بياناته كما هي (٤٥٠ حركة) بلا تنزيل")

# ═══ ٢) جهاز جديد / حُذف مجلد البيانات ═══
db_b = os.path.join(DATA_DIR, "client_data_B.db")
assert restore("B", db_b, never, never) is True
assert cloud.calls == 1 and count(db_b) == 300
print("✔ جهاز جديد أو مجلد بيانات محذوف: تُسترجع آخر نسخة من السحابة (٣٠٠ حركة)")

# ملف قديم بجوار البرنامج (نسخ قديمة جداً): يُرحَّل عند الفتح، لا يُستبدل بالسحابة
open(os.path.join(APP_DIR, "client_data_C.db"), "wb").close()
calls = cloud.calls
assert restore("C", os.path.join(DATA_DIR, "client_data_C.db"), never, never) is True
assert cloud.calls == calls
print("✔ قاعدة قديمة بجوار البرنامج تُرحَّل كما هي — لا تُستبدل بنسخة السحابة")

# ═══ ٣) شاشة الرفع عند الدخول لا تُنشئ ملفاً فارغاً ═══
work = method("SyncDownWindow", "_work")
created = []
ns2 = {"os": os, "IS_ADMIN_BUILD": False,
       "install_sync_schema": lambda p: (created.append(p), make_db(p, 0)),
       "CloudSync": None, "APP_VERSION": "t", "sync_down": None, "reset_local_cache": None}
exec("class W:\n" + textwrap.indent(work, "    ") + "\n"
     "    def _progress(self, *a): pass\n"
     "    def _ui(self, fn): pass\n"
     "    def destroy(self): pass\n", ns2)
w = ns2["W"]()
w.db_path = os.path.join(DATA_DIR, "client_data_D.db")
w.error = None
w._work()
assert w.ok and w.error is None and not created and not os.path.exists(w.db_path)
print("✔ شاشة الرفع لا تُنشئ ملفاً فارغاً حين لا توجد بيانات على الجهاز")
print("  (كان الملف الفارغ يُلغي الاسترجاع ثم يُرفع فوق نسخة السحابة السليمة)")

# والترتيب في الدخول: الاسترجاع قبل شاشة الرفع
login = method("LoginWindow", "try_login")
assert login.index("restore_client_database(") < login.index("SyncDownWindow(")
print("✔ الدخول يسترجع من السحابة قبل شاشة الرفع")

# ═══ ٤) تعذّر الاتصال ═══
cloud.fail_times, asked = 2, []
db_e = os.path.join(DATA_DIR, "client_data_E.db")
assert restore("E", db_e, lambda: asked.append("retry") or True, never) is True
assert asked == ["retry", "retry"] and count(db_e) == 300
print("✔ انقطاع الإنترنت: (إعادة المحاولة) تسترجع البيانات بعد عودة الاتصال")

cloud.fail_times = 99
db_f = os.path.join(DATA_DIR, "client_data_F.db")
assert restore("F", db_f, lambda: False, lambda: False) is False
assert not os.path.exists(db_f)
print("✔ رفض البدء فارغاً: يعود لشاشة الدخول ولا يُنشأ أي ملف")
assert restore("F", db_f, lambda: False, lambda: True) is True
print("✔ البدء فارغاً لا يحدث إلا بموافقة صريحة من المستخدم")

# حساب جديد فعلاً (لا نسخة على السحابة): يبدأ بلا أسئلة
cloud.fail_times, cloud.backup = 0, None
assert restore("G", os.path.join(DATA_DIR, "client_data_G.db"), never, never) is True
print("✔ حساب جديد بلا نسخة على السحابة: يبدأ مباشرة")

# دالة التنزيل القديمة ما زالت ترجع True/False (يستخدمها إصلاح القاعدة التالفة)
cloud.backup = base64.b64encode(open(cloud_db, "rb").read()).decode()
assert ns["cloud_download_backup"]("H", os.path.join(tmp, "h.db")) is True
cloud.fail_times = 1
assert ns["cloud_download_backup"]("H", os.path.join(tmp, "h2.db")) is False
print("✔ cloud_download_backup ما زالت ترجع True/False كما يتوقع إصلاح القاعدة التالفة")

print("\n✅ استرجاع البيانات بعد إعادة التثبيت يعمل، ولا تُطمس نسخة السحابة بقاعدة فارغة")
