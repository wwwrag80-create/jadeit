# -*- coding: utf-8 -*-
"""2.00.1 «الشاشة تنطفئ فيتوقف الرابط»: على أجهزة «السكون الحديث» (S0 Low Power Idle) انطفاء الشاشة نفسه يُدخلها
السكون فيجمّد ويندوز البرامج — فلا يكفي منع النوم وحده:
  • live_modern_standby: نوع الجهاز من «powercfg /a» (القسم المتاح وحده، بأي لغة)؛
  • live_power_request: طلب طاقة رسمي باسم البرنامج — النظام يعمل، والبرنامج لا يُجمَّد، والشاشة مضاءة عند الحاجة؛
  • live_keep_awake: والشاشة (ES_DISPLAY_REQUIRED) على تلك الأجهزة — ويُؤكَّد كل دقيقة؛
  • على الجهاز نافذة «السماح» بما فُعّل (وزر «🔓 السماح» إن احتاج ويندوز إذنه)، والمدير يرى ذلك."""
import ast, ctypes, io, re, sys, textwrap, types

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
methods = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}


def member(name):
    node = methods.get(name) or next(m for m in cls.body if isinstance(m, ast.Assign)
                                     and getattr(m.targets[0], "id", "") == name)
    return textwrap.dedent(ast.get_source_segment(src, node))


def module_src(name):
    node = next(n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return ast.get_source_segment(src, node)


WIN = types.SimpleNamespace(platform="win32")

# ═══ ١) نوع الجهاز ═══
OUT = {}
env = {"sys": WIN, "re": re, "live_run_capture": lambda cmd, timeout=30, env=None: OUT["v"]}
exec(module_src("live_modern_standby"), env)
ms = env["live_modern_standby"]
OUT["v"] = (0, "The following sleep states are available on this system:\n    Standby (S0 Low Power Idle) Network Connected\n"
               "    Hibernate\n    Fast Startup\n\nThe following sleep states are not available on this system:\n"
               "    Standby (S1)\n        The system firmware does not support this standby state.\n    Standby (S3)\n")
assert ms() is True, "سكونٌ حديث متاح"
OUT["v"] = (0, "The following sleep states are available on this system:\n    Standby (S3)\n    Hibernate\n\n"
               "The following sleep states are not available on this system:\n    Standby (S0 Low Power Idle)\n"
               "        The system firmware does not support this standby state.\n")
assert ms() is False, "S3 متاح، وS0 في غير المتاح وحده: جهازٌ عادي"
OUT["v"] = (0, "حالات السكون التالية متوفرة على هذا النظام:\n    وضع الاستعداد (S0 خامل منخفض الطاقة) الشبكة متصلة\n"
               "    الإسبات\n\nحالات السكون التالية غير متوفرة:\n    وضع الاستعداد (S3)\n")
assert ms() is True, "بأي لغةٍ لويندوز"
OUT["v"] = (1, "")
assert ms() is None, "تعذّرت القراءة: لا يُعرف"
assert env["live_modern_standby"].__globals__["sys"] is WIN
print("✔ نوع الجهاز من «powercfg /a»: القسم المتاح وحده وبأي لغة (S0 = سكونٌ حديث)")

# ═══ ٢) طلب الطاقة الرسمي ═══
CALLS = []


class K32:
    def __init__(self):
        for name in ("PowerCreateRequest", "PowerSetRequest", "PowerClearRequest", "CloseHandle",
                     "SetThreadExecutionState"):
            setattr(self, name, getattr(self, "_" + name))

    def _PowerCreateRequest(self, ctx):
        CALLS.append(("create", ctx._obj.SimpleReasonString, ctx._obj.Flags))
        return 4242

    def _PowerSetRequest(self, h, t):
        CALLS.append(("set", h, t))
        return 1

    def _PowerClearRequest(self, h, t):
        CALLS.append(("clear", h, t))
        return 1

    def _CloseHandle(self, h):
        CALLS.append(("close", h))
        return 1

    def _SetThreadExecutionState(self, flags):
        CALLS.append(("es", flags))
        return 1


class _Fn:
    """دالة ctypes مزيّفة تقبل restype/argtypes"""
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *a):
        return self.fn(*a)


k32 = K32()
for name in ("PowerCreateRequest", "PowerSetRequest", "PowerClearRequest", "CloseHandle", "SetThreadExecutionState"):
    setattr(k32, name, _Fn(getattr(k32, name)))
