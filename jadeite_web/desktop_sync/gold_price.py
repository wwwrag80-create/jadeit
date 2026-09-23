# -*- coding: utf-8 -*-
"""
جاديت — سعر الذهب العالمي اللحظي
=================================

يجلب سعر أونصة الذهب من الإنترنت ويحوّله لسعر الجرام حسب العيار.

مبادئ التصميم:
  ١) لا يوقف البرنامج أبداً: كل العمل في خيط خلفي، وأي فشل يُعرض كنص
     ولا يرمي استثناءً للواجهة.
  ٢) مصادر متعددة بالتتابع: لو سقط مصدر انتقل للتالي تلقائياً.
  ٣) صفر حزم خارجية: urllib فقط، فلا يكبر ملف exe.
  ٤) يحتفظ بآخر سعر معروف: عند انقطاع الإنترنت يظل يعرضه مع بيان وقته
     بدل أن يترك الشاشة فارغة.
  ٥) تراجع تلقائي عند الفشل المتكرر: بعض المصادر المجانية تحدّ عدد الطلبات،
     فبدل الاستمرار في الطَّرق كل ١٠ ثوانٍ نتباعد تدريجياً ثم نعود.

المعادلات (سعر الأونصة بالدولار → سعر الجرام):
    عيار ٢٤ = السعر × 161.2 / 1333.33
    عيار ٢١ = السعر × 141.05 / 1333.33
    عيار ١٨ = السعر × 121   / 1333.33
"""

import json
import threading
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------- الإعدادات
REFRESH_SECONDS = 10        # كما هو مطلوب: تحديث كل ١٠ ثوانٍ
HTTP_TIMEOUT = 8
MAX_BACKOFF = 300           # أقصى تباعد بعد فشل متكرر (٥ دقائق)

# علامة الاتجاه من اليسار لليمين: تُجبر الأرقام على الظهور بالصيغة
# الإنجليزية داخل النص العربي بدل الأرقام العربية الهندية
LTR = "\u200e"

DIVISOR = 1333.33
KARAT_FACTORS = {
    "٢٤": 161.2,
    "٢٢": 147.75,
    "٢١": 141.05,
    "١٨": 121.0,
}


def gram_price(ounce_usd, karat="١٨"):
    """سعر الجرام لعيار معيّن انطلاقاً من سعر الأونصة"""
    factor = KARAT_FACTORS.get(karat)
    if not ounce_usd or not factor:
        return 0.0
    return round(ounce_usd * factor / DIVISOR, 2)


# ---------------------------------------------------------------- المصادر
def _fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Jadeite-ERP/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _source_gold_api():
    """gold-api.com — مجاني بلا مفتاح"""
    data = _fetch_json("https://api.gold-api.com/price/XAU")
    price = data.get("price")
    return float(price) if price else None


def _source_metals_dev():
    """metals.dev — نسخة تجريبية مجانية"""
    data = _fetch_json("https://api.metals.dev/v1/latest?api_key=demo&currency=USD&unit=toz")
    return float(data["metals"]["gold"]) if data.get("metals", {}).get("gold") else None


def _source_exchangerate_fallback():
    """مصدر احتياطي: سعر XAU مقابل الدولار عبر أسعار الصرف"""
    data = _fetch_json("https://api.exchangerate.host/latest?base=XAU&symbols=USD")
    rate = (data.get("rates") or {}).get("USD")
    return float(rate) if rate else None


SOURCES = [
    ("gold-api", _source_gold_api),
    ("metals.dev", _source_metals_dev),
    ("exchangerate", _source_exchangerate_fallback),
]


def fetch_ounce_price():
    """يجرّب المصادر بالترتيب ويرجع (السعر، اسم المصدر) أو (None، سبب الفشل)"""
    errors = []
    for name, fn in SOURCES:
        try:
            price = fn()
            # فحص معقولية: أي رقم خارج هذا المدى يعني استجابة غير صحيحة
            # لا سعراً حقيقياً — عرضه سيضلّل المستخدم في تسعيره
            if price and 500 < price < 20000:
                return round(price, 2), name
            errors.append(f"{name}: قيمة غير منطقية")
        except urllib.error.HTTPError as e:
            errors.append(f"{name}: HTTP {e.code}")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
    return None, " | ".join(errors)


# ---------------------------------------------------------------- المراقب
class GoldPriceWatcher:
    """يحدّث سعر الذهب في الخلفية ويبلّغ الواجهة عبر رد نداء.

    ⚠️ رد النداء يُستدعى من خيط خلفي — مرّره عبر after(0, ...) قبل لمس الواجهة.
    """

    def __init__(self, on_update=None, refresh_seconds=REFRESH_SECONDS):
        self.on_update = on_update
        self.refresh_seconds = refresh_seconds

        self.ounce_price = None
        self.source = None
        self.updated_at = None
        self.last_error = None

        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._backoff = 0

    # ------------------------------------------------------------ التشغيل
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="JadeiteGoldPrice", daemon=True)
        self._thread.start()

    def stop(self, timeout=2):
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def refresh_now(self):
        self._backoff = 0
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            price, info = fetch_ounce_price()

            if price:
                self.ounce_price = price
                self.source = info
                self.updated_at = time.time()
                self.last_error = None
                self._backoff = 0
                wait = self.refresh_seconds
            else:
                self.last_error = info
                # تباعد تدريجي: يحمي من حظر المصادر المجانية عند تكرار الفشل
                self._backoff = min(MAX_BACKOFF, max(self.refresh_seconds, self._backoff * 2 or 20))
                wait = self._backoff

            if self.on_update:
                try:
                    self.on_update(self.snapshot())
                except Exception:
                    pass

            self._wake.wait(timeout=wait)
            self._wake.clear()

    # ------------------------------------------------------------ العرض
    def snapshot(self):
        return {
            "ounce": self.ounce_price,
            "source": self.source,
            "updated_at": self.updated_at,
            "error": self.last_error,
            "k24": gram_price(self.ounce_price, "٢٤"),
            "k22": gram_price(self.ounce_price, "٢٢"),
            "k21": gram_price(self.ounce_price, "٢١"),
            "k18": gram_price(self.ounce_price, "١٨"),
        }

    def display_text(self):
        """نص الشريط الجاهز للعرض"""
        s = self.snapshot()
        if not s["ounce"]:
            return "🥇 سعر الذهب: غير متاح — تحقق من الاتصال بالإنترنت"

        stamp = time.strftime("%H:%M:%S", time.localtime(s["updated_at"])) if s["updated_at"] else "—"
        # كل رقم مسبوق بعلامة LTR حتى يُعرض بالصيغة الإنجليزية (5)
        # لا العربية الهندية (٥) داخل النص العربي
        text = (f"🥇 الأونصة: {LTR}{s['ounce']:,.2f} $   |   "
                f"عيار {LTR}24: {LTR}{s['k24']:,.2f}   |   "
                f"عيار {LTR}22: {LTR}{s['k22']:,.2f}   |   "
                f"عيار {LTR}21: {LTR}{s['k21']:,.2f}   |   "
                f"عيار {LTR}18: {LTR}{s['k18']:,.2f}   |   ⏱ {LTR}{stamp}")

        # السعر معروض لكنه قديم: نوضّح ذلك بدل إيهام المستخدم بأنه لحظي
        if s["error"]:
            text += "   (آخر سعر معروف — تعذّر التحديث)"
        return text
