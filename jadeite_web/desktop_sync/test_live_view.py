# -*- coding: utf-8 -*-
"""1.94 → 1.95: «الرابط المباشر» — رابط المدير الثابت إلى جهاز المصنع، بلا سحابة:
  • الخادم: 127.0.0.1 وحده على منفذٍ ثابت، المفتاح السري بمقارنة ثابتة الزمن والخاطئ 404 بعد تأخير، ورؤوس أمان، والطلب
    يُجاب من خيط الواجهة عبر طابور. GET/HEAD للعرض وPOST (نموذجٌ صغير من الصفحة نفسها) للكتابة: النموذج من موقعٍ آخر
    403، والكبير 413، وغير النموذج 415؛ والجواب صفحة أو تحويل (303) أو ملف تنزيل.
  • الرابط الثابت: Tailscale (Funnel أو Serve) أو نفق Cloudflare المسمّى — الرابط من حال الأداة، وتسجيل الدخول أو
    تفعيل الميزة يظهر رابطُه، ورمز النفق في البيئة لا في سطر الأوامر، ويُعاد التشغيل إن توقف.
  • الظل (للقراءة): دوال الشاشات الحقيقية على نسخةٍ ظلّية لا تكتب.
  • الكاتب (للإضافة والتعديل): دوال الترحيل الحقيقية بقيم النموذج مكان الخانات، والكتابة في البرنامج نفسه، وتحديث
    الشاشات على الجهاز، ونوافذ الجهاز تجيب نفسها وتُجمع رسائلها، والطباعة لا تُفتح.
  • البرنامج: الشاشات الست وأدوات الإضافة والبحث والتحكم، وتحكم المدير (قفل التعديل وإيقاف البرنامج وتثبيت الرابط)
    في قاعدة بيانات الجهاز، ولا شيء في السحابة."""
import ast, base64, hashlib, io, json, os, re, shutil, stat, subprocess, sys, tempfile, textwrap, threading, time

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.splitlines()
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

logged = []
ns = {"__name__": "app", "os": os, "sys": sys, "re": re, "time": time, "threading": threading, "base64": base64,
      "hashlib": hashlib,
      "json": json, "shutil": shutil, "subprocess": subprocess, "tk": tk, "ttk": ttk, "ctk": ctk,
      "messagebox": messagebox, "log_cloud_error": lambda *a: logged.append(a), "find_edge_exe": lambda: None}
for name in ("LIVE_PORT", "LIVE_PROVIDERS", "CLOUDFLARED_CANDIDATES", "TAILSCALE_CANDIDATES", "_WINGET_FLAGS",
             "LIVE_WINGET", "LIVE_LINK_RE", "LIVE_HOST_RE", "_TS_ACTION_RE", "_find_tool", "find_cloudflared",
             "find_tailscale", "live_run_capture", "live_link", "live_key_hash", "LiveViewServer", "LiveRelay", "LiveTailscale",
             "LiveCloudflare", "live_same", "new_live_token", "live_escape", "_live_noop", "_LiveSink", "_LiveShadow",
             "_LiveEntry", "_LiveDialogs", "_LiveWriter", "live_tree_tables", "live_shadow_labels"):
    exec(module_src(name), ns)
S = ns["LiveViewServer"]

# ═══ ١) المفتاح والرابط الثابت ═══
tok = ns["new_live_token"]()
assert len(tok) == 43 and re.fullmatch(r"[A-Za-z0-9_-]+", tok) and tok != ns["new_live_token"]()
assert ns["live_same"](tok, tok) and not ns["live_same"](tok, tok[:-1] + ("A" if tok[-1] != "A" else "B"))
assert not ns["live_same"](tok, tok + "x") and not ns["live_same"]("", tok)
for base in ("https://factory-pc.tail1a2b3.ts.net", "https://live.example.com/"):
    link = ns["live_link"](base, tok)
    assert link == f"{base.rstrip('/')}/?k={tok}" and ns["LIVE_LINK_RE"].match(link), link
assert not ns["LIVE_LINK_RE"].match("http://x.com/?k=" + tok) and not ns["LIVE_LINK_RE"].match(link + "&x=<script>")
H = ns["LIVE_HOST_RE"]
assert H.match("live.example.com") and H.match("a-b.c.co") and not H.match("https://x.com") and not H.match("x")
assert not H.match("bad host.com") and not H.match("x.com/path")
assert ns["LIVE_PORT"] == 47815 and ns["LIVE_PROVIDERS"] == ("tailscale", "cloudflare")
assert "Tailscale.Tailscale" in ns["LIVE_WINGET"]["tailscale"] and "Cloudflare.cloudflared" in ns["LIVE_WINGET"]["cloudflare"]
print("✔ مفتاح سري ٣٢ بايتاً ومقارنته ثابتة الزمن؛ والرابط الثابت https://(اسم الجهاز في Tailscale أو نطاقك)/?k=المفتاح "
      "على المنفذ الثابت 47815")

# ═══ ٢) الخادم: يجيب من خيط الواجهة — صفحة أو تحويل أو تنزيل — ويرفض ما سواه ═══
import collections, socket
pending = collections.deque()
srv = S(tok, pending)
srv.FAIL_DELAY = 0.2
port = srv.start()
assert srv.sock.getsockname()[0] == "127.0.0.1", "لا يُستمع إلا على الجهاز نفسه"
stop_ui = threading.Event()
seen = []


def ui_thread():                          # بديل _live_tick: يجيب الطلبات المنتظرة
    while not stop_ui.is_set():
        while pending:
            params, box = pending.popleft()
            seen.append((box["method"], dict(params)))
            if box["method"] == "POST":
                box["location"] = "/?k=" + params["k"] + "&v=add&m=ok1"
            elif params.get("v") == "backup":
                box.update(status=200, body=b"SQLite format 3\x00...", ctype="application/octet-stream",
                           headers=(("Content-Disposition", 'attachment; filename="b.db"'),))
            else:
                box["status"], box["html"] = 200, f"<p>v={params.get('v', '')}</p>"
            box["event"].set()
        time.sleep(0.02)
threading.Thread(target=ui_thread, daemon=True).start()


