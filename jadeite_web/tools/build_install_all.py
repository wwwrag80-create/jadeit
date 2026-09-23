# -*- coding: utf-8 -*-
"""يولّد supabase/INSTALL_ALL.sql من الملفات المرقّمة بالترتيب.

الملفات المرقّمة هي المصدر الوحيد للحقيقة — لا تعدّل INSTALL_ALL.sql يدوياً،
بل عدّل الملف المرقّم ثم شغّل:

    python3 tools/build_install_all.py          # يعيد توليد الملف
    python3 tools/build_install_all.py --check  # يفشل إن كان الملف غير محدَّث (لـ CI)

لا يُضمَّن 00_repair_auth.sql و 01_create_admin.sql لأنهما يُشغَّلان منفصلَين
(الأول عند عطل المصادقة فقط، والثاني بعد إنشاء مستخدم المدير).
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(ROOT, "supabase")
TARGET = os.path.join(SQL_DIR, "INSTALL_ALL.sql")

# ملفات تُشغَّل منفصلة ولا تدخل في التثبيت الموحّد
EXCLUDED = {"00_repair_auth.sql", "01_create_admin.sql"}

HEADER = """-- ============================================================================
--  جاديت ERP — ملف التثبيت الكامل (شغّله مرة واحدة)
--  Supabase → SQL Editor → New query → الصق كل المحتوى → Run
--
--  يشمل: الجداول + سياسات الحماية + دوال الحسابات + التهيئة + الموديولات
--         + طبقة المزامنة الهجينة مع برامج سطح المكتب
--
--  آمن ويمكن إعادة تشغيله أكثر من مرة (idempotent) بدون فقدان بيانات.
--
--  ⚠️ إن ظهر خطأ 500 "Database error querying schema" عند الدخول،
--     شغّل أولاً الملف: 00_repair_auth.sql
--
--  ⚙️ هذا الملف مُولَّد آلياً من الملفات المرقّمة (tools/build_install_all.py)
--     — عدّل الملف المرقّم لا هذا الملف.
-- ============================================================================

set client_min_messages = warning;

"""

FOOTER = """
notify pgrst, 'reload schema';
select 'التثبيت اكتمل ✔' as الحالة;
"""

SEPARATOR = (
    "-- " + "#" * 76 + "\n"
    "-- ##  المصدر: {name}\n"
    "-- " + "#" * 76 + "\n\n"
)


def section_files():
    names = [
        f for f in os.listdir(SQL_DIR)
        if re.match(r"^\d{2}_.+\.sql$", f) and f not in EXCLUDED
    ]
    return sorted(names)


def build():
    parts = [HEADER]
    for name in section_files():
        body = io.open(os.path.join(SQL_DIR, name), encoding="utf-8").read().strip("\n")
        parts.append("\n" + SEPARATOR.format(name=name) + body + "\n\n")
    parts.append(FOOTER)
    return "".join(parts)


def main():
    content = build()
    if "--check" in sys.argv:
        current = io.open(TARGET, encoding="utf-8").read() if os.path.exists(TARGET) else ""
        if current != content:
            print("✘ INSTALL_ALL.sql غير محدَّث — شغّل: python3 tools/build_install_all.py")
            sys.exit(1)
        print("✔ INSTALL_ALL.sql مطابق للملفات المرقّمة")
        return
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(content)
    print(f"✔ تم توليد INSTALL_ALL.sql من {len(section_files())} ملفاً")


if __name__ == "__main__":
    main()
