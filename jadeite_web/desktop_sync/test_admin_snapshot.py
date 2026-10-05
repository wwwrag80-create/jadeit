# -*- coding: utf-8 -*-
"""
اختبار مرآة المدير الحرفية لجهاز العميل — يشغّل الدوال الحقيقية:

  • الرفع: لقطة كاملة ومتّسقة لقاعدة العميل (تشمل ما في ملف WAL) مختومة بوقتها وإصداره
  • المدير يفتح قاعدة العميل نفسها (لا إعادة بناء من سجل الحركات) ويُعلَّم أنها نسخته
  • الاحتياط (سجل الحركات) عند غياب النسخة الكاملة، بلا بقايا جلسة سابقة
  • التحديث الحي: نسخة أحدث من العميل تُعرض مكان الحالية والفترة المعروضة تبقى
  • مفتاح المدير: سبب واضح بدل قائمة فارغة، وحفظه على الجهاز مرة واحدة
"""
import ast, base64, contextlib, datetime, io, os, shutil, sqlite3, sys, tempfile, textwrap, types

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
lines = src.split("\n")
tree = ast.parse(src)
APP = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
SYNCWIN = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SyncDownWindow")


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def method_src(name, cls=APP):
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


def attr_src(name, cls=APP):
    node = next(m for m in cls.body if isinstance(m, ast.Assign)
                and any(getattr(t, "id", None) == name for t in m.targets))
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


TMP = tempfile.mkdtemp(prefix="admin_snapshot_")
errors = []
ns = {"os": os, "sys": sys, "sqlite3": sqlite3, "shutil": shutil, "base64": base64, "datetime": datetime,
      "contextlib": contextlib, "threading": __import__("threading"), "hashlib": __import__("hashlib"),
      "time": __import__("time"), "zlib": __import__("zlib"), "lzma": __import__("lzma"),
      "APP_VERSION": "9.9.9", "IS_ADMIN_BUILD": True, "SUPABASE_AVAILABLE": True,
      "SUPABASE_URL": "https://x", "SUPABASE_SECRET_KEY": "",
      "log_cloud_error": lambda *a, **k: errors.append(a)}
for name in ("MIRROR_META_TIME", "MIRROR_META_VERSION", "MIRROR_META_SOURCE", "ADMIN_LEDGER_FALLBACK_NOTE",
             "BACKUP_MAGIC", "BACKUP_MAGIC_XZ", "SQLITE_HEADER", "decode_backup_payload",
             "_remove_db_files", "DIGEST_SKIP_TABLES", "db_content_digest", "snapshot_db_bytes", "is_sqlite_db_healthy", "reset_local_cache",
             "_backup_readers", "cloud_download_backup", "cloud_backup_stamp", "load_client_mirror",
             "mark_mirror_source", "admin_secret_dir", "_load_admin_secret_key", "save_admin_secret_key",
             "cloud_list_clients", "cloud_list_clients_checked", "_SB_CLIENTS", "_SB_LOCK"):
    exec(module_src(name), ns)


def make_client_db(path, rows):
    """قاعدة عميل بنظام WAL، والاتصال يبقى مفتوحاً فتبقى الحركات في ملف ‎-wal‎ (كما في البرنامج أثناء العمل)"""
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, name TEXT, period TEXT)")
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany("INSERT INTO invoices VALUES (?, ?, ?)", rows)
    con.execute("INSERT INTO settings VALUES ('col_label_x', 'اسمي')")
    con.commit()
    return con


def count(path, sql="SELECT COUNT(*) FROM invoices"):
    with contextlib.closing(sqlite3.connect(path)) as c:
        try:
            return c.execute(sql).fetchone()[0]
        except sqlite3.DatabaseError:
            return 0