def raw(req):
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(req)
    data = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    except ConnectionResetError:            # الطلب الكبير: يُردّ ويُغلق قبل قراءة باقيه
        if not data:
            return "RESET", b""
    s.close()
    head, _, body = data.partition(b"\r\n\r\n")
    return head.decode("utf-8"), body


def form_post(body, origin=None, ctype="application/x-www-form-urlencoded", host="127.0.0.1", extra=""):
    data = body.encode("utf-8")
    hdr = (f"POST /?k={tok} HTTP/1.1\r\nHost: {host}\r\nContent-Type: {ctype}\r\nContent-Length: {len(data)}\r\n"
           + (f"Origin: {origin}\r\n" if origin else "") + extra + "\r\n")
    return raw(hdr.encode("utf-8") + data)


h, b = raw(f"GET /?k={tok}&v=sales HTTP/1.1\r\nHost: x\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 200") and b == "<p>v=sales</p>".encode(), (h, b)
for header in ("Cache-Control: no-store", "X-Robots-Tag: noindex, nofollow", "Referrer-Policy: no-referrer",
               "X-Frame-Options: DENY", "frame-ancestors 'none'", "default-src 'none'", "X-Content-Type-Options: nosniff",
               "form-action 'self'", "Content-Type: text/html; charset=utf-8", f"Content-Length: {len(b)}"):
    assert header in h, header
t0 = time.time()
h, b = raw(f"GET /?k={tok[:-1]}Z HTTP/1.1\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 404") and time.time() - t0 >= 0.2 and b"v=" not in b, "مفتاح خاطئ: 404 بعد تأخير"
for req, code in ((b"GET / HTTP/1.1\r\n\r\n", 404), (f"GET /admin?k={tok} HTTP/1.1\r\n\r\n".encode(), 404),
                  (f"DELETE /?k={tok} HTTP/1.1\r\n\r\n".encode(), 405), (f"PUT /?k={tok} HTTP/1.1\r\n\r\n".encode(), 405),
                  (b"garbage\r\n\r\n", 400), (b"GET /?k=" + b"A" * 9000 + b" HTTP/1.1\r\n\r\n", 400)):
    h, b = raw(req)
    assert h.startswith(f"HTTP/1.1 {code}") or (code == 400 and h == "RESET"), (req[:30], h[:40])
h, b = raw(f"HEAD /?k={tok} HTTP/1.1\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 200") and b == b"", "HEAD بلا جسم"

# POST: النموذج يُدمج مع عنوانه ويُحوَّل بعده (303) — والمفتاح الخاطئ والموقع الغريب وغير النموذج والكبير مرفوضة
n_seen = len(seen)
h, b = form_post("a=add&f=mfg&name=%D8%A3%D8%AD%D9%85%D8%AF&f1=20&n=x1", origin="http://127.0.0.1")
assert h.startswith("HTTP/1.1 303") and f"Location: /?k={tok}&v=add&m=ok1" in h, h
method, params = seen[-1]
assert method == "POST" and params["a"] == "add" and params["name"] == "أحمد" and params["f1"] == "20" and params["k"] == tok
h, b = form_post("a=control&do=lock&n=x2", origin="https://evil.example")
assert h.startswith("HTTP/1.1 403"), "نموذج من موقعٍ آخر: مرفوض"
h, b = form_post("a=control&do=lock&n=x3", extra="Sec-Fetch-Site: cross-site\r\n")
assert h.startswith("HTTP/1.1 403"), "والمتصفح يقول إنه من موقعٍ آخر: مرفوض"
h, b = form_post("a=control&do=lock&n=x4", origin="https://factory-pc.tail1a2b3.ts.net", host="factory-pc.tail1a2b3.ts.net")
assert h.startswith("HTTP/1.1 303"), "من الرابط نفسه عبر الوسيط: مقبول"
h, b = form_post('{"a": "add"}', ctype="application/json")
assert h.startswith("HTTP/1.1 415")
h, b = raw(f"POST /?k={tok} HTTP/1.1\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 999999\r\n\r\n"
           .encode())
assert h.startswith("HTTP/1.1 413"), "نموذجٌ كبير: مرفوض قبل قراءته"
h, b = raw(f"POST /?k=WRONG{tok[5:]} HTTP/1.1\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 4\r\n\r\na=b1"
           .encode())
assert h.startswith("HTTP/1.1 404"), "بمفتاحٍ خاطئ: 404"
assert len(seen) == n_seen + 2, "المرفوض لا يصل إلى البرنامج أبداً"
h, b = raw(f"GET /?k={tok}&v=backup HTTP/1.1\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 200") and b.startswith(b"SQLite format 3") and "Content-Type: application/octet-stream" in h \
    and 'Content-Disposition: attachment; filename="b.db"' in h and "text/html" not in h, h
assert srv.served >= 4
stop_ui.set()
time.sleep(0.05)
srv.WAIT_SECONDS = 0.5
h, b = raw(f"GET /?k={tok} HTTP/1.1\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 503") and "مشغول".encode() in b, "الواجهة لا تجيب ← «مشغول» بعد المهلة، لا تعليق"
srv.stop()
time.sleep(1.2)
try:
    socket.create_connection(("127.0.0.1", port), timeout=1).close()
    stopped = False
except OSError:
    stopped = True
assert stopped, "الإيقاف يغلق المنفذ"
# 1.96: حساب عميل — الخادم لا يعرف المفتاح: بصمته وحدها (مفتاح المدير على جهاز المدير)
admin_key = ns["new_live_token"]()
v = S(None, collections.deque(), verifier=ns["live_key_hash"](admin_key))
assert v.token is None and v.key_ok(admin_key) and not v.key_ok(tok) and not v.key_ok(""), "البصمة تكفي للتحقق"
assert ns["live_key_hash"](admin_key) == hashlib.sha256(admin_key.encode()).hexdigest()
v.verifier = ns["live_key_hash"](tok)
assert v.key_ok(tok) and not v.key_ok(admin_key), "مفتاحٌ جديد من المدير يسري وهو يعمل"
assert not S(None, collections.deque()).key_ok(tok), "بلا مفتاح ولا بصمة: لا شيء يفتح"
print("✔ الخادم: 127.0.0.1 وحده، والمفتاح الخاطئ أو المسار الآخر 404 بعد تأخير؛ النموذج يُدمج ويُحوَّل بعده (303)، "
      "والنموذج من موقعٍ آخر 403 والكبير 413 وغير النموذج 415 ولا يصل شيءٌ منها للبرنامج؛ والتنزيل ملفٌّ لا صفحة")

