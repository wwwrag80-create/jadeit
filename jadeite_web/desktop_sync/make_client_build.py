# -*- coding: utf-8 -*-
"""
يولّد نسخة العميل الآمنة: نفس البرنامج بعد إزالة المفتاح السري ولوحة المدير.

لماذا هذا ضروري:
  ملف exe الذي يُسلَّم للعميل يمكن فكّه واستخراج ما بداخله. والمفتاح السري
  (service_role) يتخطى كل سياسات الحماية ويعطي حامله وصولاً كاملاً لبيانات
  **كل** عملائك. وجوده في نسخة العميل خطر حقيقي لا احتمالي.

الاستخدام:  python3 make_client_build.py
الناتج:     rageh-CLIENT.py   ← هذا ما تبنيه exe وتسلّمه للعملاء
"""
import io
import re

SRC = "rageh-1-34-14-cloud.py"
OUT = "rageh-CLIENT.py"

src = io.open(SRC, encoding="utf-8").read()

# ---------- ١) إزالة المفتاح السري ----------
before = re.search(r'SUPABASE_SECRET_KEY\s*=\s*"([^"]*)"', src)
src = re.sub(
    r'SUPABASE_SECRET_KEY\s*=\s*"[^"]*"',
    'SUPABASE_SECRET_KEY = ""   # مُزال عمداً من نسخة العميل (يتخطى كل الحمايات)',
    src)

# ---------- ١-ب) ضبط نوع النسخة: العميل يستعيد بياناته المحلية ----------
assert 'IS_ADMIN_BUILD = True' in src, "علم نوع النسخة غير موجود — راجع السكربت"
src = src.replace('IS_ADMIN_BUILD = True',
                  'IS_ADMIN_BUILD = False   # نسخة العميل: تستعيد بياناتها المحلية ثم ترفعها')

# ---------- ٢) تعطيل دخول لوحة المدير من نسخة العميل ----------
old_admin = '''        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            self.destroy()
            panel = AdminPanel()
            panel.mainloop()
            return'''
new_admin = '''        # لوحة المدير غير متاحة في نسخة العميل — تُدار من لوحة الويب
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            self.btn_login.configure(state="normal", text="دخول")
            self.lbl_status.configure(text="هذه النسخة مخصصة للعملاء فقط")
            return'''
assert src.count(old_admin) == 1, "بنية دخول المدير تغيّرت — راجع السكربت"
src = src.replace(old_admin, new_admin)

io.open(OUT, "w", encoding="utf-8").write(src)

# ---------- التحقق ----------
check = io.open(OUT, encoding="utf-8").read()
key = re.search(r'SUPABASE_SECRET_KEY\s*=\s*"([^"]*)"', check)
assert key and key.group(1) == "", "لم يُزل المفتاح السري!"
assert "IS_ADMIN_BUILD = False" in check, "نسخة العميل ما زالت مضبوطة كنسخة مدير!"
if before and before.group(1):
    assert before.group(1) not in check, "بقيت نسخة أخرى من المفتاح السري في الملف!"

import ast
ast.parse(check)

print(f"✔ تم إنشاء {OUT}")
print("✔ المفتاح السري مُزال بالكامل")
print("✔ لوحة المدير معطّلة في نسخة العميل")
print("✔ نوع النسخة: عميل — تستعيد بياناتها المحلية ثم ترفعها")
print(f"\nالبناء:\n  pyinstaller --onefile --noconsole ^\n"
      f"    --add-data \"cloud_sync.py;.\" --add-data \"sync_down.py;.\" ^\n"
      f"    --add-data \"supabase_api.py;.\" ^\n    --add-data \"gold_price.py;.\" --add-data \"jadeite.ico;.\" --add-data \"jadeite_logo.png;.\" ^\n    --icon \"jadeite.ico\" {OUT}")
