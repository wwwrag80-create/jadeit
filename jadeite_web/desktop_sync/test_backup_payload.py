# -*- coding: utf-8 -*-
"""
النسخة الكاملة على السحابة (الدفعة ١٥) — من دوال البرنامج نفسها:

  • تُرفع مضغوطة بعلامتها (xz منذ الدفعة ٢٠)، وتُقرأ بكل الصيغ: xz و zlib (الدفعة ١٥) والقديمة
    غير المضغوطة،
    وأي محتوى غير قاعدة SQLite يُرفض فلا يُكتب ملف تالف مكان القاعدة.
  • الرفع برمز مزامنة الجلسة عبر upload_backup_secure، والرجوع للدالة القديمة فقط
    إن لم تُثبَّت الجديدة بعد — لا عند رفض الرمز (فلا يُتجاوز الفحص ولا تُرفع النسخة مرتين).
  • نسخة المدير لا ترفع، ونسخة العميل لا تنزّل (كما كانتا).
"""
import ast, base64, io, lzma, os, sqlite3, sys, tempfile, zlib

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.split("\n")


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


errors = []
ns = {"os": os, "base64": base64, "zlib": zlib, "lzma": lzma, "IS_ADMIN_BUILD": False, "CURRENT_SYNC_TOKEN": None,
      "log_cloud_error": lambda *a: errors.append(a)}
for name in ("BACKUP_MAGIC", "BACKUP_MAGIC_XZ", "SQLITE_HEADER", "encode_backup_payload", "decode_backup_payload",
             "rpc_missing", "_LAST_BACKUP_DIGEST", "BACKUP_UNCHANGED", "cloud_upload_backup", "_backup_readers",
             "cloud_download_backup"):
    exec(module_src(name), ns)

TMP = tempfile.mkdtemp(prefix="backup_payload_")
db = os.path.join(TMP, "client.db")
with sqlite3.connect(db) as con:
    con.execute("CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, name TEXT, op_type TEXT, weight REAL, "
                "note TEXT, period TEXT)")
    con.executemany("INSERT INTO invoices VALUES (?,?,?,?,?,?)",
                    [(i, f"عامل {i % 15}", "صرف ذهب" if i % 2 else "قبض ذهب", round(i * 0.37, 2), "", "2026-09")
                     for i in range(1, 4001)])
raw = open(db, "rb").read()
ns["snapshot_db_bytes"] = lambda path, slim=False, with_digest=False: (
    (open(path, "rb").read(), "d-" + str(os.path.getmtime(path))) if with_digest else open(path, "rb").read())

# ═══ ١) الضغط والقراءة بالصيغتين ═══
enc = ns["encode_backup_payload"](raw)
blob = base64.b64decode(enc)
assert blob.startswith(ns["BACKUP_MAGIC_XZ"]) and ns["decode_backup_payload"](enc) == raw
legacy = base64.b64encode(raw).decode()
ratio = len(legacy) / len(enc)
assert ratio > 2, ratio
assert ns["decode_backup_payload"](legacy) == raw
zlib_enc = base64.b64encode(ns["BACKUP_MAGIC"] + zlib.compress(raw, 6)).decode()
assert ns["decode_backup_payload"](zlib_enc) == raw
assert len(enc) < len(zlib_enc), "xz أصغر من zlib"
print(f"✔ النسخة تُرفع مضغوطة بـ xz ({len(legacy) // 1024} ك.ب ← {len(enc) // 1024} ك.ب، أصغر {ratio:.1f}×؛ "
      f"وصيغة zlib كانت {len(zlib_enc) // 1024} ك.ب)، والصيغتان الأقدم تُقرآن كما هما")

for bad in (base64.b64encode(b"<html>error</html>").decode(),
            base64.b64encode(ns["BACKUP_MAGIC"] + b"not zlib").decode(),
            base64.b64encode(ns["BACKUP_MAGIC_XZ"] + b"not xz").decode(),
            base64.b64encode(ns["BACKUP_MAGIC_XZ"] + lzma.compress(b"not sqlite")).decode(),
            base64.b64encode(ns["BACKUP_MAGIC"] + zlib.compress(b"not sqlite")).decode()):
    try:
        ns["decode_backup_payload"](bad)
        raise AssertionError("محتوى غير صالح قُبل")
    except ValueError:
        pass
print("✔ محتوى غير قاعدة SQLite (صفحة خطأ، ضغط تالف، ملف آخر) يُرفض")


