# -*- coding: utf-8 -*-
"""1.94: «العرض المباشر» — رابط المدير الخاص إلى جهاز المصنع (للقراءة فقط):
  • الخادم: 127.0.0.1 وحده، GET/HEAD وحدهما، المفتاح السري بمقارنة ثابتة الزمن والخاطئ 404 بعد تأخير، ورؤوس أمان
    (لا تخزين ولا فهرسة ولا إطار ولا مُحيل)، والطلب يُجاب من خيط الواجهة عبر طابور.
  • النفق: رابط trycloudflare من مخرجات cloudflared، ويُعاد تشغيله إن توقف، ويُوقف مع البرنامج.
  • الظل: دوال الشاشات الحقيقية على نسخةٍ ظلّية — البيانات بالمرجع، والإطارات خفية، والجداول نسخٌ بأعمدتها، والأدوات
    بدائل تقرأ ولا تكتب، وردود الشاشة ودوال الكتابة لا تعمل.
  • الصفحة: الشاشات الست بالفترة، والصف المكرر للإجمالي مرة واحدة، والمدخلات مُهرَّبة.
  • الربط: زر «🌐 مباشر» ونافذته، والتشغيل يعود مع البرنامج ويتوقف معه، والرابط للمدير برمز المزامنة (22_live_view.sql)
    وزر «🌐 العرض المباشر» في لوحته."""
import ast, base64, io, os, re, shutil, stat, subprocess, sys, tempfile, textwrap, threading, time, types

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


def flat(text):
    return " ".join(text.split())


import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

logged = []
ns = {"__name__": "app", "os": os, "sys": sys, "re": re, "time": time, "threading": threading, "base64": base64,
      "shutil": shutil, "subprocess": subprocess, "tk": tk, "ttk": ttk, "ctk": ctk,
      "log_cloud_error": lambda *a: logged.append(a), "find_edge_exe": lambda: None}
for name in ("CLOUDFLARED_CANDIDATES", "_TRYCLOUDFLARE_RE", "LIVE_LINK_RE", "find_cloudflared", "live_link",
             "LiveViewServer", "LiveTunnel", "live_same", "new_live_token", "live_escape", "_live_noop", "_LiveSink",
             "_LiveShadow", "live_tree_tables", "live_shadow_labels"):
    exec(module_src(name), ns)
S = ns["LiveViewServer"]

# ═══ ١) المفتاح والرابط ═══
tok = ns["new_live_token"]()
assert len(tok) == 43 and re.fullmatch(r"[A-Za-z0-9_-]+", tok) and tok != ns["new_live_token"]()
assert ns["live_same"](tok, tok) and not ns["live_same"](tok, tok[:-1] + ("A" if tok[-1] != "A" else "B"))
assert not ns["live_same"](tok, tok + "x") and not ns["live_same"]("", tok)
link = ns["live_link"]("https://calm-sea-12.trycloudflare.com/", tok)
assert link == f"https://calm-sea-12.trycloudflare.com/?k={tok}" and ns["LIVE_LINK_RE"].match(link)
assert not ns["LIVE_LINK_RE"].match("http://x.com/?k=" + tok) and not ns["LIVE_LINK_RE"].match(link + "&x=<script>")
sql = io.open(os.path.join(os.path.dirname(os.path.abspath(TARGET)), "..", "supabase", "22_live_view.sql"),
              encoding="utf-8").read()
assert r"v_url !~ '^https://[A-Za-z0-9.-]+/\?k=[A-Za-z0-9_-]{24,100}$'" in sql, "صيغة الرابط نفسها في السحابة"
print("✔ مفتاح سري ٣٢ بايتاً (٤٣ حرفاً) ومقارنته ثابتة الزمن؛ والرابط https و?k=المفتاح بالصيغة نفسها في البرنامج والسحابة")

# ═══ ٢) الخادم: يجيب من خيط الواجهة، ويرفض ما سواه ═══
import collections
pending = collections.deque()
srv = S(tok, pending)
srv.FAIL_DELAY = 0.2
port = srv.start()
assert srv.sock.getsockname()[0] == "127.0.0.1", "لا يُستمع إلا على الجهاز نفسه"
stop_ui = threading.Event()


def ui_thread():                          # بديل _live_tick: يجيب الطلبات المنتظرة
    while not stop_ui.is_set():
        while pending:
            params, box = pending.popleft()
            box["status"], box["html"] = 200, f"<p>v={params.get('v', '')}</p>"
            box["event"].set()
        time.sleep(0.02)