# ═══ ١) قراءة الملف مباشرة كانت تُفوّت آخر الحركات ═══
client_db = os.path.join(TMP, "client.db")
rows = [(1000 + i, f"حركة {i}", "2026-08" if i < 30 else "2026-09") for i in range(60)]
live = make_client_db(client_db, rows)
raw_copy = os.path.join(TMP, "raw.db")
with open(client_db, "rb") as f, open(raw_copy, "wb") as g:
    g.write(f.read())
assert count(raw_copy) < 60, "كان يُفترض أن تبقى حركات في ملف WAL"
print(f"✔ الرفع القديم (قراءة الملف مباشرة): وصل {count(raw_copy)} من 60 حركة — الباقي في ملف ‎-wal‎")

snap = ns["snapshot_db_bytes"](client_db)
snap_path = os.path.join(TMP, "snap.db")
with open(snap_path, "wb") as f:
    f.write(snap)
assert count(snap_path) == 60 and count(snap_path, "SELECT COUNT(DISTINCT period) FROM invoices") == 2
with contextlib.closing(sqlite3.connect(snap_path)) as c:
    meta = dict(c.execute("SELECT key, value FROM settings").fetchall())
    mode = c.execute("PRAGMA journal_mode").fetchone()[0]
assert meta["col_label_x"] == "اسمي" and meta["_mirror_app_version"] == "9.9.9" and meta["_mirror_snapshot_at"]
assert mode == "delete", mode
assert count(client_db, "SELECT COUNT(*) FROM settings WHERE key LIKE '_mirror%'") == 0
assert not [f for f in os.listdir(TMP) if ".snapshot" in f]
print("✔ اللقطة الجديدة: الحركات الستون كلها وفترتاها وإعدادات الشاشات، في ملف واحد مستقل")
import threading as _th
_res = []
_ts = [_th.Thread(target=lambda: _res.append(len(ns["snapshot_db_bytes"](client_db)))) for _ in range(4)]
[t.start() for t in _ts]
[t.join() for t in _ts]
assert len(_res) == 4 and len(set(_res)) == 1 and not [f for f in os.listdir(TMP) if ".snapshot" in f]
print("✔ أربع لقطات متزامنة (رفع دوري + عند الإغلاق + يدوي) تنجح كلها بلا تصادم في الملفات المؤقتة")
print("✔ مختومة بوقتها وإصدار البرنامج — في النسخة المرفوعة وحدها، لا في قاعدة العميل")
live.close()

# ═══ ٢) المدير يفتح قاعدة العميل نفسها ═══
calls = []


class FakeRes:
    def __init__(self, data):
        self.data = data


class FakeClient:
    def __init__(self, name, payload=None, fail=None, stamp=None):
        self.name, self.payload, self.fail, self.stamp = name, payload, fail, stamp

    def rpc(self, fn, args):
        calls.append((self.name, fn))
        client = self

        class Q:
            def execute(self_inner):
                if client.fail:
                    raise RuntimeError(client.fail)
                return FakeRes([{"out_backup_data": client.payload}] if client.payload else [])
        return Q()

    def table(self, _t):
        client = self

        class T:
            def select(self_, *a): return self_
            def eq(self_, *a): return self_
            def limit(self_, *a): return self_
            def order(self_, *a, **k): return self_

            def execute(self_):
                if client.fail:
                    raise RuntimeError(client.fail)
                return FakeRes([{"updated_at": client.stamp}] if client.stamp else [])
        return T()


payload = base64.b64encode(snap).decode()
pub = FakeClient("public", payload=payload, stamp="2026-09-27T10:00:00")
adm = FakeClient("admin", payload=payload, stamp="2026-09-27T10:00:00")
ns["get_supabase_public_client"] = lambda: pub
ns["get_supabase_admin_client"] = lambda: adm