# ═══ ٣) الرابط الثابت: Tailscale وCloudflare بأداتين وهميتين ═══
work = tempfile.mkdtemp(prefix="live_relay_")
old_path = os.environ.get("PATH", "")
os.environ["PATH"] = work + os.pathsep + old_path


def fake_tool(name, body):
    path = os.path.join(work, name)
    with open(path, "w") as f:
        f.write(f"#!{sys.executable}\nimport sys, os, time, json\nW = {work!r}\n" + textwrap.dedent(body))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


mode_file = os.path.join(work, "ts_mode")
ts = fake_tool("tailscale", """
    mode = open(os.path.join(W, "ts_mode")).read().strip()
    open(os.path.join(W, "ts_calls"), "a").write(" ".join(sys.argv[1:]) + "\\n")
    if sys.argv[1:3] == ["status", "--json"]:
        if mode == "login":
            print(json.dumps({"BackendState": "NeedsLogin", "AuthURL": "https://login.tailscale.com/a/abc123"}))
        else:
            print(json.dumps({"BackendState": "Running", "Self": {"DNSName": "factory-pc.tail1a2b3.ts.net."}}))
    elif sys.argv[1] in ("funnel", "serve"):
        # كأداة Tailscale الحقيقية: تكتب رابط التفعيل ثم تنتظر حتى يُفعَّل من الصفحة فتكمل وحدها
        open(os.path.join(W, "ts_funnel_pid"), "w").write(str(os.getpid()))

        def now():
            return open(os.path.join(W, "ts_mode")).read().strip()
        if mode == "https":
            print("HTTPS is not enabled on your tailnet.\\nTo enable, visit:\\n\\n  https://login.tailscale.com/f/serve?node=n1\\n",
                  flush=True)
            while now() == "https":
                time.sleep(0.1)
            print("Success.", flush=True)
        if now() == "enable":
            print("Funnel is not enabled on your tailnet.\\nTo enable, visit:\\n\\n  https://login.tailscale.com/f/funnel?node=n1\\n",
                  flush=True)
            while now() == "enable":
                time.sleep(0.1)
            print("Success.", flush=True)
        print("Available on the internet:\\n\\nhttps://factory-pc.tail1a2b3.ts.net/\\n|-- proxy http://127.0.0.1:47815")
""")
assert ns["find_tailscale"]() == ts, "Tailscale من PATH"
code, out = ns["live_run_capture"]([sys.executable, "-c", "import time; print('partial', flush=True); time.sleep(20)"], timeout=1)
assert code is None and "partial" in out, "المهلة: تُوقف الأداة ويُقرأ ما كتبته"
TS = ns["LiveTailscale"]
TS.BACKOFF = (0.2, 0.2)


def wait_for(cond, secs=15):
    end = time.time() + secs
    while not cond() and time.time() < end:
        time.sleep(0.05)
    return cond()


open(mode_file, "w").write("login")
r = TS(ts, 47815).start()
assert wait_for(lambda: r.state == "login"), r.state
assert r.action_url == "https://login.tailscale.com/a/abc123" and r.url is None, "تسجيل الدخول: رابطه يظهر"
r.stop()
open(mode_file, "w").write("https")
open(os.path.join(work, "ts_calls"), "w").close()
r = TS(ts, 47815)
r.CHECK_EVERY, r.CONFIGURE_TIMEOUT = 0.2, 1.5
r.start()
t0 = time.time()
assert wait_for(lambda: r.state == "enable", 20), (r.state, r.error)
assert time.time() - t0 < 5, "1.96.2: رابط التفعيل يظهر فوراً (لا بعد مهلة الأمر)"
assert r.action_url == "https://login.tailscale.com/f/serve?node=n1" and "HTTPS" in r.error and "ثم Funnel" in r.error, \
    "الصفحة الأولى: HTTPS ثم Funnel"
assert r.host == "https://factory-pc.tail1a2b3.ts.net" and r.url is None, "العنوان يُعرف قبل جاهزية Funnel، والرابط لا"
time.sleep(2.5)                                    # أطول من مهلة الأمر: ما دام رابط التفعيل ظاهراً لا يُوقف
assert r.state == "enable", r.state
open(mode_file, "w").write("enable")
assert wait_for(lambda: r.action_url == "https://login.tailscale.com/f/funnel?node=n1", 10), r.action_url
assert "Funnel" in r.error and "HTTPS" not in r.error, "الصفحة الثانية: Funnel"
open(mode_file, "w").write("ok")
assert wait_for(lambda: r.state == "ready", 10), (r.state, r.error)
assert r.url == "https://factory-pc.tail1a2b3.ts.net" and r.command()[1:] == ["funnel", "--bg", "47815"]
assert open(os.path.join(work, "ts_calls")).read().count("funnel --bg 47815") == 1, \
    "بعد Enable يكمل الأمر نفسه وحده — بلا إعادة"
r.stop()
open(mode_file, "w").write("enable")
r = TS(ts, 47815)
r.CHECK_EVERY = 0.2
r.start()
assert wait_for(lambda: r.state == "enable", 20)
r.stop()
funnel_pid = int(open(os.path.join(work, "ts_funnel_pid")).read())


def gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


assert wait_for(lambda: gone(funnel_pid), 10), "الإيقاف يُنهي الأمر المنتظر"
assert r.state == "stopped"
open(mode_file, "w").write("ok")
assert TS(ts, 47815, private=True).command()[1:] == ["serve", "--bg", "47815"], "لأجهزتي فقط: Serve"
calls = open(os.path.join(work, "ts_calls")).read()
assert "funnel --bg 47815" in calls and "status --json" in calls

