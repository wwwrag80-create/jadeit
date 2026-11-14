# -*- coding: utf-8 -*-
"""2.00 الرابط تلقائياً بالكامل على جهاز المصنع، و«الرصيد» في كاستنج الرابط، وأقسام «العمليات»:
  • حساب عميل: الرابط يعمل وحده مع البرنامج وبعد كل تحديث (بلا زرٍّ ولا فحصٍ يدوي)، ولا يُوقف من الجهاز، ويُعاد إن
    توقف، ويفحص نفسه في الخلفية (بعد التشغيل، وكل ١٠ دقائق، وبعد الاستيقاظ) ويُصلح ما يُصلح وحده، ويضبط الطاقة مرة؛
  • الطاقة: الغطاء «لا شيء» على الشاحن والبطارية، بلا إذنٍ أولاً؛
  • كاستنج الرابط: «الرصيد» بعد كل عملية مكان «الخياس» — والجهاز كما هو؛
  • «العمليات»: كل قسمٍ شريحة، وقسم كل عملية على بطاقتها."""
import ast, io, sys, textwrap, time as _time

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
methods = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}


def member(name):
    node = methods.get(name) or next(m for m in cls.body if isinstance(m, ast.Assign)
                                     and getattr(m.targets[0], "id", "") == name)
    deco = "".join(f"@{ast.get_source_segment(src, d)}\n" for d in getattr(node, "decorator_list", []))
    return deco + textwrap.dedent(ast.get_source_segment(src, node))


def make(names, extra="", env=None):
    ns = dict(env or {})
    body = "\n\n".join(member(n) for n in names) + "\n\n" + extra
    exec("class App:\n" + textwrap.indent(body, "    "), ns)
    return ns["App"], ns


# ═══ ١) الرابط يعمل دائماً لحساب العميل ═══
AWAKE = []
env = {"time": _time, "sys": sys, "datetime": __import__("datetime"), "log_cloud_error": lambda *a: None,
       "live_keep_awake": lambda on, display=False: AWAKE.append((on, display))}     # (2.00.1) يُؤكَّد كل دقيقة
A, _ = make(("live_always_on", "live_pinned", "live_enabled_pref"), extra='''
admin_mode = True
view_only = False
flags = ()

def live_admin_mode(self):
    return self.admin_mode

def remote_flag(self, name):
    return name in self.flags
''', env=dict(env, load_ui_prefs=lambda: {}, LIVE_ENABLED_PREF="x"))
a = A()
assert a.live_always_on() and a.live_pinned() and a.live_enabled_pref(), "حساب عميل: يعمل دائماً ولا يُوقف من الجهاز"
a.view_only = True
assert not a.live_always_on(), "عرض المدير للقراءة: لا رابط"
a.view_only, a.admin_mode = False, False
assert not a.live_always_on() and not a.live_pinned() and not a.live_enabled_pref(), \
    "برنامج المدير والجلسة المحلية: الزر كما كان"
init = src[src.index("if self.live_always_on():\n            self.after(3000, self.live_auto_tick)"):][:400]
assert "elif self.live_enabled_pref()" in init, "مع البرنامج (وبعد كل تحديث): الرابط يبدأ وحده"
assert "رابط المدير يعمل تلقائياً دائماً" in member("stop_live_view")
print("✔ حساب عميل: الرابط يعمل وحده مع البرنامج وبعد كل تحديث، ولا يُوقف من الجهاز (والمدير والجلسة المحلية كما كانا)")