had = getattr(ctypes, "windll", None)
ctypes.windll = types.SimpleNamespace(kernel32=k32)
try:
    penv = {"sys": WIN}
    exec(module_src("_LIVE_POWER_REQ") + "\n" + module_src("LIVE_POWER_REASON") + "\n" + module_src("live_power_request")
         + "\n" + module_src("live_keep_awake"), penv)
    req, awake = penv["live_power_request"], penv["live_keep_awake"]
    assert req(True, display=True) == (0, 1, 3)
    assert CALLS[0][0] == "create" and "جاديت" in CALLS[0][1] and CALLS[0][2] == 1, "باسم البرنامج (يظهر في powercfg /requests)"
    assert [c for c in CALLS if c[0] == "set"] == [("set", 4242, 0), ("set", 4242, 1), ("set", 4242, 3)], \
        "الشاشة، والنظام، والتنفيذ (لا يُجمَّد في السكون الحديث)"
    CALLS.clear()
    assert req(True, display=False) == (1, 3)
    assert CALLS[:4] == [("clear", 4242, 0), ("clear", 4242, 1), ("clear", 4242, 3), ("close", 4242)], \
        "الطلب السابق يُلغى قبل الجديد (لا طلبات متراكمة)"
    CALLS.clear()
    assert req(False) == () and CALLS == [("clear", 4242, 1), ("clear", 4242, 3), ("close", 4242)], "الإيقاف يُلغيه"
    CALLS.clear()
    awake(True, display=True)
    awake(True)
    awake(False)
    assert CALLS == [("es", 0x80000003), ("es", 0x80000001), ("es", 0x80000000)], \
        "ES_CONTINUOUS | النظام | (الشاشة على أجهزة السكون الحديث)"
finally:
    if had is None:
        del ctypes.windll
    else:
        ctypes.windll = had
linux = {"sys": types.SimpleNamespace(platform="linux")}
exec(module_src("_LIVE_POWER_REQ") + "\n" + module_src("LIVE_POWER_REASON") + "\n" + module_src("live_power_request"), linux)
assert linux["live_power_request"](True, display=True) == ()
print("✔ طلب طاقة رسمي باسم البرنامج: النظام يعمل، والبرنامج لا يُجمَّد، والشاشة مضاءة عند الحاجة — ويُلغى بالإيقاف")

# ═══ ٣) التطبيق في البرنامج ═══
ns = {"sys": WIN, "live_keep_awake": lambda on, display=False: CALLS.append(("awake", on, display)),
      "live_power_request": lambda on, display=False: (CALLS.append(("req", on, display)), (1, 3))[1]}
exec("class A:\n" + textwrap.indent(member("live_awake_apply"), "    "), ns)
a = ns["A"]()
a._live = {"server": object()}
CALLS.clear()
assert a.live_awake_apply(None) is True and a._live["display_on"], "قبل معرفة نوع الجهاز: الشاشة مضاءة (الأسلم للرابط)"
assert a.live_awake_apply(False) is False and not a._live["display_on"], "جهازٌ عادي: الشاشة تنطفئ والنظام يعمل"
assert a.live_awake_apply(True) is True and a._live["modern_standby"] is True
assert CALLS == [("awake", True, True), ("req", True, True), ("awake", True, False), ("req", True, False),
                 ("awake", True, True), ("req", True, True)]
a._live = {}
assert a.live_awake_apply(True) is None, "الرابط لا يعمل: لا شيء"
start = member("start_live_view")
assert "self.live_awake_apply(None)" in start and "tk_background(self, live_modern_standby, self.live_awake_apply)" in start
assert "live_power_request(False)" in member("stop_live_view")
assert 'live_keep_awake(True, display=bool(live.get("display_on")))' in member("live_auto_tick"), "يُؤكَّد كل دقيقة"
fix = ast.get_source_segment(src, next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "live_power_fix"))
assert "*_PWR_WIFI" in fix, "والواي فاي «أقصى أداء»"
print("✔ مع الرابط: الطلب فوراً ثم نوع الجهاز (الشاشة على السكون الحديث وحده)، ويُؤكَّد كل دقيقة، ويُلغى بالإيقاف")

# ═══ ٤) «السماح» على الجهاز، وما يراه المدير ═══
notice = member("live_awake_notice")
assert "self.LIVE_AWAKE_NOTICE_PREF" in notice and "if not force and power_ok and load_ui_prefs().get(" in notice, \
    "مرةً واحدة على الجهاز إن ضُبط كل شيء"
assert "🔓 السماح" in notice and "live_power_fix(elevate=True)" in notice and "if not power_ok:" in notice, \
    "وإن لم يسمح ويندوز: زر «🔓 السماح» يطلب إذنه"
assert "إغلاق غطاء اللابتوب لا ينيمه" in notice and "الشاشة تبقى مضاءة" in notice
assert "self.live_awake_notice(ok_)" in member("live_power_auto")
summary = member("live_state_summary")
assert "الشاشة مضاءة (سكونٌ حديث)" in summary
assert "السكون الحديث" in member("live_check_power")
print("✔ على الجهاز نافذة «السماح» بما فُعّل (وزر «🔓 السماح» إن احتاج ويندوز إذنه)، والمدير يرى حال الشاشة")
print("✔ الرابط والشاشة مطفأة 2.00.1 سليم")