cf = fake_tool("cloudflared", """
    n_file = os.path.join(W, "cf_runs")
    n = int(open(n_file).read()) + 1 if os.path.exists(n_file) else 1
    open(n_file, "w").write(str(n))
    open(os.path.join(W, "cf_seen"), "w").write(json.dumps({"argv": sys.argv[1:], "token": os.environ.get("TUNNEL_TOKEN")}))
    sys.stderr.write("INF Starting tunnel tunnelID=x\\n")
    sys.stderr.write("INF Registered tunnel connection connIndex=0 location=fra01\\n"); sys.stderr.flush()
    time.sleep(0.6 if n == 1 else 30)
""")
assert ns["find_cloudflared"]() == cf
CF = ns["LiveCloudflare"]
CF.BACKOFF = (0.3, 0.3)
secret = "fake-tunnel-token-for-tests-" + "x" * 40
r = CF(cf, 47815, "Live.Example.com", secret).start()
assert wait_for(lambda: r.state == "ready"), (r.state, r.error)
assert r.url == "https://live.example.com"
seen_cf = json.loads(open(os.path.join(work, "cf_seen")).read())
assert seen_cf["argv"] == ["tunnel", "--no-autoupdate", "run"] and seen_cf["token"] == secret, "الرمز في البيئة لا في الأوامر"
assert wait_for(lambda: open(os.path.join(work, "cf_runs")).read() == "2" and r.state == "ready"), "توقّف ← يُعاد تشغيله"
proc = r.proc
r.stop()
assert r.url is None and r.state == "stopped" and proc.poll() is not None, "الإيقاف ينهي الأداة"
os.environ["PATH"] = old_path
print("✔ الرابط الثابت: Tailscale ← https://اسم-الجهاز.شبكتك.ts.net (Funnel، أو Serve لأجهزتك)، وتسجيل الدخول وتفعيل "
      "Funnel يظهر رابطهما؛ وCloudflare ← https://نطاقك والرمز في البيئة لا في الأوامر، ويُعاد تشغيله إن توقف")

# ═══ ٤) الظل: دوال الشاشة الحقيقية بلا لمس الشاشة ولا البيانات ═══
root = tk.Tk()
root.withdraw()
exec(textwrap.dedent('''
class FakeApp:
    COLS = ("الاسم", "الوزن")
    def refresh_x(self):
        self.lbl_total.configure(text=f"الإجمالي: {sum(i['w'] for i in self.invoices.values()):.2f}")
        tree = self.make_tree(self.table_frame)
        for i in self.invoices.values():
            tree.insert("", "end", values=(i["n"], f"{i['w']:.2f}"))
        tree.insert("", "end", values=("الإجمالي", "9.00"), tags=("total_tag",))
        tree._total_tree = ttk.Treeview(self.table_frame, columns=self.COLS, show="headings")
        tree._total_tree.insert("", "end", values=("الإجمالي", "9.00"), tags=("total_tag",))
        self.prebuilt.insert("", "end", values=("مسجّل", "1"))
        self.combo_seen = self.combo.get()
        self.on_done()
        self.set_setting("x", "1")
        self.marks.add("dirty")
        return self.period
    def make_tree(self, parent):
        t = ttk.Treeview(parent, columns=self.COLS, show="headings")
        for c in self.COLS:
            t.heading(c, text=c)
        return t
    def set_setting(self, k, v):
        raise AssertionError("كتابة!")
'''), ns)
app = ns["FakeApp"]()
real_frame = ctk.CTkFrame(root)
real_label = ctk.CTkLabel(root, text="كما هو")
real_tree = ttk.Treeview(root, columns=("أ", "ب"), show="headings")
real_tree.heading("أ", text="العمود أ")
real_tree.insert("", "end", values=("x", "y"))
real_combo = ctk.CTkComboBox(root, values=["سالم"])
real_combo.set("سالم")
called = []
app.__dict__.update(invoices={1: {"n": "أحمد", "w": 4.0}, 2: {"n": "خالد", "w": 5.0}}, table_frame=real_frame,
                    lbl_total=real_label, prebuilt=real_tree, combo=real_combo, on_done=lambda: called.append(1),
                    marks={"clean"}, period="2026-10", scroll=ctk.CTkScrollbar(root),
                    nested={"stage": {"table_frame": real_frame, "totals_lbl": real_label, "n": 3}})
host = tk.Frame(root)
sh = ns["_LiveShadow"](app, host, period="2026-09")
assert sh.refresh_x() == "2026-09", "دوال البرنامج مربوطة بالظل وفترته"
assert sh.invoices is app.invoices, "الحركات بالمرجع (بلا نسخ)"
assert isinstance(sh.table_frame, tk.Frame) and sh.table_frame is not real_frame and sh.table_frame.master is host
assert not real_frame.winfo_children(), "لا جدول في إطار الشاشة الحقيقي"
assert real_label.cget("text") == "كما هو" and sh.lbl_total.text() == "الإجمالي: 9.00", "العنوان الحقيقي كما هو"
assert real_tree.get_children() and len(real_tree.get_children()) == 1, "الجدول الحقيقي كما هو"
assert isinstance(sh.prebuilt, ttk.Treeview) and sh.prebuilt is not real_tree and sh.prebuilt.heading("أ")["text"] == "العمود أ"
assert sh.combo_seen == "سالم", "الأدوات تُقرأ (الاختيار الحالي)"
assert called == [] and app.marks == {"clean"} and sh.marks == {"clean", "dirty"}, "ردود الشاشة لا تعمل، والمجموعات نسخ"
assert isinstance(sh.scroll, ns["_LiveSink"]), "الشريط (CTkScrollbar يرث Frame) بديلٌ لا إطار"
assert isinstance(sh.nested["stage"]["table_frame"], tk.Frame) and isinstance(sh.nested["stage"]["totals_lbl"], ns["_LiveSink"])
assert app.nested["stage"]["table_frame"] is real_frame
tables = ns["live_tree_tables"](host)
assert tables[0] == {"heads": ["الاسم", "الوزن"], "rows": [(["أحمد", "4.00"], False), (["خالد", "5.00"], False),
                                                          (["الإجمالي", "9.00"], True)]}, tables[0]