admin_db = os.path.join(TMP, "client_data_C1.db")
old = make_client_db(admin_db, [(1, "بقايا جلسة سابقة", "2026-07")])
old.close()
ok, why = ns["load_client_mirror"]("C1", admin_db)
assert ok and why is None
assert count(admin_db) == 60 and count(admin_db, "SELECT COUNT(*) FROM invoices WHERE period='2026-07'") == 0
assert count(admin_db, "SELECT COUNT(*) FROM settings WHERE key='_mirror_source' AND value='snapshot'") == 1
assert calls[-1] == ("public", "download_backup")
print("✔ المدير يفتح قاعدة العميل نفسها: 60 حركة وفترتان — لا فترة ثالثة من بقايا جلسة سابقة")

ns["SUPABASE_SECRET_KEY"] = "sb_secret_test"
calls.clear()
assert ns["cloud_download_backup"]("C1", os.path.join(TMP, "x.db"))
assert calls == [("admin", "download_backup")]
adm.fail = "boom"
calls.clear()
assert ns["cloud_download_backup"]("C1", os.path.join(TMP, "y.db"))
assert calls == [("admin", "download_backup"), ("public", "download_backup")]
adm.fail = None
print("✔ التنزيل بمفتاح المدير أولاً، وبالمفتاح العام إن تعذّر")
ns["SUPABASE_SECRET_KEY"] = ""
_saved_stamp = pub.stamp
pub.stamp = None
assert ns["cloud_backup_stamp"]("C1") is None          # فراغ من المفتاح العام = غير معروف
ns["SUPABASE_SECRET_KEY"] = "sb_secret_test"
adm.stamp = None
assert ns["cloud_backup_stamp"]("C1") == ""            # فراغ من مفتاح المدير = لا نسخة فعلاً
adm.stamp = pub.stamp = _saved_stamp
assert ns["cloud_backup_stamp"]("C1") == _saved_stamp
ns["SUPABASE_SECRET_KEY"] = ""
print("✔ جواب فارغ بالمفتاح العام «غير معروف» (قد تحجبه الصلاحيات) فلا يتوقّف التحديث التلقائي")

pub_empty = FakeClient("public")
ns["get_supabase_public_client"] = lambda: pub_empty
ns["SUPABASE_SECRET_KEY"] = ""
keep = os.path.join(TMP, "keep.db")
shutil.copy(snap_path, keep)
ok, why = ns["load_client_mirror"]("C2", keep)
assert not ok and "لا توجد نسخة كاملة" in why and count(keep) == 60
print("✔ بلا نسخة كاملة من العميل: يُرجع السبب ولا يمسّ شيئاً (والاحتياط يقرّر)")
ns["get_supabase_public_client"] = lambda: pub

# ═══ ٣) نافذة التجهيز: النسخة الكاملة أولاً، والاحتياط بلا بقايا ═══
work_ns = dict(ns)
reset_calls = []
work_ns.update({"SYNC_AVAILABLE": True, "reset_local_cache": lambda p: reset_calls.append(p),
                "install_sync_schema": lambda p: None, "CloudSync": None,
                "sync_down": lambda *a, **k: reset_calls.append("sync_down")})
exec(method_src("_work", SYNCWIN), work_ns)


def run_work(mirror_ok, api, key=""):
    reset_calls.clear()
    work_ns["SUPABASE_SECRET_KEY"] = key
    work_ns["load_client_mirror"] = lambda cid, p: (True, None) if mirror_ok else (False, "لا نسخة")

    class Up:
        def __init__(self, **k): pass
        def pending_count(self): return 0
    work_ns["CloudSync"] = Up
    s = types.SimpleNamespace(db_path="db", api=api, tenant_id="C1", cloud_only=True, ok=False, error=None,
                              mode=None, mirror_error=None,
                              _progress=lambda *a: None, _ui=lambda fn: None, destroy=lambda: None)
    work_ns["_work"](s)
    return s


