# -*- coding: utf-8 -*-
"""
الدفعة الثالثة عشرة — الجزء الأول:
  • علم على مستوى النسخة (IS_ADMIN_BUILD) يجعل نسخة المدير سحابية بحتة
    في **كل** مسارات الدخول: انتحال الشخصية، وتسجيل الدخول بحساب العميل مباشرة.
  • رسالة أوضح عند تعذّر السحب، وتشخيص فوري لسبب 28000.

الاستخدام:  python3 patch_client_app_v20.py rageh-1-34-14-cloud.py
"""
import io
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(SRC, encoding="utf-8").read()


def rep(old, new, count=1):
    global src
    n = src.count(old)
    assert n == count, "MISMATCH (%d != %d):\n%s" % (n, count, old[:220])
    src = src.replace(old, new)


# ==========================================================================
#  ١) علم النسخة: يُضبط تلقائياً على False في نسخة العميل
# ==========================================================================
rep('''APP_VERSION = "1.36.0"''',
    '''APP_VERSION = "1.43.0"

# ══════════════════════════════════════════════════════════════════════════
#  نوع النسخة — يضبطه make_client_build.py تلقائياً
#
#  True  = نسخة المدير: سحابية بحتة. لا تعتمد على قاعدة الجهاز المحلية إطلاقاً،
#          بل تمسح النسخة المؤقتة وتسحب أحدث نسخة سحابية للعميل في كل دخول،
#          سواء بانتحال الشخصية أو بتسجيل الدخول بحساب العميل مباشرة.
#  False = نسخة العميل: تستعيد بياناتها المحلية أولاً ثم ترفعها للسحابة.
# ══════════════════════════════════════════════════════════════════════════
IS_ADMIN_BUILD = True''')


# ==========================================================================
#  ٢) نافذة التجهيز تحترم علم النسخة في كل مسار
# ==========================================================================
rep('''    def __init__(self, master, db_path, api, tenant_id, business_name):
        super().__init__(master)
        self.db_path = db_path''',
    '''    def __init__(self, master, db_path, api, tenant_id, business_name, cloud_only=None):
        super().__init__(master)
        # cloud_only: عند True تُمسح النسخة المحلية قبل السحب فتُعرض بيانات
        # السحابة وحدها. الافتراضي يتبع نوع النسخة (مدير = سحابي بحت).
        self.cloud_only = IS_ADMIN_BUILD if cloud_only is None else cloud_only
        self.db_path = db_path''')

rep('''    def _work(self):
        try:
            install_sync_schema(self.db_path)''',
    '''    def _work(self):
        try:
            # نسخة المدير: نبدأ من قاعدة نظيفة دائماً، فما يُعرض هو أحدث نسخة
            # سحابية للعميل حصراً — لا بقايا من جلسة سابقة على هذا الجهاز
            if self.cloud_only:
                self._progress("جارٍ تجهيز نسخة سحابية نظيفة…", 0.03)
                reset_local_cache(self.db_path)

            install_sync_schema(self.db_path)''')

rep('''            # (١) رفع ما لم يُرفع بعد
            uploader = CloudSync(db_path=self.db_path, api=self.api,
                                 tenant_id=self.tenant_id, app_version=APP_VERSION)
            pending = uploader.pending_count()
            if pending > 0:''',
    '''            # (١) رفع ما لم يُرفع بعد — يُتخطّى في نسخة المدير لأن قاعدتها
            # مُسحت للتو، فلا يوجد ما يُرفع، ورفع نسخة فارغة قد يطمس بيانات العميل
            uploader = CloudSync(db_path=self.db_path, api=self.api,
                                 tenant_id=self.tenant_id, app_version=APP_VERSION)
            pending = 0 if self.cloud_only else uploader.pending_count()
            if pending > 0:''')