# ═══ ٢) الدورة كل دقيقة: يُشغَّل إن توقف، والطاقة مرة، والفحص في وقته ═══
T, _ = make(("live_auto_tick", "LIVE_AUTO_EVERY_MS", "LIVE_AUTO_CHECK_SECS"), extra='''
def live_always_on(self):
    return self.on

def start_live_view(self, user=False):
    self.calls.append("start")
    if self.can_start:
        self._live = {"server": object(), "auto_check_at": self.check_at}
    return self.can_start

def live_power_auto(self):
    self.calls.append("power")

def live_auto_check(self):
    self.calls.append("check")
    self._live["auto_check_at"] = time.time()

def after(self, ms, fn):
    self.scheduled.append(ms)
''', env=env)
t = T()
t.__dict__.update(on=True, calls=[], scheduled=[], can_start=False, check_at=0)
t.live_auto_tick()
assert t.calls == ["start"] and t.scheduled == [60_000], "المنفذ مشغول: يُعاد بعد دقيقة (لا يتوقف أبداً)"
t.can_start = True
t.check_at = _time.time()
t.live_auto_tick()
assert t.calls == ["start", "start", "power"], "شُغّل: الطاقة مرة، ولا فحص قبل وقته"
t.live_auto_tick()
assert t.calls == ["start", "start", "power"], "يعمل: لا تشغيل ولا طاقة مرةً ثانية"
t._live["auto_check_at"] = _time.time() - 601
t.live_auto_tick()
assert t.calls[-1] == "check" and len(t.scheduled) == 4, "حان وقت الفحص (١٠ دقائق)"
assert AWAKE and all(a == (True, False) for a in AWAKE), "ومنع السكون يُؤكَّد في كل دورةٍ والرابط يعمل"
t.on = False
t.live_auto_tick()
assert len(t.scheduled) == 4, "ليس حساب عميل: تتوقف الدورة"
start = member("start_live_view")
assert '"auto_check_at": time.time() - self.LIVE_AUTO_CHECK_SECS + self.LIVE_AUTO_FIRST_SECS' in start, \
    "أول فحصٍ بعد التشغيل بدقيقة وربع (بعد أن يجهّز الوسيط)"
assert 'live["auto_check_at"] = 0' in member("_live_tick"), "وفحصٌ فور الاستيقاظ من النوم"
print("✔ كل دقيقة: يُشغَّل إن توقف، والطاقة مرة، والفحص بعد التشغيل وكل ١٠ دقائق وبعد الاستيقاظ")

# ═══ ٣) الفحص في الخلفية وما يُصلح وحده ═══
C, _ = make(("live_auto_check", "live_auto_fix", "LIVE_AUTO_LOGIN_GAP"), extra='''
def live_state(self):
    return {"provider": "tailscale", "url": "https://pc.ts.net"}

def live_provider(self):
    return "tailscale"

def live_check_compute(self, snap, provider, exe, relay=None):
    return self.steps

def start_live_view(self, user=False):
    self.calls.append("start")

def live_start_relay(self):
    self.calls.append("relay")

def live_sync_async(self, url=None, then=None):
    self.calls.append("sync")

def live_power_auto(self):
    self.calls.append("power")

def install_live_tool(self, provider, done=None):
    self.calls.append("install")
    done(True, "")

def live_tailscale_login(self, done=None):
    self.calls.append("login")
''', env=dict(env, find_tailscale=lambda: "ts.exe", find_cloudflared=lambda: None,
              tk_background=lambda host, work, done: done(work())))
c = C()
c.__dict__.update(calls=[], _live={"server": object(), "relay": None})
c.steps = [{"ok": True, "title": "أ", "action": None}, {"ok": False, "title": "Funnel", "action": "relay"}]
c.live_auto_check()
assert c.calls == ["relay", "sync"] and c._live["check_text"].startswith("فحص تلقائي") \
    and "توقف عند: Funnel" in c._live["check_text"] and not c._live["auto_busy"], \
    "الوسيط يُعاد وحده، والنتيجة تصل المدير"
c.steps = [{"ok": True, "title": "أ", "action": None}]
c.calls = []
c.live_auto_check()
assert c.calls == ["sync"] and "✔ كل الخطوات مكتملة" in c._live["check_text"]
c.calls = []
for action in ("start", "sync", "power", "install", "install", "login", "login", "enable", None):
    c.live_auto_fix(action)
assert c.calls == ["start", "sync", "power", "install", "relay", "login"], \
    f"التثبيت مرة، وصفحة الدخول مرة كل ٦ ساعات، وتفعيل Funnel للمدير: {c.calls}"
print("✔ الفحص في الخلفية بلا نافذة: نتيجته للمدير، ويُصلح وحده (الوسيط، الإرسال، الطاقة، التثبيت مرة، صفحة الدخول)")