threading.Thread(target=ui_thread, daemon=True).start()
import socket


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
            return "RESET", ""
    s.close()
    head, _, body = data.partition(b"\r\n\r\n")
    return head.decode("latin-1"), body.decode("utf-8")


h, b = raw(f"GET /?k={tok}&v=sales HTTP/1.1\r\nHost: x\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 200") and b == "<p>v=sales</p>", (h, b)
for header in ("Cache-Control: no-store", "X-Robots-Tag: noindex, nofollow", "Referrer-Policy: no-referrer",
               "X-Frame-Options: DENY", "frame-ancestors 'none'", "default-src 'none'", "X-Content-Type-Options: nosniff",
               "Content-Type: text/html; charset=utf-8", f"Content-Length: {len(b.encode())}"):
    assert header in h, header
t0 = time.time()
h, b = raw(f"GET /?k={tok[:-1]}Z HTTP/1.1\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 404") and time.time() - t0 >= 0.2 and "v=" not in b, "مفتاح خاطئ: 404 بعد تأخير"
for req, code in ((b"GET / HTTP/1.1\r\n\r\n", 404), (f"GET /admin?k={tok} HTTP/1.1\r\n\r\n".encode(), 404),
                  (f"POST /?k={tok} HTTP/1.1\r\n\r\n".encode(), 405), (f"DELETE /?k={tok} HTTP/1.1\r\n\r\n".encode(), 405),
                  (b"garbage\r\n\r\n", 400), (b"GET /?k=" + b"A" * 9000 + b" HTTP/1.1\r\n\r\n", 400)):
    h, b = raw(req)
    assert h.startswith(f"HTTP/1.1 {code}") or (code == 400 and h == "RESET"), (req[:30], h[:40])
h, b = raw(f"HEAD /?k={tok} HTTP/1.1\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 200") and b == "", "HEAD بلا جسم"
assert srv.served >= 2
stop_ui.set()
time.sleep(0.05)
srv.WAIT_SECONDS = 0.5
h, b = raw(f"GET /?k={tok} HTTP/1.1\r\n\r\n".encode())
assert h.startswith("HTTP/1.1 503") and "مشغول" in b, "الواجهة لا تجيب ← «مشغول» بعد المهلة، لا تعليق"
srv.stop()
time.sleep(1.2)
try:
    socket.create_connection(("127.0.0.1", port), timeout=1).close()
    stopped = False
except OSError:
    stopped = True
assert stopped, "الإيقاف يغلق المنفذ"
print("✔ الخادم: 127.0.0.1 وحده، GET/HEAD وحدهما، والمفتاح الخاطئ أو المسار الآخر 404 بعد تأخير، والطلب الكبير والتالف "
      "مرفوضان، ورؤوس الأمان كاملة، والجواب من خيط الواجهة (أو «مشغول» بعد المهلة)، والإيقاف يغلق المنفذ")

# ═══ ٣) النفق: الرابط من مخرجات cloudflared، ويُعاد التشغيل إن توقف ═══
work = tempfile.mkdtemp(prefix="live_tunnel_")
fake = os.path.join(work, "cloudflared")
with open(fake, "w") as f:
    f.write("#!%s\nimport sys, time, os\ncount = os.path.join(%r, 'runs')\nn = int(open(count).read()) + 1 if "
            "os.path.exists(count) else 1\nopen(count, 'w').write(str(n))\nsys.stderr.write('INF Requesting new quick "
            "Tunnel\\n')\nsys.stderr.write('INF |  https://bright-moon-%%d.trycloudflare.com  |\\n' %% n)\nsys.stderr.flush()\n"
            "time.sleep(0.6 if n == 1 else 30)\n" % (sys.executable, work))
os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
old_path = os.environ.get("PATH", "")
os.environ["PATH"] = work + os.pathsep + old_path
assert ns["find_cloudflared"]() == fake, "أداة الربط من PATH"
T = ns["LiveTunnel"]
T.BACKOFF = (0.3, 0.3)
tun = T(fake, 51234)
assert tun.command()[1:] == ["tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:51234"]
tun.start()
end = time.time() + 10
while tun.url != "https://bright-moon-1.trycloudflare.com" and time.time() < end:
    time.sleep(0.05)
assert tun.url == "https://bright-moon-1.trycloudflare.com" and tun.state == "ready", (tun.url, tun.state)
end = time.time() + 15
while tun.url != "https://bright-moon-2.trycloudflare.com" and time.time() < end:
    time.sleep(0.05)
