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
import ast, base64, io, json, os, re, shutil, stat, subprocess, sys, tempfile, textwrap, threading, time

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
      "json": json, "shutil": shutil, "subprocess": subprocess, "tk": tk, "ttk": ttk, "ctk": ctk,
      "messagebox": messagebox, "log_cloud_error": lambda *a: logged.append(a), "find_edge_exe": lambda: None}
for name in ("LIVE_PORT", "LIVE_PROVIDERS", "CLOUDFLARED_CANDIDATES", "TAILSCALE_CANDIDATES", "_WINGET_FLAGS",
             "LIVE_WINGET", "LIVE_LINK_RE", "LIVE_HOST_RE", "_TS_ACTION_RE", "_find_tool", "find_cloudflared",
             "find_tailscale", "live_run_capture", "live_link", "LiveViewServer", "LiveRelay", "LiveTailscale",
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
        if mode == "enable":
            print("Funnel is not enabled on your tailnet.\\nTo enable, visit:\\n\\n  https://login.tailscale.com/f/funnel?node=n1\\n")
            sys.stdout.flush(); time.sleep(120)
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
open(mode_file, "w").write("enable")
r = TS(ts, 47815)
r.CHECK_EVERY, r.CONFIGURE_TIMEOUT = 0.2, 1.5
r.start()
assert wait_for(lambda: r.state == "enable", 20), (r.state, r.error)
assert r.action_url == "https://login.tailscale.com/f/funnel?node=n1" and "Funnel" in r.error, "تفعيل Funnel: رابطه يظهر"
open(mode_file, "w").write("ok")
assert wait_for(lambda: r.state == "ready", 30), (r.state, r.error)
assert r.url == "https://factory-pc.tail1a2b3.ts.net" and r.command()[1:] == ["funnel", "--bg", "47815"]
r.stop()
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
          '"remember_discount_pct"', '"print_"', '"refresh_"', '"recalculate"', 'WRITE = frozenset({"update_set_move"})'):
    assert w in writer_src, w
print("✔ الكاتب: دالة الترحيل الحقيقية بقيم النموذج وفترة الصفحة، والحركة في البرنامج نفسه، وشاشة الجهاز تُحدَّث وخاناته "
      "كما هي؛ «تأكيد…» نعم وغيره لا (إلا مع «متابعة»)، والطباعة ومسودة الجهاز لا تُمسّان، والنوافذ تعود كما كانت")
root.destroy()

# ═══ ٦) البرنامج: الصفحات والأدوات والتحكم — بلا سحابة ═══
page = member("live_page")
assert "self.ensure_screen_built(screen, background=True)" in page and "p if p in periods else self.current_display_month" in page
assert set(re.findall(r'\("(\w+)", "[^"]+", "[^"]+"\)', member("LIVE_SCREENS"))) == {
    "stages", "khayas", "sales", "inbound", "factory", "losses"}
assert set(re.findall(r'\("(\w+)", "[^"]+", "[^"]+"\)', member("LIVE_TOOLS"))) == {"add", "set", "control"}
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
assert "if self.live_pinned():" in member("renew_live_token")
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
    open_live = next(m for m in admin.body if isinstance(m, ast.FunctionDef) and m.name == "open_client_live_view")
    body = ast.get_source_segment(src, open_live)
    assert "self.client_live_link(client_id)" in body and "open_url_window(url)" in body
    assert 'text="🌐 العرض المباشر"' in src and "LIVE_LINK_RE.match(url)" in src
for mod_name in ("http.server", "socketserver", "secrets", "hmac", "queue"):
    assert not re.search(rf"^\s*import {re.escape(mod_name)}\b", src, re.M), f"{mod_name}: قد لا يحمله exe الحالي"
print("✔ البرنامج: الشاشات الست وأدوات الإضافة (كل المراحل والوارد والقيود والمبيعات) والبحث والتعديل والتحكم؛ وتحكم "
      "المدير في قاعدة بيانات الجهاز ويبقى بعد إعادة التشغيل؛ والمنفذ ثابت والرابط لا يُوقف من الجهاز ما دام مثبّتاً؛ "
      "ولا شيء من الرابط في السحابة — بلا مكتبةٍ جديدة على exe")

print("\n✅ 1.95: الرابط المباشر الثابت — عرضٌ وإضافة وتعديل ولوحة تحكم، بلا سحابة")