# ═══ ٢) الرفع: الدالة المحمية برمز أولاً، والقديمة إن لم تُثبَّت ═══
class Q:
    def __init__(self, client, fn, args):
        self.client, self.fn, self.args = client, fn, args

    def execute(self):
        self.client.calls.append((self.fn, self.args))
        err = self.client.errors.get(self.fn)
        if err:
            raise RuntimeError(err)
        payload = self.client.payload
        return type("R", (), {"data": [{"out_backup_data": payload}] if payload else []})()


class Client:
    def __init__(self, errors=None, payload=None):
        self.calls, self.errors, self.payload = [], errors or {}, payload

    def rpc(self, fn, args):
        return Q(self, fn, args)


def upload(client, token):
    ns["get_supabase_public_client"] = lambda: client
    ns["CURRENT_SYNC_TOKEN"] = token
    ns["_LAST_BACKUP_DIGEST"].clear()          # كل حالة هنا رفع جديد (الرفع عند التغيير يُختبر في test_cloud_light)
    return ns["cloud_upload_backup"]("C1", db)


c = Client()
assert upload(c, "tok-1") and [f for f, _ in c.calls] == ["upload_backup_secure"]
args = c.calls[0][1]
assert args["p_sync_token"] == "tok-1" and args["p_client_id"] == "C1"
assert base64.b64decode(args["p_backup_data"]).startswith(ns["BACKUP_MAGIC_XZ"])
print("✔ الرفع برمز مزامنة الجلسة عبر upload_backup_secure وبالصيغة المضغوطة")

c = Client(errors={"upload_backup_secure": "{'code': 'PGRST202', 'message': 'Could not find the function'}"})
assert upload(c, "tok-1") and [f for f, _ in c.calls] == ["upload_backup_secure", "upload_backup"]
print("✔ قبل تثبيت 17_backup_security.sql: يرجع للدالة القديمة تلقائياً فلا يتوقف الرفع")

c = Client(errors={"upload_backup_secure": "{'code': '28000', 'message': 'رمز المزامنة غير صالح'}"})
errors.clear()
assert upload(c, "tok-bad") is False and [f for f, _ in c.calls] == ["upload_backup_secure"] and errors
print("✔ الرمز المرفوض لا يُتجاوز بالدالة القديمة (ولا تُرفع النسخة مرتين)")

c = Client()
assert upload(c, None) and [f for f, _ in c.calls] == ["upload_backup"]
print("✔ جلسة بلا رمز (دخول بلا اتصال): الدالة القديمة كما كانت")

ns["IS_ADMIN_BUILD"] = True
c = Client()
assert upload(c, "tok-1") is False and not c.calls
ns["IS_ADMIN_BUILD"] = False
print("✔ نسخة المدير لا ترفع شيئاً")

# ═══ ٣) التنزيل (المدير): الصيغتان تُكتبان قاعدةً سليمة، والتالف لا يُكتب ═══
ns["SUPABASE_SECRET_KEY"] = "sb_secret_x"
for payload, label in ((enc, "المضغوطة"), (legacy, "القديمة")):
    admin = Client(payload=payload)
    ns["get_supabase_admin_client"] = lambda: admin
    ns["get_supabase_public_client"] = lambda: None
    out = os.path.join(TMP, f"mirror_{label}.db")
    assert ns["cloud_download_backup"]("C1", out)
    with sqlite3.connect(out) as con:
        assert con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 4000
    assert [f for f, _ in admin.calls] == ["download_backup"]
admin = Client(payload=base64.b64encode(b"garbage").decode())
ns["get_supabase_admin_client"] = lambda: admin
out = os.path.join(TMP, "bad.db")
errors.clear()
assert ns["cloud_download_backup"]("C1", out) is False and not os.path.exists(out) and errors
print("✔ المدير يفتح الصيغتين قاعدةً سليمة (4000 حركة)، والنسخة التالفة لا تُكتب مكان القاعدة")

login = next("\n".join(lines[n.lineno - 1:n.end_lineno]) for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "try_login")
assert "download_backup" not in login
print("✔ دخول العميل لا ينزّل شيئاً من السحابة (كما كان)")

import shutil
shutil.rmtree(TMP, ignore_errors=True)
print("\n✅ النسخة الكاملة على السحابة: مضغوطة ومحمية برمز ومقروءة بالصيغتين")