# ==========================================================================
#  ٣) دالة مسح النسخة المحلية على مستوى الوحدة (تُستخدم من كل المسارات)
# ==========================================================================
rep('''def migrate_legacy_file(filename, target_path):''',
    '''def reset_local_cache(db_path):
    """يمسح النسخة المحلية المؤقتة قبل السحب من السحابة (نسخة المدير فقط).

    الخطر الذي يمنعه: السحب دمج لا استبدال، فلو بقيت نسخة قديمة على جهاز
    المدير لظهرت له حركة حذفها العميل فعلياً، وقد يبني عليها قراراً محاسبياً.
    الحذف آمن هنا: هذه القاعدة ذاكرة عرض مؤقتة، ومصدر الحقيقة السحابة وجهاز
    العميل — لا تُحذف بيانات أحد.
    """
    for suffix in ("", "-journal", "-wal", "-shm"):
        path = db_path + suffix
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            log_cloud_error("تعذّر تنظيف النسخة المؤقتة", e)


def migrate_legacy_file(filename, target_path):''')

# إزالة النسخة المكررة داخل الكلاس واستخدام دالة الوحدة
rep('''    @staticmethod
    def reset_admin_local_cache(db_path):
        """يمسح النسخة المحلية المؤقتة على جهاز المدير قبل السحب من السحابة.

        الخطر الذي يمنعه: لو بقيت نسخة قديمة، فقد يرى المدير حركة حذفها العميل
        فعلياً (لأن السحب دمج لا استبدال)، فيتخذ قراراً محاسبياً على رقم خاطئ.
        الحذف آمن تماماً هنا: هذه القاعدة مجرد ذاكرة عرض مؤقتة على جهاز المدير،
        ومصدر الحقيقة هو السحابة وجهاز العميل — لا تُحذف بيانات أحد.
        """
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = db_path + suffix
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                log_cloud_error("تعذّر تنظيف النسخة المؤقتة على جهاز المدير", e)

''', '''''')

rep('''                if getattr(self, "ADMIN_CLOUD_ONLY", True):
                    self.reset_admin_local_cache(db_path)

                api = _RpcBridge(sb_admin, CURRENT_SYNC_TOKEN)''',
    '''                api = _RpcBridge(sb_admin, CURRENT_SYNC_TOKEN)''')


# ==========================================================================
#  ٤) رسالة أوضح عند فشل التجهيز + تشخيص سبب 28000
# ==========================================================================
rep('''                    if win.error:
                        messagebox.showwarning(
                            "تنبيه المزامنة",
                            f"تعذّر تجهيز البيانات من السحابة:\\n{win.error}\\n\\n"
                            "سيفتح النظام ببياناتك المحفوظة على هذا الجهاز، "
                            "وستُرفع أي حركات جديدة تلقائياً عند عودة الاتصال.")''',
    '''                    if win.error:
                        messagebox.showwarning("تنبيه المزامنة", sync_error_message(win.error))''')

rep('''def reset_local_cache(db_path):''',
    '''def sync_error_message(raw_error):
    """يحوّل خطأ المزامنة إلى رسالة تقول للمستخدم ماذا يفعل بالضبط"""
    text = str(raw_error)

    if "28000" in text or "غير مصرّح بالمزامنة" in text or "غير مصرح بالمزامنة" in text:
        return ("تعذّر تجهيز البيانات من السحابة: هذا الحساب غير مربوط بالمزامنة بعد.\\n\\n"
                "الحل (مرة واحدة): افتح Supabase ← SQL Editor وشغّل الملفين:\\n"
                "   11_fix_sync_permissions.sql\\n"
                "   12_fix_pull_token.sql\\n\\n"
                "سيفتح النظام الآن ببياناتك المحفوظة على هذا الجهاز، ولن تفقد شيئاً.")

    if any(k in text for k in ("اتصال", "الإنترنت", "urlopen", "timed out", "Connection")):
        return ("تعذّر الاتصال بالسحابة — تحقق من الإنترنت.\\n\\n"
                "سيفتح النظام ببياناتك المحفوظة على هذا الجهاز، "
                "وستُرفع أي حركات جديدة تلقائياً عند عودة الاتصال.")

    return (f"تعذّر تجهيز البيانات من السحابة:\\n{text}\\n\\n"
            "سيفتح النظام ببياناتك المحفوظة على هذا الجهاز، "
            "وستُرفع أي حركات جديدة تلقائياً عند عودة الاتصال.")


def reset_local_cache(db_path):''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة الثالثة عشرة على:", SRC)
