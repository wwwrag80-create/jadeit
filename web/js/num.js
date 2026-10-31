// حساب عشري دقيق في المتصفح باستخدام BigInt (نفس قواعد الخادم تماماً).
// يُستخدم للعرض الفوري أثناء الإدخال فقط؛ الخادم يعيد الحساب ويعتمد نتيجته عند الترحيل.

export const SCALE = 10000n;
export const DP = { gold: 4, diamond: 3, wage: 2, rate: 3 };
export const KARATS = [18, 21, 22, 24];

const ARABIC_DIGITS = { "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
  "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9", "٫": "." };

export function normalizeDigits(text) {
  return String(text ?? "").replace(/[٠-٩۰-۹٫]/g, (c) => ARABIC_DIGITS[c]);
}

/** يحلل نصاً عشرياً إلى BigInt بمقياس 10000. يعيد {ok, value, error, empty}. */
export function parse(text, dp) {
  const t = normalizeDigits(text).trim();
  if (t === "") return { ok: true, value: 0n, empty: true };
  if (t.startsWith("-")) return { ok: false, error: "لا يُقبل رقم سالب" };
  const m = /^(\d+)(?:\.(\d*))?$/.exec(t);
  if (!m) return { ok: false, error: "رقم غير صالح" };
  let frac = m[2] || "";
  if (frac.length > dp) frac = frac.replace(/0+$/, "");
  if (frac.length > dp) return { ok: false, error: `الحد الأقصى ${dp} منازل عشرية` };
  const value = BigInt(m[1]) * SCALE + BigInt((frac + "0000").slice(0, 4));
  return { ok: true, value, empty: false };
}

/** قسمة مع تقريب نصف للأعلى (بعيداً عن الصفر). */
export function roundDiv(n, d) {
  const neg = (n < 0n) !== (d < 0n);
  const an = n < 0n ? -n : n;
  const ad = d < 0n ? -d : d;
  let q = an / ad;
  const r = an % ad;
  if (r * 2n >= ad) q += 1n;
  return neg ? -q : q;
}

/** إجمالي الأجر = الذهب × الأجر، مقرّباً لمنزلتين. */
export function wageTotal(goldE4, rateE4) {
  return roundDiv(goldE4 * rateE4, 1000000n) * 100n;
}

/** الوزن المكافئ = الوزن الفعلي × العيار الفعلي ÷ عيار العمل. */
export function equivalent(actualE4, karat, workingKarat) {
  return roundDiv(actualE4 * BigInt(karat), BigInt(workingKarat));
}

/** تنسيق قيمة BigInt بعدد منازل ثابت مع فواصل الآلاف. */
export function fmt(e4, dp, group = true) {
  let v = BigInt(e4);
  if (dp < 4) v = roundDiv(v, 10n ** BigInt(4 - dp)) * 10n ** BigInt(4 - dp);
  const neg = v < 0n;
  if (neg) v = -v;
  const whole = (v / SCALE).toString();
  const frac = (v % SCALE).toString().padStart(4, "0").slice(0, dp);
  const w = group ? whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") : whole;
  return (neg ? "-" : "") + w + (dp > 0 ? "." + frac : "");
}

/** يحوّل نصاً عشرياً قادماً من الخادم (مثل "-12.5000") إلى BigInt بدقة كاملة. */
export function fromStr(s) {
  const t = String(s ?? "0").trim() || "0";
  const neg = t.startsWith("-");
  const r = parse(neg ? t.slice(1) : t, 4);
  if (!r.ok) return 0n;
  return neg ? -r.value : r.value;
}

/** إضافة فواصل الآلاف لنص عشري جاهز من الخادم دون أي تحويل رقمي. */
export function group(s) {
  if (s === null || s === undefined || s === "") return "";
  const t = String(s);
  if (!/^-?\d+(\.\d+)?$/.test(t)) return t; // ليس رقماً (تاريخ أو رقم مستند): يُعرض كما هو
  const neg = t.startsWith("-");
  const body = neg ? t.slice(1) : t;
  const [w, f] = body.split(".");
  const gw = w.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return (neg ? "-" : "") + gw + (f !== undefined ? "." + f : "");
}

export function isZeroStr(s) {
  return fromStr(s) === 0n;
}

/** تنسيق سعر الأجر: منزلتان على الأقل وثلاث عند الحاجة. */
export function fmtRate(e4) {
  const s = fmt(e4, 3);
  return s.endsWith("0") ? s.slice(0, -1) : s;
}

/** مرشّح لوحة المفاتيح لحقول الأرقام: يسمح بالأرقام والنقطة فقط. */
export function sanitizeTyping(text) {
  let t = normalizeDigits(text).replace(/[,،٬\s]/g, "").replace(/[^\d.]/g, "");
  const i = t.indexOf(".");
  if (i >= 0) t = t.slice(0, i + 1) + t.slice(i + 1).replace(/\./g, "");
  return t;
}
