# -*- coding: utf-8 -*-
"""
الميزان الإلكتروني (الدفعة ١٦) — وحدة القراءة ودوال البرنامج نفسها، بلا ميزان حقيقي:

  • صيغ الموازين الشائعة (A&D، Sartorius، Mettler، Ohaus، Radwag، Kern) تُقرأ وزناً بالجرام،
    والقراءة المتحرّكة تُعلَّم غير مستقرة، والوحدات تُحوَّل (قيراط، كجم، أونصة…).
  • سطر التاريخ أو رقم التعريف أو وضع العدّ بالقطعة أو التحميل الزائد لا يُقرأ وزناً.
  • القارئ في خيط خلفي يعيد الاتصال وحده بعد فصل الكابل، ولا يعتمد قراءة قديمة.
  • F2: يُكتب الوزن المستقر فقط (ينتظر الثبات ثم ينبّه)، والسالب يُرفض، وبلا ميزان تنبيه لا خطأ.
"""
import ast, io, os, sys, textwrap, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scale_reader as sr

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def body(name):
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name))


# ═══ ١) الصيغ ═══
CASES = {
    "ST,+00012.345  g": (12.345, True),        # A&D مستقر
    "US,+00012.340  g": (12.34, False),        # A&D متحرّك
    "N     +   12.345 g": (12.345, True),      # Sartorius
    "S S      12.345 g": (12.345, True),       # Mettler SICS مستقر
    "S D      12.340 g": (12.34, False),       # Mettler SICS متحرّك
    "12.345 g ?": (12.345, False),             # Ohaus متحرّك
    "SI ?   12.345 g": (12.345, False),        # Radwag متحرّك
    "    12.345 g": (12.345, True),            # Kern / عام
    "+12,345 g": (12.345, True),               # فاصلة عشرية
    "  61.73 ct": (12.346, True),              # قيراط
    "0.050 kg": (50.0, True),
    "1.000 ozt": (31.1035, True),              # أونصة ذهب
    "+  12.345 G": (12.345, True),
    "12.34": (12.34, True),                    # رقم وحده
    "-   0.012 g": (-0.012, True),
}
for line, (grams, stable) in CASES.items():
    r = sr.parse_weight(line)
    assert r and r["grams"] == grams and r["stable"] is stable, (line, r)
for junk in ("", "OL", "ERR 4", "2026/10/01 12:30", "ID No. 123", "QT,+00100 PC", "Date 01.10.2026", "\x00\x00"):
    assert sr.parse_weight(junk) is None, junk
print(f"✔ {len(CASES)} صيغة لموازين الذهب الشائعة تُقرأ بالجرام مع حالة الثبات، والوحدات تُحوَّل")
print("✔ سطر التاريخ ورقم التعريف ووضع العدّ بالقطعة والتحميل الزائد لا تُقرأ وزناً")


# ═══ ٢) القارئ: خيط خلفي، إعادة اتصال، وحداثة القراءة ═══
class FakePort:
    def __init__(self, lines, fail_after=None):
        self.lines, self.fail_after, self.reads, self.writes, self.closed = list(lines), fail_after, 0, [], False

    def readline(self):
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            raise OSError("الكابل فُصل")
        time.sleep(0.01)
        return self.lines.pop(0).encode() + b"\r\n" if self.lines else b""

    def write(self, data):
        self.writes.append(data)

    def close(self):
        self.closed = True


opened = []


def opener(port, baud):
    if len(opened) == 0:
        p = FakePort(["US,+00010.000  g", "ST,+00012.345  g"], fail_after=2)
    else:
        p = FakePort(["ST,+00020.500  g"])
    opened.append((port, baud, p))
    return p


sr.RECONNECT_SECONDS = 0.05
reader = sr.ScaleReader("COM3", 4800, request=b"Q\r\n", interval=0.01, opener=opener)
reader.start()
deadline = time.time() + 5
while time.time() < deadline and not (reader.latest and reader.latest["grams"] == 20.5):
    time.sleep(0.02)
reader.stop()
assert reader._thread.daemon and opened[0][:2] == ("COM3", 4800)
assert len(opened) >= 2 and opened[0][2].closed, "لم يُعد الاتصال بعد فصل الكابل"
assert opened[0][2].writes and opened[0][2].writes[0] == b"Q\r\n", "أمر طلب الوزن لم يُرسل"
assert reader.latest["grams"] == 20.5 and reader.latest["stable"]
assert reader.last_raw == "ST,+00020.500  g"
print("✔ القارئ يرسل أمر الطلب ويقرأ في خيط خلفي (daemon)، ويعيد الاتصال وحده بعد فصل الكابل")

