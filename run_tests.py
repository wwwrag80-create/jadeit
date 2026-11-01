#!/usr/bin/env python3
"""تشغيل كل الاختبارات: المحاسبية + طبقة الخادم، ثم اختبارات الواجهة في المتصفح إن توفر Playwright.

    python run_tests.py            ← الاختبارات المحاسبية واختبارات الخادم
    python run_tests.py --ui       ← إضافة اختبارات الواجهة (تحتاج Node.js و Playwright)

كل اختبار يستخدم قاعدة بيانات مؤقتة منفصلة تماماً عن بياناتك الحقيقية.
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    os.environ["JADEIT_QUIET"] = "1"
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    ok = result.wasSuccessful()
    if "--ui" in sys.argv:
        for script in ("ui_flow.js", "ui_admin.js", "ui_keyboard.js"):
            print(f"\n=== اختبار الواجهة: {script} ===")
            code = subprocess.call(["node", os.path.join(ROOT, "tests", "e2e", script)])
            ok = ok and code == 0
    print("\nالنتيجة النهائية:", "كل الاختبارات ناجحة ✔" if ok else "توجد اختبارات فاشلة ✘")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
