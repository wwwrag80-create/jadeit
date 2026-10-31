"""حساب عشري دقيق بأعداد صحيحة (Fixed-point).

كل الكميات في النظام (أوزان الذهب، أوزان الألماس، الأجور، أسعار الأجر)
تُخزَّن كأعداد صحيحة مضروبة في SCALE = 10_000 (أي بدقة 4 منازل عشرية).
بهذا لا يدخل أي رقم عشري ثنائي (float) في أي عملية حسابية أو تخزين،
فيستحيل ظهور أخطاء مثل 0.1 + 0.2 = 0.30000000000000004.

حدود الإدخال (عدد المنازل المسموح بها لكل نوع):
    الذهب: 4 منازل (جرام)
    الألماس: 3 منازل (قيراط افتراضياً)
    الأجور (مبالغ): منزلتان
    سعر الأجر للجرام: 3 منازل
"""
from __future__ import annotations

import re

SCALE = 10_000
SCALE_DP = 4

# المنازل العشرية المعتمدة لكل نوع
DP_GOLD = 4
DP_DIAMOND = 3
DP_WAGE = 2
DP_RATE = 3

MATERIAL_DP = {"gold": DP_GOLD, "diamond": DP_DIAMOND, "wage": DP_WAGE}

# حد أعلى منطقي يحمي من أخطاء الإدخال (مليار وحدة)
MAX_VALUE = 1_000_000_000 * SCALE

KARATS = (18, 21, 22, 24)

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_NUM_RE = re.compile(r"^(\d+)(?:\.(\d*))?$")


class FixedError(ValueError):
    """قيمة رقمية غير صالحة — الرسالة عربية جاهزة للعرض."""


def normalize_digits(text: str) -> str:
    return text.translate(_ARABIC_DIGITS)


def parse(value, dp: int, label: str = "القيمة", allow_zero: bool = True) -> int:
    """يحوّل نصاً عشرياً إلى عدد صحيح مضروب في SCALE دون أي تقريب.

    يرفض: القيم السالبة، الصيغ غير الرقمية، المنازل الزائدة عن dp، القيم الضخمة.
    يقبل الأرقام العربية الهندية (٠-٩) والفاصلة العشرية العربية (٫).
    """
    if value is None:
        text = ""
    elif isinstance(value, bool):
        raise FixedError(f"{label}: قيمة غير صالحة")
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        # لا نقبل float من الواجهة إطلاقاً لأن تمثيله الثنائي غير دقيق
        raise FixedError(f"{label}: يجب إرسال القيمة كنص عشري")
    else:
        text = str(value)
    text = normalize_digits(text.strip())
    if text == "":
        if allow_zero:
            return 0
        raise FixedError(f"{label}: الحقل مطلوب")
    if text.startswith("-"):
        raise FixedError(f"{label}: لا يُقبل رقم سالب")
    m = _NUM_RE.match(text)
    if not m:
        raise FixedError(f"{label}: «{value}» ليس رقماً صالحاً")
    whole, frac = m.group(1), (m.group(2) or "")
    frac = frac.rstrip("0") if len(frac) > dp else frac
    if len(frac) > dp:
        raise FixedError(f"{label}: الحد الأقصى {dp} منازل عشرية")
    frac = (frac + "0" * SCALE_DP)[:SCALE_DP]
    result = int(whole) * SCALE + int(frac)
    if result > MAX_VALUE:
        raise FixedError(f"{label}: القيمة أكبر من الحد المسموح")
    if not allow_zero and result == 0:
        raise FixedError(f"{label}: يجب أن تكون أكبر من صفر")
    return result


def round_div(numerator: int, denominator: int) -> int:
    """قسمة صحيحة مع تقريب نصف للأعلى (بعيداً عن الصفر) — ROUND_HALF_UP."""
    if denominator == 0:
        raise ZeroDivisionError("denominator")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    sign = -1 if numerator < 0 else 1
    q, r = divmod(abs(numerator), denominator)
    if r * 2 >= denominator:
        q += 1
    return sign * q


def quantize(value_e4: int, dp: int) -> int:
    """تقريب قيمة (بمقياس SCALE) إلى dp منازل، والنتيجة تبقى بمقياس SCALE."""
    if dp >= SCALE_DP:
        return value_e4
    step = 10 ** (SCALE_DP - dp)
    return round_div(value_e4, step) * step


def wage_total(gold_e4: int, rate_e4: int) -> int:
    """إجمالي الأجر = وزن الذهب × الأجر المعتمد لكل جرام، مقرّباً إلى منزلتين."""
    product_e8 = gold_e4 * rate_e4
    step = 10 ** (SCALE_DP + (SCALE_DP - DP_WAGE))  # من e8 إلى منزلتين
    return round_div(product_e8, step) * (10 ** (SCALE_DP - DP_WAGE))


def equivalent(actual_e4: int, actual_karat: int, working_karat: int) -> int:
    """الوزن المكافئ = الوزن الفعلي × عيار الذهب الفعلي ÷ عيار العمل المعتمد.

    مثال: 100 × 21 ÷ 18 = 116.6667 (يُقرَّب مرة واحدة إلى 4 منازل).
    """
    if actual_karat not in KARATS or working_karat not in KARATS:
        raise FixedError("العيار يجب أن يكون أحد: 18، 21، 22، 24")
    return round_div(actual_e4 * actual_karat, working_karat)


def fmt(value_e4: int, dp: int) -> str:
    """تنسيق نصي دقيق بعدد منازل ثابت (بدون فواصل آلاف)."""
    value_e4 = quantize(int(value_e4), dp)
    sign = "-" if value_e4 < 0 else ""
    v = abs(value_e4)
    whole, frac = divmod(v, SCALE)
    if dp == 0:
        return f"{sign}{whole}"
    frac_s = str(frac).rjust(SCALE_DP, "0")[:dp]
    return f"{sign}{whole}.{frac_s}"


def fmt_material(value_e4: int, material: str) -> str:
    return fmt(value_e4, MATERIAL_DP[material])


def fmt_rate(value_e4: int) -> str:
    """سعر الأجر: منزلتان على الأقل وثلاث عند الحاجة (5.50 ، 3.125)."""
    text = fmt(value_e4, DP_RATE)
    return text[:-1] if text.endswith("0") else text