assert tables[1]["rows"] == [(["مسجّل", "1"], False)]
assert ns["live_shadow_labels"](sh) == ["الإجمالي: 9.00"]
try:
    ns["_LiveShadow"](app, host).missing_attr
    raise SystemExit("✘ سمة مفقودة")
except AttributeError:
    pass
shadow_src = module_src("_LiveShadow")
for w in ('"set_setting"', '"save_invoice_to_db"', '"mark_backup_dirty"', '"push_undo"', '"recalculate_all"',
          '"save_name_to_db"', '"toast"', '"navigate_to_screen"'):
    assert w in shadow_src, w
print("✔ الظل (للقراءة): دوال الشاشة نفسها بفترةٍ أخرى — الحركات بالمرجع، والإطارات خفية، والجداول نسخٌ بأعمدتها، "
      "والأدوات تُقرأ ولا تُكتب، وردود الشاشة ودوال الكتابة لا تعمل")

# ═══ ٥) الكاتب (للإضافة): دالة الترحيل الحقيقية بقيم النموذج، والكتابة في البرنامج نفسه ═══
E = ns["_LiveEntry"]("12")
E.insert("end", ".5")
assert E.get() == "12.5"
E.delete(0, "end")
E.insert(0, "7")
assert E.get() == "7"
E.set("abc")
E.delete(1)
assert E.get() == "ac" and E.focus_set() is not None, "خانة النموذج: get/insert/delete/set، وما سواها لا يعمل"
exec(textwrap.dedent('''
class WApp:
    def submit(self):
        name = self.combo.get()
        if not self.check_edit_permission():
            return "locked"
        if not messagebox.askyesno("تأكيد الترحيل", f"ترحيل {name}؟"):
            return "no"
        messagebox.showinfo("نجاح", "تم")
        if messagebox.askyesno("طباعة", "هل تريد الطباعة؟"):
            self.print_voucher()
        if messagebox.askyesno("رقم مكرر", "متابعة؟"):
            self.dups += 1
        self.counter += 1
        self.invoices[self.counter] = {"n": name, "p": self.period}
        self.entry.delete(0, "end")
        self.discard_draft("x")
        self.refresh_table()
        self.status_text = "✔"
        return self.counter
    def check_edit_permission(self, silent=False):
        return False
    def print_voucher(self):
        raise AssertionError("طباعة!")
    def discard_draft(self, k):
        raise AssertionError("مسودة الجهاز!")
    def refresh_table(self):
        self.refreshed.append(type(self).__name__)
'''), ns)
wa = ns["WApp"]()
wa.__dict__.update(combo=real_combo, counter=10, invoices={}, period="2026-11", dups=0, refreshed=[], entry=real_combo)
asked_before = messagebox.askyesno
W = ns["_LiveWriter"](wa, combo=ns["_LiveEntry"]("أحمد"), entry=ns["_LiveEntry"]("x"), period="2026-09")
with ns["_LiveDialogs"]() as dlg:
    assert W.submit() == 11
assert wa.invoices == {11: {"n": "أحمد", "p": "2026-09"}} and wa.counter == 11, "الحركة في البرنامج نفسه بقيم النموذج وفترته"
assert real_combo.get() == "سالم" and wa.refreshed == ["WApp"], "خانة الجهاز كما هي، وشاشته حُدِّثت (بالبرنامج نفسه)"
assert wa.status_text == "✔" and wa.dups == 0 and wa.period == "2026-11", "ما يخص العملية في النسخة، والباقي في البرنامج"
assert [k for k, _t in dlg.lines] == ["yes", "info", "no", "no"] and not dlg.blocked, dlg.lines
assert messagebox.askyesno is asked_before, "نوافذ الجهاز تعود كما كانت"
with ns["_LiveDialogs"](force=True) as dlg:
    assert W.submit() == 12
assert wa.dups == 1 and [k for k, _t in dlg.lines] == ["yes", "info", "no", "yes"], "«متابعة رغم التنبيهات»: نعم إلا الطباعة"
with ns["_LiveDialogs"]() as dlg:
    messagebox.showwarning("تنبيه", "x")
    assert messagebox.askquestion("تأكيد", "?") == "yes" and messagebox.askquestion("سؤال", "?") == "no"
assert dlg.blocked
writer_src = module_src("_LiveWriter")
for w in ('"is_edit_locked": lambda: False', '"check_edit_permission": lambda silent=False: True', '"discard_draft"',
          '"remember_discount_pct"', '"print_"', '"refresh_"', '"recalculate"',
          'WRITE = frozenset({"update_set_move", "update_inbound_move", "update_journal_entry"})'):
    assert w in writer_src, w
print("✔ الكاتب: دالة الترحيل الحقيقية بقيم النموذج وفترة الصفحة، والحركة في البرنامج نفسه، وشاشة الجهاز تُحدَّث وخاناته "
      "كما هي؛ «تأكيد…» نعم وغيره لا (إلا مع «متابعة»)، والطباعة ومسودة الجهاز لا تُمسّان، والنوافذ تعود كما كانت")
root.destroy()

# ═══ ٦) البرنامج: الصفحات والأدوات والتحكم — بلا سحابة ═══
page = member("live_page")
assert "self.ensure_screen_built(screen, background=True)" in page and "p if p in periods else self.current_display_month" in page
assert set(re.findall(r'\("(\w+)", "[^"]+", "[^"]+"\)', member("LIVE_SCREENS"))) == {
    "stages", "khayas", "sales", "inbound", "factory", "losses"}
assert set(re.findall(r'\("(\w+)", "[^"]+", "[^"]+"\)', member("LIVE_TOOLS"))) == {"add", "recent", "set", "bin", "control"}
respond = member("live_respond")
assert 'if method == "POST":' in respond and "self.live_post(params)" in respond and "self.live_backup()" in respond
post = member("live_post")
assert "nonce in nonces" in post and '"status": 303' in post and "self.live_url(back, m=mid)" in post
forms = member("live_forms")
for key in ('"mfg"', '"asm"', '"cast"', '"polish"', '"pbuff"', '"g:{s}"', '"inbound"', '"journal"', '"sale"'):
    assert key in forms, key