s = run_work(True, None)
assert s.ok and s.mode == "mirror" and reset_calls == []
s = run_work(False, None)
assert not s.ok and s.error == "لا نسخة" and reset_calls == ["db"]
s = run_work(False, types.SimpleNamespace(sync_token="tok"))
assert s.ok and s.mode == "ledger" and reset_calls == ["db", "sync_down"]
print("✔ التجهيز: النسخة الكاملة أولاً (بلا رمز مزامنة)؛ وإن غابت فسجل الحركات من قاعدة نظيفة مع تنبيه")
print("✔ وبلا نسخة ولا رمز: لا تُعرض بقايا جلسة سابقة كأنها بيانات العميل")

# ═══ ٤) التحديث الحي داخل جلسة المدير ═══
M = {}
body = "\n".join(textwrap.indent(attr_src(a), "    ") for a in ("ADMIN_MIRROR_POLL_MS", "ADMIN_MIRROR_FULL_EVERY"))
body += "\n" + "\n".join(textwrap.indent(method_src(m), "    ") for m in (
    "admin_mirror_info", "show_admin_mirror_status", "_admin_ui_busy", "refresh_admin_mirror",
    "_apply_admin_mirror"))
extra = '''
def get_setting(self, key, default=None):
    with contextlib.closing(sqlite3.connect(self.db_path)) as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default
def init_database(self): self.log.append("init")
def load_data_from_db(self):
    self.log.append("load"); self.current_display_month = "2026-10"
def update_period_selector(self): self.log.append("periods")
def recalculate_all(self): self.log.append("recalc")
def winfo_children(self): return []
def after(self, ms, fn=None):
    if ms == 0 and fn: fn()
'''
M.update(ns)
M.update({"tk": types.SimpleNamespace(Toplevel=type("T", (), {})),
          "threading": types.SimpleNamespace(Thread=lambda target, daemon: types.SimpleNamespace(start=target))})
exec("class A:\n" + body + "\n" + textwrap.indent(extra, "    "), M)


class Label:
    def __init__(self): self.text = ""
    def configure(self, **k): self.text = k.get("text", self.text)


a = M["A"]()
a.client_id, a.db_path, a.log, a.lbl_cloud_sync = "C1", admin_db, [], Label()
a.current_display_month = "2026-08"
a._mirror_stamp, a._mirror_ticks, a._mirror_busy = "2026-09-27T10:00:00", 0, False
M["IS_ADMIN_BUILD"] = True
M["APP_VERSION"] = "1.0.0"          # برنامج المدير بإصدار غير إصدار العميل

a.show_admin_mirror_status()
assert a.lbl_cloud_sync.text.startswith("📥 نسخة العميل: ") and "⚠️" in a.lbl_cloud_sync.text   # 9.9.9 ≠ إصدار المدير
M["APP_VERSION"] = "9.9.9"
a.show_admin_mirror_status()
assert "⚠️" not in a.lbl_cloud_sync.text
print(f"✔ شريط المدير يعرض وقت نسخة العميل ({a.lbl_cloud_sync.text.split(': ', 1)[1]}) ويُنبّه إن اختلف إصدار البرنامجين")

pub.stamp = adm.stamp = "2026-09-27T10:00:00"
a.refresh_admin_mirror(manual=False)
assert a.log == [] and count(admin_db) == 60
print("✔ الفحص الخفيف: وقت النسخة لم يتغيّر ← لا تنزيل ولا إعادة عرض")

# العميل سجّل حركة جديدة ورفع لقطة أحدث
live = sqlite3.connect(client_db)
live.execute("INSERT INTO invoices VALUES (2000, 'حركة جديدة عند العميل', '2026-09')")
live.commit()
newer = ns["snapshot_db_bytes"](client_db)
live.close()
pub.payload = base64.b64encode(newer).decode()
pub.stamp = "2026-09-27T10:05:00"
# (اللقطتان في الثانية نفسها ممكنتان: يميّزهما ختم الوقت أو بصمة المحتوى)
a.refresh_admin_mirror(manual=False)
assert count(admin_db) == 61, count(admin_db)
assert a.log == ["init", "load", "periods", "recalc"] and a.current_display_month == "2026-08"
assert a._mirror_stamp == "2026-09-27T10:05:00" and a.lbl_cloud_sync.text.startswith("🔄 وصل تحديث من العميل")
assert count(admin_db, "SELECT COUNT(*) FROM settings WHERE key='_mirror_source'") == 1
print("✔ نسخة أحدث من العميل تُعرض تلقائياً (61 حركة)، والفترة التي يتصفّحها المدير تبقى كما هي")

