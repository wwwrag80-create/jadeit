# -*- coding: utf-8 -*-
"""
جاديت — قراءة الميزان الإلكتروني (منفذ تسلسلي RS-232 أو USB)
=========================================================

الوزن يُقرأ من الميزان مباشرة بدل كتابته يدوياً: يضغط المستخدم F2 داخل خانة الوزن
فتُكتب القراءة المستقرة فيها — فلا خطأ نقل ولا رقم مقلوب.

مبادئ التصميم:
  ١) لا يلمس الواجهة أبداً: خيط خلفي (daemon) يقرأ ويحفظ آخر قراءة، والواجهة تسأله
     بـ after() من خيطها هي.
  ٢) pyserial اختيارية: بدونها تُعطَّل الميزة برسالة واضحة ولا يتأثر البرنامج.
  ٣) يفهم صيغ موازين الذهب الشائعة كما يرسلها كل ميزان:
        A&D           ST,+00012.345  g      (US = غير مستقر)
        Sartorius     N     +   12.345 g
        Mettler SICS  S S      12.345 g     (S D = غير مستقر)
        Ohaus         12.345 g ?            (? = غير مستقر)
        Radwag        SI ?   12.345 g
        Kern / عام    12.345 g
     ويحوّل الوحدات (g، ct، kg، mg، ozt، dwt) إلى جرام.
  ٤) يعيد الاتصال تلقائياً عند فصل الكابل أو إطفاء الميزان.
"""

import re
import threading
import time

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except Exception:          # مكتبة الاتصال غير مثبّتة: الميزة معطّلة فقط
    serial = None
    SERIAL_AVAILABLE = False

# ---------------------------------------------------------------- الإعدادات
BAUD_RATES = (1200, 2400, 4800, 9600, 19200, 38400)
DEFAULT_BAUD = 9600
FRESH_SECONDS = 3.0         # قراءة أقدم من هذا لا تُعتمد (الميزان فُصل أو توقّف)
RECONNECT_SECONDS = 3.0

# أوامر طلب الوزن لكل نوع (None = الميزان يرسل الوزن باستمرار بلا طلب)
PRESETS = {
    "بث مستمر (بلا أمر)": None,
    "A&D": b"Q\r\n",
    "Sartorius": b"\x1bP\r\n",
    "Mettler Toledo (SICS)": b"SI\r\n",
    "Ohaus": b"IP\r\n",
    "Kern": b"w",
}
DEFAULT_PRESET = "بث مستمر (بلا أمر)"

UNIT_TO_GRAM = {
    "g": 1.0, "gm": 1.0, "gr": 1.0, "grm": 1.0,
    "ct": 0.2, "kg": 1000.0, "mg": 0.001,
    "ozt": 31.1034768, "dwt": 1.55517384,
}

_WEIGHT_RE = re.compile(r"([+-])?\s*(\d+(?:[.,]\d+)?)\s*(ozt|dwt|grm|gm|gr|ct|kg|mg|g)?(?![a-z])", re.I)
# سطر بلا وحدة يُقبل فقط إن كان رقماً وحده (مع علامات الحالة): يمنع قراءة سطر
# تاريخ أو رقم تعريف في طباعة الميزان وزناً، ووضع العدّ بالقطعة (PCS)
_BARE_NUMBER_RE = re.compile(r"^(?:ST|US|S S|S D|SI|S|N|W|G|NET|GS)?[\s,:]*[+-]?\s*\d+(?:[.,]\d+)?\s*\??\s*$")
_ERROR_PREFIXES = ("OL", "-OL", "ERR", "E ", "EE", "OVER", "UNDER", "LOW")