form = member("live_form")
for fn in ('"submit_unified_op"', '"submit_casting_op"', '"submit_polish_op"', '"submit_polish_buff_op"',
           '"live_generic_post"', '"submit_inbound"', '"submit_journal_entry"', '"live_sale_post"'):
    assert fn in form, fn
assert "self.stage_sale_row()" in member("live_sale_post") and "self.commit_sale_invoice()" in member("live_sale_post")
assert '"update_set_move"' in member("live_do_move") and '"delete_set_move"' in member("live_do_move")
assert 'params.get("c") != "1"' in member("live_do_move") and 'params.get("c") != "1"' in member("live_do_control")
assert "self.unified_op_fields(" in member("render_unified_fields"), "خانات الشاشة والرابط من مصدرٍ واحد"
html = member("live_html")
assert html.count("esc(") >= 15 and 'onchange="this.form.submit()"' in html
assert ns["live_escape"]('"><script>x</script>') == "&quot;&gt;&lt;script&gt;x&lt;/script&gt;"
fh = member("live_form_html")
assert 'method="post"' in fh and "n=new_live_token()" in fh and fh.count("esc(") >= 10
tick = member("_live_tick")
assert "box.update(self.live_respond(params, box.get(\"method\", \"GET\")))" in tick and "box[\"event\"].set()" in tick
start = member("start_live_view")
assert "server.start(LIVE_PORT)" in start and 'if getattr(self, "view_only", False):' in start
assert "self.live_start_relay()" in start and "save_ui_pref(LIVE_ENABLED_PREF, True)" in start
relay = member("live_start_relay")
assert "LiveTailscale(" in relay and "LiveCloudflare(" in relay and "LIVE_CF_TOKEN_PREF" in relay
stop = member("stop_live_view")
assert "if user and self.live_pinned():" in stop and "save_ui_pref(LIVE_ENABLED_PREF, False)" in stop
assert "if self.live_pinned() or self.live_admin_mode():" in member("renew_live_token")
assert "self.stop_live_view(user=False)" in member("on_app_closing")
assert "self.after(3000, self.start_live_view)" in src and "if self.live_enabled_pref()" in src
assert "or self.live_pinned()" in member("live_enabled_pref"), "المثبّت يعود مع البرنامج"
assert "save_ui_pref(LIVE_TOKEN_PREF, token)" in member("live_token"), "المفتاح في تفضيلات الجهاز — لا قاعدة البيانات ولا السحابة"
# تحكم المدير من رابطه: في قاعدة بيانات الجهاز، ويُطبَّق فوراً، ويبقى بعد إعادة التشغيل
flags = member("REMOTE_FLAGS")
assert '"remote_edit_locked"' in flags and '"remote_suspended"' in flags and '"remote_link_pinned"' in flags
setf = member("set_remote_flag")
assert "INSERT OR REPLACE INTO settings" in setf and "self.after(50, self.apply_remote_flags)" in setf
assert 'self.show_access_lock("remote_suspended")' in member("apply_remote_flags")
assert 'self.remote_flag("edit_locked")' in member("is_edit_locked")
assert 'if self.remote_flag("suspended"):' in member("hide_access_lock") and "quiet" in member("hide_access_lock")
assert 'if self.remote_flag("suspended"):' in member("check_access_now")
assert '"remote_suspended"' in member("ACCESS_LOCK_TEXT")
assert 'self.after(400, self.apply_remote_flags)' in src
for gone in ("cloud_publish_live_link", "cloud_get_live_link", 'table("live_links")', "client_publish_live_link", "trycloudflare",
             "LiveTunnel", "_live_publish_async"):
    assert gone not in src, gone
if "class AdminPanel" in src:
    admin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AdminPanel")
    open_live = next(m for m in admin.body if isinstance(m, ast.FunctionDef) and m.name == "open_client_live_dialog")
    body = ast.get_source_segment(src, open_live)
    assert "self.client_live_key(client_id, renew=renew)" in body and "live_link(addr, key)" in body
    assert "cloud_admin_set_live_key(client_id, live_key_hash(key))" in body and "tk_background(win, work, done)" in body
    assert "cloud_admin_live_devices(client_id)" in body and "live_probe(link, timeout=15)" in body
    assert "self.client_live_manual_address(client_id)" in body, "1.96.1: العنوان من موقع Tailscale يدوياً"
    # 1.96.1: فحص المدير خطوةً خطوة (دالة نقية) والعنوان اليدوي
    pure = {"re": re, "LIVE_HOST_RE": ns["LIVE_HOST_RE"], "_TS_ACTION_RE": ns["_TS_ACTION_RE"]}
    exec(module_src("version_tuple"), pure)
    for fn in ("live_admin_checks", "normalize_live_address"):
        node = next(m for m in admin.body if isinstance(m, ast.FunctionDef) and m.name == fn)
        exec(textwrap.dedent(ast.get_source_segment(src, node)).replace("@staticmethod\n", ""), pure)
    norm = pure["normalize_live_address"]
    assert norm("  Factory-PC.tail1a2b3.ts.net/ ") == norm("https://factory-pc.tail1a2b3.ts.net/x?y") == \
        "https://factory-pc.tail1a2b3.ts.net" and norm("not an address") is None and norm("") is None
    chk = pure["live_admin_checks"]
    dev = lambda **kw: dict({"device_name": "جهاز", "app_version": "1.96.1", "last_seen": "2026-11-12T09:00",
                             "live_url": None, "live_state": None}, **kw)
    r = chk(False, "LIVE_SQL", None, None, None, None)
    assert [x[0] for x in r] == [False] and "LIVE_SQL" in r[0][2], "المفتاح لم يُحفظ ← يتوقف أولاً"
    r = chk(True, None, [], None, None, None)
    assert r[-1][0] is False and "لم يدخل أي جهاز" in r[-1][2]
    r = chk(True, None, [dev(app_version="1.95.0")], None, None, None)
    assert r[1][0] is False and "حدّث برنامج المصنع" in r[1][2], "إصدارٌ قديم على جهاز المصنع"
    r = chk(True, None, [dev()], None, None, None)
    assert r[-1][0] is False and "موقع Tailscale" in r[-1][2] and r[2][0] is None, "بلا عنوان ولا حال: يُطلب العنوان"
    url = "https://factory-pc.tail1a2b3.ts.net"
    r = chk(True, None, [dev(live_url=url, live_state="✘ لم يكتمل · بانتظار تفعيل Funnel")], None, url + "/?k=x", (404, True, ""))
    assert r[2][0] is False and "بانتظار تفعيل Funnel" in r[2][2] and r[-1][0] is False and "لم يأخذ المفتاح" in r[-1][2]
    r = chk(True, None, [dev(live_state="✔ جاهز")], url, url + "/?k=x", (200, True, ""))
    assert all(x[0] for x in r) and "مكتوب هنا من موقع Tailscale" in r[3][2], "العنوان اليدوي يكفي، والرابط يفتح"
    r = chk(True, None, [dev(live_url=url, live_state="✔ جاهز")], None, url + "/?k=x", (None, False, "timed out"))
    assert r[-1][0] is False and "لا يصل" in r[-1][2]
    # 1.96.2: رابط التفعيل يصل في حال الجهاز ← المدير يفعّل Funnel من جهازه
    st = "✘ لم يكتمل · بانتظار تفعيل Funnel في Tailscale · رابط التفعيل: https://login.tailscale.com/f/funnel?node=n1 · الإصدار 1.96.2"
    r = chk(True, None, [dev(live_state=st)], None, None, None)
    assert r[2][0] is False and "«🔓 فعّل من جهازي»" in r[2][2] and "Enable" in r[2][2], "فحص المدير يدلّه على التفعيل من جهازه"
    r = chk(True, None, [dev(live_state="✘ لم يكتمل · بانتظار مفتاح المدير")], None, None, None)
    assert "فعّل من جهازي" not in r[2][2], "بلا رابط تفعيل: لا زر"
    r = chk(True, None, [dev(live_state="✔ جاهز · ⚠️ نام الجهاز 14:02–14:40")], url, url + "/?k=x", (None, False, "timed out"))
    assert "«💤 امنع النوم»" in r[2][2] and "نائم" in r[-1][2], "المدير يعرف أن جهاز المصنع ينام وما يُصلحه"
    assert 'state["enable_url"] = urls[0] if urls and bad is not None else None' in body and "enable_btn.pack(" in body
    assert "open_url_window(state[\"enable_url\"])" in body
    assert 'text="🌐 العرض المباشر"' in src