a.log.clear()
a.refresh_admin_mirror(manual=True)
assert a.log == [], a.log
print("✔ «تحديث من العميل» يدوياً بلا جديد: لا إعادة عرض (يُقارن ختم الوقت وبصمة المحتوى)")

pub.fail = "timed out"
a.refresh_admin_mirror(manual=True)
assert "تعذّر تنزيل" in a.lbl_cloud_sync.text and count(admin_db) == 61
pub.fail = None
print("✔ انقطاع الإنترنت: رسالة واضحة والبيانات المعروضة تبقى")

# ═══ ٥) مفتاح المدير ═══
ns["SUPABASE_SECRET_KEY"] = ""
clients, err = ns["cloud_list_clients_checked"]()
assert clients == [] and err == "no_key"
ns["SUPABASE_SECRET_KEY"] = "sb_secret_old"
ns["get_supabase_admin_client"] = lambda: FakeClient("admin", fail="401 Invalid API key")
clients, err = ns["cloud_list_clients_checked"]()
assert clients == [] and "مرفوض" in err
ns["get_supabase_admin_client"] = lambda: FakeClient("admin", fail="Connection timed out")
clients, err = ns["cloud_list_clients_checked"]()
assert "الإنترنت" in err
print("✔ قائمة الحسابات الفارغة صار لها سبب: مفتاح غير مضبوط، أو مرفوض، أو لا إنترنت")

appdata = os.path.join(TMP, "appdata")
os.environ["LOCALAPPDATA"] = appdata
ns["_sb_create_client"] = lambda url, key: FakeClient("check", fail=None if key == "sb_secret_good" else "401")
ok, why = ns["save_admin_secret_key"]("sb_secret_bad")
assert not ok and "غير صحيح" in why and not os.path.exists(os.path.join(appdata, "JadeiteERP", "admin_secret.key"))
ok, why = ns["save_admin_secret_key"]("  sb_secret_good \n")
assert ok and ns["SUPABASE_SECRET_KEY"] == "sb_secret_good"
assert io.open(os.path.join(appdata, "JadeiteERP", "admin_secret.key"), encoding="utf-8").read() == "sb_secret_good"
os.environ.pop("JADEITE_SUPABASE_SECRET_KEY", None)
assert ns["_load_admin_secret_key"]() == "sb_secret_good"
print("✔ المفتاح يُختبر قبل حفظه، ويُحفظ على جهاز المدير وحده ويُقرأ تلقائياً في كل تشغيل")

adm_src = method_src("refresh_clients", next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AdminPanel"))
assert "cloud_list_clients_checked()" in adm_src and "self.show_admin_key_card(error)" in adm_src
login = method_src("try_login", next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LoginWindow"))
assert "if IS_ADMIN_BUILD:" in login and "ADMIN_LEDGER_FALLBACK_NOTE" in login
assert "self.start_admin_mirror_watch()" in method_src("__init__")
assert "raw, digest = snapshot_db_bytes(db_path, slim=True, with_digest=True)" in module_src("cloud_upload_backup")
print("✔ الدخول بحساب العميل في نسخة المدير يفتح النسخة الكاملة أيضاً (لا يشترط رمز مزامنة)")

assert not errors or all("تعليم" not in str(e[0]) for e in errors), errors
shutil.rmtree(TMP, ignore_errors=True)
print("\n✅ مرآة المدير تعرض جهاز العميل حرفياً")
