# -*- coding: utf-8 -*-
"""اختبار معادلات سعر الذهب ومنطق المراقب — يعمل بلا إنترنت"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gold_price as gp

assert gp.gram_price(2000, "\u0661\u0668") == round(2000 * 121 / 1333.33, 2) == 181.5
assert gp.gram_price(2000, "\u0662\u0664") == round(2000 * 161.2 / 1333.33, 2) == 241.8
print("\u2714 المعادلات مطابقة للمطلوب: عيار\u0661\u0668 = 181.5 | عيار\u0662\u0664 = 241.8 (أونصة 2000$)")

ratio = gp.gram_price(2000, "\u0661\u0668") / gp.gram_price(2000, "\u0662\u0664")
assert abs(ratio - 18 / 24) < 0.002
print("\u2714 النسبة بين العيارين متسقة مع نسبة النقاء")

assert gp.gram_price(None, "\u0661\u0668") == 0.0
assert gp.gram_price(2000, "\u0669\u0669") == 0.0
print("\u2714 القيم الناقصة والعيار المجهول لا تُسبب خطأ")

w = gp.GoldPriceWatcher()
assert "غير متاح" in w.display_text()
w.ounce_price, w.updated_at = 2650.55, time.time()
txt = w.display_text()
assert "2,650.55" in txt and "عيار \u200e18" in txt and "\u200e2,650.55" in txt
print("\u2714 نص الشريط سليم ويعرض كل العيارات بأرقام إنجليزية")
assert "\u0661\u0668" not in txt and "\u0662\u0664" not in txt
print("\u2714 لا توجد أرقام عربية هندية في الشريط إطلاقاً")

w.last_error = "لا اتصال"
assert "آخر سعر معروف" in w.display_text()
print("\u2714 عند الانقطاع: يبقى آخر سعر مع توضيح أنه ليس لحظياً")

prog, b = [], 0
for _ in range(5):
    b = min(gp.MAX_BACKOFF, max(gp.REFRESH_SECONDS, b * 2 or 20)); prog.append(b)
assert prog == [20, 40, 80, 160, 300]
print("\u2714 التراجع التدريجي عند الفشل: " + " \u2190 ".join(map(str, prog)) + " ثانية")

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gold_price.py"), encoding="utf-8").read()
assert not any(k in src for k in ("tkinter", "ctk.", "messagebox")) and "daemon=True" in src
print("\u2714 لا يلمس الواجهة إطلاقاً وخيطه daemon")
print("\n\u2705 كل اختبارات سعر الذهب نجحت")