# 1.96: رابط المدير في برنامج المدير وحده — الجهاز يأخذ البصمة ويرسل عنوانه، ولا يعرض رابطاً
assert "server = LiveViewServer(None, pending, verifier=self.live_stored_hash() or None)" in start
assert 'save_ui_pref(LIVE_TOKEN_PREF, None)' in start, "مفتاح 1.95 على جهاز العميل يُمسح"
sync = member("live_sync_async")
assert "tk_background(self, lambda: cloud_live_sync(client_id, url or \"\", summary), done)" in sync
assert "self.live_sync_async(state[\"url\"])" in member("_live_tick")
dlg = member("open_live_view_dialog")
assert "if admin_mode:" in dlg and "admin_note.pack(" in dlg and "if not admin_mode:" in dlg
assert '"p_url": url or ""' in module_src("cloud_live_sync") and '"client_live_sync"' in module_src("cloud_live_sync")
assert 'p_state=str(state or "")[:300]' in module_src("cloud_live_sync") and '"ok_nostate"' in module_src("cloud_live_sync"), \
    "1.96.1: حال الرابط تُرسل للمدير — و24 القديم (بلا حال) يعمل"
check = member("live_check_compute")
# 1.96.2: Funnel — رابط التفعيل فوراً، والأمر ينتظر Enable فيكمل وحده؛ والفحص ينتظر الوسيط ويتابع التفعيل وحده
cfg = module_src("LiveTailscale")
assert "code, out = self._configure()" in cfg and "limit = self.ENABLE_WAIT if asked else self.CONFIGURE_TIMEOUT" in cfg
assert "live_run_capture(self.command()" not in cfg, "لا انتظارٌ أعمى للمهلة قبل قراءة رابط التفعيل"
assert 'while relay.state == "starting" and time.monotonic() < end' in check, "الفحص لا يعدّ «يجهّز» فشلاً"
assert '"Tailscale ما زال يجهّز الرابط' in check and "Enable" in check
olc = member("open_live_check")
assert "self.live_check_compute(snap, provider, exe, relay)" in olc
assert 'state["follow_until"] = time.time() + self.LIVE_FOLLOW_SECS' in olc and "win.after(self.LIVE_FOLLOW_MS, run)" in olc
assert "win.after_cancel(state[\"follow_job\"])" in olc, "متابعةٌ واحدة لا تتكرر"
assert "📋 نسخ رابط التفعيل" in olc and 'if text != state["sent_text"]:' in olc
# 1.96.3: لابتوب المصنع لا ينام عند إغلاق الغطاء (إعدادات الطاقة عند توصيل الشاحن) — والنوم يُكشف ويُبلَّغ
import types
PW = {"LIDACTION": 1, "STANDBYIDLE": 1800, "HIBERNATEIDLE": 10800}
PW_CALLS = []


def fake_powercfg(cmd, timeout=30, env=None):
    PW_CALLS.append(cmd)
    if cmd[1] == "/q":
        key = cmd[4]
        extra = ("" if key == "LIDACTION" else
                 "      الحد الأدنى: 0x00000000\n      الحد الأقصى: 0xffffffff\n      الزيادة: 0x00000001\n")
        return 0, (f"معرّف GUID لنظام الطاقة: 381b4222-f694-41f0-9685-ff5bb260df2e  (متوازن)\n  {cmd[3]}\n    {key}\n"
                   f"      Possible Setting Index: 000\n{extra}"
                   f"    Current AC Power Setting Index: 0x{PW[key]:08x}\n    Current DC Power Setting Index: 0x{PW[key] + 7:08x}\n")
    if cmd[1] == "/setacvalueindex":
        PW[cmd[4]] = int(cmd[5])
    return 0, ""