reader.latest["at"] = time.time() - 10
assert reader.current() is None and reader.status_text() in ("⚖️ الميزان: غير متصل", "⚖️ الميزان: بانتظار قراءة")
reader.feed("S D   7.10 g")
assert reader.current()["stable"] is False and reader.status_text() == "⚖️ 7.10 جم …"
reader.feed("S S   7.12 g")
assert reader.status_text() == "⚖️ 7.12 جم ✓"
print("✔ القراءة الأقدم من ٣ ثوانٍ لا تُعتمد (ميزان مفصول)، والمؤشر يميّز المستقر من المتحرّك")


# ═══ ٣) F2 في البرنامج: الوزن المستقر فقط في الخانة ═══
class FakeEntry:
    def __init__(self, text=""): self.text = text
    def delete(self, a, b): self.text = ""
    def insert(self, i, s): self.text = s + self.text
    def winfo_toplevel(self): return None


class FakeTk:
    Entry = FakeEntry


ns = {"tk": FakeTk}
exec("class Base:\n" + textwrap.indent(textwrap.dedent(body("insert_scale_weight")), "    "), ns)


class App(ns["Base"]):
    def __init__(self):
        self.toasts, self.later = [], []

    def toast(self, text, kind="info", ms=0, parent=None):
        self.toasts.append((kind, text))

    def after(self, ms, fn):
        self.later.append(fn)


app = App()
e = FakeEntry("99")
assert app.insert_scale_weight(e) is False and app.toasts[-1][0] == "warn" and e.text == "99"
app.scale_reader = sr.ScaleReader("COM1")
assert app.insert_scale_weight(e) is False and app.toasts[-1][0] == "error", "بلا قراءة يجب تنبيه"
app.scale_reader.feed("ST,+00012.345  g")
assert app.insert_scale_weight("not an entry") is False and "خانة الوزن" in app.toasts[-1][1]
assert app.insert_scale_weight(e) is True and e.text == "12.35" and app.toasts[-1][0] == "success"
print("✔ F2: الوزن المستقر يُكتب في الخانة بدقة النظام (12.345 ← 12.35)، وبلا ميزان أو بلا قراءة تنبيه")

app.scale_reader.feed("US,+00015.000  g")
e2 = FakeEntry("")
assert app.insert_scale_weight(e2) is None and app.later and e2.text == ""
app.scale_reader.feed("ST,+00015.010  g")
app.later.pop()()                           # المحاولة التالية بعد ربع ثانية
assert e2.text == "15.01"
app.scale_reader.feed("US,+00016.000  g")
e3 = FakeEntry("")
assert app.insert_scale_weight(e3, attempts=12) is False and "غير مستقرة" in app.toasts[-1][1] and e3.text == ""
app.scale_reader.feed("ST,-00000.500  g")
assert app.insert_scale_weight(e3) is False and "سالب" in app.toasts[-1][1]
print("✔ القراءة المتحرّكة تُنتظر حتى تثبت (٣ ثوانٍ) ثم تنبيه، والوزن السالب يُرفض")

# الربط في البرنامج
ind = body("build_scale_indicator")
assert 'self.bind_all("<F2>", self._on_scale_key, add="+")' in ind and "self.open_scale_settings()" in ind
assert "self.after(500, self._scale_tick)" in body("_scale_tick")
assert "self.scale_reader.stop(" in body("on_app_closing")
assert "if not IS_ADMIN_BUILD:\n            self.build_scale_indicator()" in src
start = body("start_scale_reader")
assert "scale_reader.ScaleReader(conf[\"port\"], conf[\"baud\"]" in start and "old.stop(" in start
settings = body("open_scale_settings")
for key in ("scale_enabled", "scale_port", "scale_baud", "scale_preset"):
    assert f'save_ui_pref("{key}"' in settings, key
bx = io.open(os.path.join(HERE, "build_exe.py"), encoding="utf-8").read()
assert '"scale_reader"' in bx and '("serial", "pyserial")' in bx
assert "pyserial" in io.open(os.path.join(HERE, "requirements-desktop.txt"), encoding="utf-8").read()
print("✔ مؤشر الميزان في الشريط السفلي (يفتح الإعداد)، F2 في كل النوافذ، الإعداد لهذا الجهاز، "
      "والإيقاف عند الإغلاق — ونسخة المدير بلا ميزان")

print("\n✅ الميزان الإلكتروني سليم")