# ═══ ٤) الطاقة ═══
pw = src[src.index("_PWR_DC_SETTINGS = "):][:80]
assert '("SUB_BUTTONS", "LIDACTION")' in pw
fix = ast.get_source_segment(src, next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "live_power_fix"))
assert '"/setdcvalueindex"' in fix and "if not elevate:" in fix and fix.index("if not elevate:") < fix.index('"runas"')
auto = member("live_power_auto")
assert "live_power_ok(live_power_read())" in auto and "live_power_fix(elevate=True)" in auto
print("✔ الطاقة وحدها: الغطاء «لا شيء» على الشاحن والبطارية، بلا إذنٍ أولاً ثم إذن ويندوز مرة إن لزم")

# ═══ ٥) «الرصيد» في كاستنج الرابط ═══
render = member("render_stage_ops_table")
assert 'running_col = bool(recover_name) and bool(getattr(self, "live_running_balance", False))' in render
assert 'kh_col = "الرصيد" if running_col else "الخياس"' in render
assert "running = round(running + khayas, 2)" in render and 'vals.append(f"{running:.2f}" if running_col else f"{khayas:.2f}")' in render
assert "live_running_balance = False" in src and "live_running_balance=True" in member("live_view_stages")
print("✔ كاستنج الرابط: «الرصيد» بعد كل عملية مكان «الخياس» (والإجمالي بالرصيد الأخير) — والجهاز كما هو")

# ═══ ٦) أقسام «العمليات» ═══
S, _ = make(("live_recent_sections", "live_recent_match", "live_recent_group", "movement_section"), extra='''
categories = {"أقسام_خياس_إضافية": ["السبيكة"]}
JOURNAL_TYPES = ("قيد يومي مدين", "قيد يومي دائن")
SALE_TYPES = ("مبيعات ذهب",)

def get_all_stage_categories(self):
    return ["الكاستنج", "التلميع", "التلميع/البف", "خياس الطقوم"] + self.categories["أقسام_خياس_إضافية"]

def get_display_label(self, cat):
    return {"التلميع/البف": "بوليش 1"}.get(cat, cat)
''')
s = S()
s.categories.update({"المصنعين": ["خالد"], "المركبين": ["سالم"]})
keys = [k for k, _l in s.live_recent_sections()]
assert keys[:2] == ["all", "stages"] and keys[-4:] == ["inbound", "sales", "journal", "other"]
assert {"المصنعين", "المركبين", "الكاستنج", "التلميع", "التلميع/البف", "السبيكة"} <= set(keys), keys
assert dict(s.live_recent_sections())["التلميع/البف"] == "بوليش 1", "بأسماء الأقسام كما سمّاها المصنع"
tm = {"صرف كاستنج": "الكاستنج", "صرف السبيكة": "السبيكة"}
cast = {"النوع": "صرف كاستنج", "الاسم": "كاستنج"}
mfg = {"النوع": "صرف ذهب", "الاسم": "خالد"}
sale = {"النوع": "مبيعات ذهب", "الاسم": "زبون"}
gen = {"النوع": "صرف السبيكة", "الاسم": "السبيكة"}
odd = {"النوع": "رصيد افتتاحي", "الاسم": "المصنع"}
assert s.live_recent_match(cast, "الكاستنج", tm) and not s.live_recent_match(mfg, "الكاستنج", tm)
assert s.live_recent_match(mfg, "المصنعين", tm) and s.live_recent_match(gen, "السبيكة", tm)
assert s.live_recent_match(cast, "stages", tm) and s.live_recent_match(sale, "sales", tm) and s.live_recent_match(odd, "other", tm)
assert all(s.live_recent_match(x, "all", tm) for x in (cast, mfg, sale, gen, odd))
page = member("live_recent_page")
assert "type_map = self._stage_type_map()" in page and "self.live_recent_match(inv, group, type_map)" in page
view = member("live_view_recent")
assert "sections = self.live_recent_sections()" in view and "section=self.movement_label(inv)" in view
assert '<span class="secb">' in member("live_move_html")
print("✔ العمليات: كل قسمٍ شريحة (بأسماء المصنع)، واختياره يعرض عملياته — وقسم كل عملية شارةٌ على بطاقتها")
print("✔ الرابط التلقائي 2.00 سليم")