pw = {"re": re, "time": time, "sys": types.SimpleNamespace(platform="win32"), "live_run_capture": fake_powercfg}
for fn in ("_PWR_SETTINGS", "_PWR_HEX_RE", "live_power_read", "live_power_ok", "live_power_fix", "live_on_battery",
           "live_keep_awake"):
    exec(module_src(fn), pw)
vals = pw["live_power_read"]()
assert vals == {"LIDACTION": 1, "STANDBYIDLE": 1800, "HIBERNATEIDLE": 10800}, f"قيمة الشاحن (لا البطارية) بأي لغة: {vals}"
assert not pw["live_power_ok"](vals) and not pw["live_power_ok"](None)
assert pw["live_power_fix"](wait=1) == (True, "") and pw["live_power_ok"](pw["live_power_read"]()), "الضبط بلا إذن"
sets = [c for c in PW_CALLS if c[1] == "/setacvalueindex"]
assert {(c[3], c[4], c[5]) for c in sets} == {("SUB_BUTTONS", "LIDACTION", "0"), ("SUB_SLEEP", "STANDBYIDLE", "0"),
                                             ("SUB_SLEEP", "HIBERNATEIDLE", "0")}, "الغطاء «لا شيء» والنوم والإسبات «أبداً»"
assert ["powercfg", "/setactive", "SCHEME_CURRENT"] in PW_CALLS and not any("/setdcvalueindex" in c for c in PW_CALLS), \
    "عند توصيل الشاحن وحده — البطارية كما هي"
PW.update(LIDACTION=1)
pw["live_run_capture"] = lambda cmd, timeout=30, env=None: (fake_powercfg(cmd) if cmd[1] == "/q" else (1, "Access denied"))
done_, why = pw["live_power_fix"](wait=1)
assert done_ is False and why, "رُفض بلا صلاحية ولا إذن ويندوز (UAC): فشلٌ بسببه لا انهيار"
assert pw["live_on_battery"]() is None and pw["live_keep_awake"](True) is False, "خارج ويندوز الحقيقي: لا شيء"
linux_pw = {"sys": sys, "re": re, "_PWR_SETTINGS": pw["_PWR_SETTINGS"]}
exec(module_src("live_power_read"), linux_pw)
assert sys.platform.startswith("win") or linux_pw["live_power_read"]() is None, "غير ويندوز: لا خطوة طاقة"
start2 = member("start_live_view")
assert "live_keep_awake(True)" in start2 and '"tick_at": time.time()' in start2, "الرابط يعمل ← لا نوم من الخمول"
assert "live_keep_awake(False)" in member("stop_live_view")
tick2 = member("_live_tick")
assert "if now - last > self.LIVE_SLEEP_GAP:" in tick2 and 'live["slept"] = (last, now)' in tick2 \
    and "self.live_start_relay()" in tick2, "بعد الاستيقاظ: الوسيط يُعاد ويُبلَّغ المدير"
assert "self.live_check_power(add, snap)" in check and '"power")' in member("live_check_power")
assert "tk_background(win, live_power_fix, powered)" in member("open_live_check")
assert '"⚠️ الجهاز ينام عند إغلاق الغطاء"' in member("live_state_summary") and "نام الجهاز" in member("live_state_summary")
summ2 = member("live_state_summary")
assert 'parts.append(f"رابط التفعيل: {st[\'action_url\']}")' in summ2 and 'f"حساب Tailscale: {st[\'account\']}"' in summ2
for t in ('"Tailscale مثبّت"', '"تسجيل الدخول في Tailscale"', '"Funnel (فتح الرابط للإنترنت)"', '"عنوان هذا الجهاز"',
          '"إرسال العنوان للمدير"', '"مفتاح المدير"', '"يصل من الإنترنت"'):
    assert t in check, t
assert set(re.findall(r'"(\w+)": "', member("LIVE_CHECK_ACTIONS"))) == {"start", "install", "login", "enable", "relay", "sync",
                                                                        "power"}
summ = member("live_state_summary")
assert '"✔ جاهز" if ready else "✘ لم يكتمل"' in summ and "[:300]" in summ
assert "self.live_report_state(" in member("stop_live_view") and "self.live_report_state(" in member("on_app_closing")
assert "self.open_live_check(win)" in member("open_live_view_dialog")
assert "connect-src 'self'" in module_src("LiveViewServer"), "الملء التلقائي يسأل الجهاز نفسه فقط"
fill = member("live_fill")
assert "self.find_row_by_set_number(cat, set_no, month=month)" in fill and "self.sb_sale_fill(set_no)" in fill
assert "self.row_set_numbers(name, row, month=month)" in fill and "get_assembler_khayas_details" in fill
assert "data-fill" in member("live_form_html") and "fetch(" in member("LIVE_FILL_JS")
assert '"any_del": self.live_do_any_delete' in post and '"bin_restore": self.live_do_bin_restore' in post
anyd = member("live_delete_any")
assert "get_sale_invoice_records(self.sale_key_of(inv))" in anyd and "self.journal_legs(inv)" in anyd
for mod_name in ("http.server", "socketserver", "secrets", "hmac", "queue"):
    assert not re.search(rf"^\s*import {re.escape(mod_name)}\b", src, re.M), f"{mod_name}: قد لا يحمله exe الحالي"
print("✔ البرنامج: الشاشات الست وأدوات الإضافة (كل المراحل والوارد والقيود والمبيعات) والبحث والتعديل والتحكم؛ وتحكم "
      "المدير في قاعدة بيانات الجهاز ويبقى بعد إعادة التشغيل؛ والمنفذ ثابت والرابط لا يُوقف من الجهاز ما دام مثبّتاً؛ "
      "ولا شيء من الرابط في السحابة — بلا مكتبةٍ جديدة على exe")

print("✔ 1.96: الرابط في برنامج المدير وحده (الجهاز يتحقق ببصمة المفتاح ويرسل عنوانه)، والملء التلقائي، وآخر العمليات "
      "وحذف أي عملية (الفاتورة كاملة والقيد بطرفيه)، والمحذوفات في الرابط")
print("\n✅ 1.95–1.96: الرابط المباشر الثابت — عرضٌ وإضافة وتعديل ولوحة تحكم، ويظهر في برنامج المدير وحده")