def parse_weight(line):
    """سطر من الميزان ← {"grams", "stable", "unit"} أو None إن لم يكن سطر وزن.

    الإشارة السالبة تُحفظ (وزن بعد طرح وعاء أكبر)؛ والإدخال يرفضها.
    """
    text = (line or "").replace("\x00", "").strip()
    if not text:
        return None
    upper = text.upper()
    if upper.startswith(_ERROR_PREFIXES):
        return None
    # A&D: ST/US/OL في أول السطر، و Mettler SICS: «S S» مستقر و«S D» متحرّك
    unstable = (upper.startswith(("US", "S D", "SD ", "QT")) or "?" in text
                or upper.startswith("D "))
    for m in _WEIGHT_RE.finditer(text):
        if m.group(3) is None and not _BARE_NUMBER_RE.match(upper):
            return None
        sign, number, unit = m.group(1), m.group(2), (m.group(3) or "g").lower()
        try:
            value = float(number.replace(",", "."))
        except ValueError:
            continue
        grams = value * UNIT_TO_GRAM.get(unit, 1.0)
        if sign == "-":
            grams = -grams
        return {"grams": round(grams, 4), "stable": not unstable, "unit": unit}
    return None


def list_ports():
    """المنافذ المتاحة على الجهاز: [(الاسم، الوصف)]"""
    if not SERIAL_AVAILABLE:
        return []
    try:
        return [(p.device, p.description or p.device) for p in serial.tools.list_ports.comports()]
    except Exception:
        return []


class ScaleReader:
    """يقرأ الميزان في الخلفية ويحفظ آخر قراءة.

    ⚠️ لا يستدعي الواجهة إطلاقاً — الواجهة تقرأ current() من خيطها عبر after().
    opener: دالة فتح المنفذ (للاختبار بمنفذ وهمي)؛ الافتراضي serial.Serial.
    """

    def __init__(self, port, baudrate=DEFAULT_BAUD, request=None, interval=0.4, opener=None):
        self.port = port
        self.baudrate = int(baudrate or DEFAULT_BAUD)
        self.request = request
        self.interval = interval
        self._opener = opener
        self.latest = None          # {"grams", "stable", "unit", "at"}
        self.last_raw = ""
        self.error = None
        self.connected = False
        self._thread = None
        self._stop = threading.Event()

    # ------------------------------------------------------------ التشغيل
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="JadeiteScale", daemon=True)
        self._thread.start()

    def stop(self, timeout=2):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self.connected = False

    def _open(self):
        if self._opener is not None:
            return self._opener(self.port, self.baudrate)
        if not SERIAL_AVAILABLE:
            raise RuntimeError("مكتبة pyserial غير مثبّتة")
        return serial.Serial(self.port, self.baudrate, timeout=1)

    def _run(self):
        conn = None
        while not self._stop.is_set():
            try:
                if conn is None:
                    conn = self._open()
                    self.connected, self.error = True, None
                if self.request:
                    conn.write(self.request)
                raw = conn.readline()
                if raw:
                    self.feed(raw.decode("ascii", "ignore") if isinstance(raw, bytes) else str(raw))
                if self.request:
                    self._stop.wait(self.interval)
            except Exception as e:
                self.error = str(e) or type(e).__name__
                self.connected = False
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass
                conn = None
                self._stop.wait(RECONNECT_SECONDS)
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

    def feed(self, line):
        """سطر وصل من الميزان (يُستدعى من خيط القراءة، أو مباشرة في الاختبار)"""
        self.last_raw = line.strip()
        parsed = parse_weight(line)
        if parsed:
            parsed["at"] = time.time()
            self.latest = parsed
        return parsed

    # ------------------------------------------------------------ القراءة
    def current(self, max_age=FRESH_SECONDS):
        """آخر قراءة حديثة أو None (الميزان فُصل أو لم يرسل منذ مدة)"""
        r = self.latest
        if not r or time.time() - r["at"] > max_age:
            return None
        return r

    def status_text(self):
        """نص قصير لشريط الحالة"""
        r = self.current()
        if r:
            mark = "✓" if r["stable"] else "…"
            return f"⚖️ {r['grams']:.2f} جم {mark}"
        if self.error:
            return "⚖️ الميزان: غير متصل"
        return "⚖️ الميزان: بانتظار قراءة"