assert tun.url == "https://bright-moon-2.trycloudflare.com", ("أعيد التشغيل برابط جديد", tun.url, tun.state)
proc = tun.proc
tun.stop()
assert tun.url is None and tun.state == "stopped" and proc.poll() is not None, "الإيقاف ينهي الأداة"
os.environ["PATH"] = old_path
print("✔ النفق: رابط trycloudflare يُقرأ من مخرجات cloudflared، وتوقّفها ← إعادة تشغيل برابطٍ جديد، والإيقاف ينهيها")

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
print("✔ الظل: دوال الشاشة نفسها بفترةٍ أخرى — الحركات بالمرجع، والإطارات خفية، والجداول نسخٌ بأعمدتها وعناوينها، والأدوات "
      "تُقرأ ولا تُكتب، وردود الشاشة ودوال الكتابة لا تعمل؛ والإجمالي المكرر مرة واحدة، والشاشة الحقيقية كما هي")
root.destroy()

# ═══ ٥) البرنامج: الصفحات والتشغيل والإيقاف والإرسال ═══
page = member("live_page")
assert "self.ensure_screen_built(screen, background=True)" in page and "p if p in periods else self.current_display_month" in page
assert set(re.findall(r'\("(\w+)", "[^"]+", "[^"]+"\)', member("LIVE_SCREENS"))) == {
    "stages", "khayas", "sales", "inbound", "factory", "losses"}
html = member("live_html")
assert html.count("esc(") >= 15 and 'onchange="this.form.submit()"' in html
assert "esc(v)" in html and "esc(h)" in html and "esc(label)" in html, "كل نصٍّ في الصفحة مُهرَّب"
assert ns["live_escape"]('"><script>x</script>') == "&quot;&gt;&lt;script&gt;x&lt;/script&gt;"
tick = member("_live_tick")
assert "box[\"event\"].set()" in tick and "self.live_page(params)" in tick and "self.after(self.LIVE_TICK_MS, self._live_tick)" in tick
assert "self._live_publish_async(link)" in tick
start = member("start_live_view")
assert 'if getattr(self, "view_only", False):' in start and "save_ui_pref(LIVE_ENABLED_PREF, True)" in start
assert "LiveTunnel(exe, server.port).start() if exe else None" in start
stop = member("stop_live_view")
assert 'self._live_publish_async("")' in stop and "save_ui_pref(LIVE_ENABLED_PREF, False)" in stop
assert "self.stop_live_view(user=False)" in member("on_app_closing")
assert "self.after(3000, self.start_live_view)" in src and "if self.live_enabled_pref()" in src
assert 'text="🌐 مباشر"' in src and "command=self.open_live_view_dialog" in src
token_fn = member("live_token")
assert "save_ui_pref(LIVE_TOKEN_PREF, token)" in token_fn, "المفتاح في تفضيلات الجهاز — لا في قاعدة البيانات ولا السحابة"
assert "CLOUDFLARED_WINGET" in member("install_cloudflared") and "Cloudflare.cloudflared" in module_src("CLOUDFLARED_WINGET")
pub = module_src("cloud_publish_live_link")
assert '"client_publish_live_link"' in pub and '"p_sync_token": CURRENT_SYNC_TOKEN' in pub
assert 'table("live_links")' in module_src("cloud_get_live_link") and "get_supabase_admin_client()" in module_src("cloud_get_live_link")
if "class AdminPanel" in src:
    admin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AdminPanel")
    open_live = next(m for m in admin.body if isinstance(m, ast.FunctionDef) and m.name == "open_client_live_view")
    body = ast.get_source_segment(src, open_live)
    assert "LIVE_LINK_RE.match(url)" in body and "open_url_window(url)" in body
    assert 'text="🌐 العرض المباشر"' in src
for mod_name in ("http.server", "socketserver", "secrets", "hmac", "queue"):
    assert not re.search(rf"^\s*import {re.escape(mod_name)}\b", src, re.M), f"{mod_name}: قد لا يحمله exe الحالي"
print("✔ البرنامج: الشاشات الست بالفترة (والشاشة تُبنى إن لم تُفتح)، وكل نصٍّ مُهرَّب، والتشغيل يعود مع البرنامج ويتوقف معه، "
      "والمفتاح على الجهاز وحده، والرابط للمدير برمز المزامنة ولوحته تفتحه — بلا مكتبةٍ جديدة على exe")

print("\n✅ 1.94: العرض المباشر — رابط المدير الخاص للقراءة فقط")
