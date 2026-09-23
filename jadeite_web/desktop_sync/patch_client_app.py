# -*- coding: utf-8 -*-
"""
يعدّل نسخة العميل (rageh) لتعمل بالمعمارية الجديدة:
  • حذف ملف الجلسة device_session.json نهائياً
  • بعد تسجيل الدخول: سحب بيانات المصنع من السحابة إلى SQLite المحلية
  • تشغيل محرك رفع خلفي صامت داخل البرنامج

الاستخدام:  python3 patch_client_app.py rageh-1-34-14.py
"""
import io
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14.py"
OUT = SRC.replace(".py", "-cloud.py")

src = io.open(SRC, encoding="utf-8").read()


def rep(old, new, count=1):
    global src
    n = src.count(old)
    assert n == count, "MISMATCH (%d != %d):\n%s" % (n, count, old[:200])
    src = src.replace(old, new)


# ==========================================================================
#  ١) حذف ملف الجلسة نهائياً
# ==========================================================================
rep('DEVICE_SESSION_FILE = os.path.join(APP_DATA_DIR, "device_session.json")',
    '# (أُلغي ملف الجلسة نهائياً — لا يُخزَّن أي سر على القرص)')

# حذف دالتي الحفظ والقراءة
start = src.index("def save_device_session(")
end = src.index("# ================= نهاية وحدة الربط بالسحابة =================")
src = src[:start] + """# ملاحظة معمارية: أُلغيت دوال حفظ/قراءة جلسة الجهاز.
# البرنامج الآن يطلب تسجيل الدخول في كل تشغيل، ويحتفظ ببيانات الجلسة
# (معرّف المصنع ورمز المزامنة) في الذاكرة فقط، فتختفي بإغلاق البرنامج.


""" + src[end:]

# أي استدعاء متبقٍ للجلسة
src = re.sub(r"^\s*(save|load)_device_session\([^\)]*\)\s*$", "", src, flags=re.M)
src = src.replace('migrate_legacy_file("device_session.json", DEVICE_SESSION_FILE)', "")


# ==========================================================================
#  ٢) استيراد وحدات المزامنة
# ==========================================================================
rep('''ADMIN_USERNAME = "admin"''',
    '''# ================= وحدات المزامنة السحابية =================
try:
    from cloud_sync import CloudSync, install_sync_schema
    from sync_down import sync_down
    SYNC_AVAILABLE = True
except Exception as _sync_err:      # noqa: F841
    # غياب وحدات المزامنة لا يمنع البرنامج من العمل محلياً
    CloudSync = None
    install_sync_schema = None
    sync_down = None
    SYNC_AVAILABLE = False


class _RpcBridge:
    """يمرّر استدعاءات المزامنة لعميل Supabase الموجود أصلاً في البرنامج،
    ويحقن رمز المزامنة المحفوظ في الذاكرة (بدون أي ملف على القرص)."""

    def __init__(self, sb_client, sync_token=None):
        self._sb = sb_client
        self.sync_token = sync_token

    def rpc(self, name, payload=None):
        params = dict(payload or {})
        if "p_token" in params and params["p_token"] is None:
            params["p_token"] = self.sync_token
        res = self._sb.rpc(name, params).execute()
        return res.data


ADMIN_USERNAME = "admin"''')


# ==========================================================================
#  ٣) الدخول يجلب رمز المزامنة أيضاً (استجابة واحدة، بلا ملفات)
# ==========================================================================
rep('''        res = sb.rpc("verify_client_login", {"p_username": username, "p_password_hash": hash_password(password)}).execute()
        if res.data:
            row = res.data[0]
            client_id = row.get("out_client_id")''',
    '''        # نجرّب أولاً الدالة الموسّعة التي ترجع رمز المزامنة معها،
        # ونرجع للقديمة تلقائياً لو لم تكن مثبّتة في السحابة بعد
        try:
            res = sb.rpc("client_login_full", {"p_username": username, "p_password_hash": hash_password(password)}).execute()
        except Exception:
            res = sb.rpc("verify_client_login", {"p_username": username, "p_password_hash": hash_password(password)}).execute()

        if res.data:
            row = res.data[0]
            client_id = row.get("out_client_id")
            # رمز المزامنة يبقى في الذاكرة فقط طوال تشغيل البرنامج
            global CURRENT_SYNC_TOKEN
            CURRENT_SYNC_TOKEN = row.get("out_sync_token")''')

rep('''def cloud_verify_client_login(username, password):''',
    '''CURRENT_SYNC_TOKEN = None   # رمز مزامنة الجلسة الحالية (ذاكرة فقط)


def cloud_verify_client_login(username, password):''')


# ==========================================================================
#  ٤) شاشة تجهيز البيانات: تُعرض بين الدخول وفتح النظام
# ==========================================================================
rep('''class LoginWindow(ctk.CTk):''',
    '''class SyncDownWindow(ctk.CTkToplevel):
    """شاشة تجهيز بيانات المصنع: ترفع ما لم يُرفع ثم تسحب نسخة السحابة.

    الترتيب مقصود: الرفع قبل السحب دائماً — لو عمل العميل أسبوعاً بلا إنترنت
    فحركاته المتراكمة تُرفع أولاً، وإلا طمستها نسخة السحابة الأقدم.
    """

    def __init__(self, master, db_path, api, tenant_id, business_name):
        super().__init__(master)
        self.db_path = db_path
        self.api = api
        self.tenant_id = tenant_id
        self.ok = False
        self.error = None

        self.title("تجهيز بيانات المصنع")
        self.geometry("480x260")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)   # لا يُغلق أثناء التجهيز

        ctk.CTkLabel(self, text="💎 جاديت", font=("Cairo", 26, "bold"),
                     text_color="#d4af37").pack(pady=(28, 2))
        ctk.CTkLabel(self, text=business_name or "", font=("Cairo", 15, "bold")).pack()

        self.lbl = ctk.CTkLabel(self, text="جارٍ الاتصال بالسحابة…",
                                font=("Cairo", 13), text_color="#d4af37",
                                wraplength=420, justify="center")
        self.lbl.pack(pady=(18, 8))

        self.bar = ctk.CTkProgressBar(self, width=380, height=10, progress_color="#d4af37")
        self.bar.set(0)
        self.bar.pack(pady=6)

        ctk.CTkLabel(self, text="لا تغلق البرنامج أثناء التجهيز",
                     font=("Cairo", 11), text_color="#7f858c").pack(pady=(10, 0))

        threading.Thread(target=self._work, daemon=True).start()

    def _ui(self, fn):
        """كل تحديث للواجهة يمر من هنا — استدعاء Tkinter من خيط آخر يُسقط البرنامج"""
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _progress(self, text, ratio=None):
        def apply():
            self.lbl.configure(text=text)
            if ratio is not None:
                self.bar.set(max(0.0, min(1.0, ratio)))
        self._ui(apply)

    def _work(self):
        try:
            install_sync_schema(self.db_path)

            # (١) رفع ما لم يُرفع بعد
            uploader = CloudSync(db_path=self.db_path, api=self.api,
                                 tenant_id=self.tenant_id, app_version=APP_VERSION)
            pending = uploader.pending_count()
            if pending > 0:
                self._progress(f"جارٍ رفع {pending} حركة لم تُرفع بعد…", 0.08)
                uploader.flush(max_batches=300)

            # (٢) سحب نسخة السحابة ودمجها محلياً
            sync_down(self.db_path, self.api, self.tenant_id,
                      on_progress=lambda t, r: self._progress(t, r))
            self.ok = True

        except Exception as e:
            # فشل التجهيز لا يمنع العمل: البيانات المحلية سليمة والمزامنة تعيد المحاولة
            self.error = str(e)

        self._ui(self.destroy)


class LoginWindow(ctk.CTk):''')


# ==========================================================================
#  ٥) بعد الدخول: تجهيز البيانات ثم فتح النظام
# ==========================================================================
rep('''        client_id, business_name, can_edit = cloud_verify_client_login(username, password)
        if client_id:
            self.destroy()
            app = GoldSystemApp(client_id=client_id, client_name=business_name, supabase_client=get_supabase_public_client(), initial_can_edit=can_edit)
            app.mainloop()''',
    '''        client_id, business_name, can_edit = cloud_verify_client_login(username, password)
        if client_id:
            # تجهيز بيانات المصنع من السحابة قبل فتح النظام
            if SYNC_AVAILABLE and CURRENT_SYNC_TOKEN:
                try:
                    db_path = os.path.join(DATA_DIR, f"client_data_{client_id}.db")
                    api = _RpcBridge(get_supabase_public_client(), CURRENT_SYNC_TOKEN)
                    win = SyncDownWindow(self, db_path, api, client_id, business_name)
                    self.wait_window(win)
                    if win.error:
                        messagebox.showwarning(
                            "تنبيه المزامنة",
                            f"تعذّر تجهيز البيانات من السحابة:\\n{win.error}\\n\\n"
                            "سيفتح النظام ببياناتك المحفوظة على هذا الجهاز، "
                            "وستُرفع أي حركات جديدة تلقائياً عند عودة الاتصال.")
                except Exception as e:
                    log_cloud_error("تعذّر تجهيز البيانات من السحابة", e)

            self.destroy()
            app = GoldSystemApp(client_id=client_id, client_name=business_name, supabase_client=get_supabase_public_client(), initial_can_edit=can_edit)
            app.mainloop()''')


# ==========================================================================
#  ٦) تشغيل محرك الرفع الخلفي داخل النظام
# ==========================================================================
rep('''        self.build_home_screen()
        self.show_home_screen()
        self.update_edit_status_ui()''',
    '''        self.build_home_screen()
        self.show_home_screen()
        self.update_edit_status_ui()
        self.start_cloud_sync_engine()

    def start_cloud_sync_engine(self):
        """يشغّل محرك الرفع الخلفي. فشله لا يؤثر على عمل البرنامج محلياً إطلاقاً."""
        self.cloud_sync = None
        if not (SYNC_AVAILABLE and self.client_id and CURRENT_SYNC_TOKEN):
            return
        try:
            api = _RpcBridge(self.supabase or get_supabase_public_client(), CURRENT_SYNC_TOKEN)
            self.cloud_sync = CloudSync(
                db_path=self.db_path,
                api=api,
                tenant_id=self.client_id,
                app_version=APP_VERSION,
                on_status=self._on_sync_status,
            )
            self.cloud_sync.start()
        except Exception as e:
            log_cloud_error("تعذّر تشغيل محرك المزامنة", e)

    def _on_sync_status(self, text):
        """تُستدعى من الخيط الخلفي — نمرّرها لخيط الواجهة عبر after"""
        try:
            self.after(0, lambda: self.lbl_cloud_sync.configure(text=text))
        except Exception:
            pass''')

# إيقاف المحرك عند الإغلاق
rep('''    def on_app_closing(self):''',
    '''    def on_app_closing(self):
        try:
            if getattr(self, 'cloud_sync', None):
                self.cloud_sync.stop()
        except Exception:
            pass''')

# رفع فوري بعد كل إعادة حساب (ترحيل/تعديل/حذف)
rep('''        if hasattr(self, 'sales_ops_table_frame'):
            self.refresh_sales_ops_table()''',
    '''        if hasattr(self, 'sales_ops_table_frame'):
            self.refresh_sales_ops_table()
        if getattr(self, 'cloud_sync', None):
            self.cloud_sync.sync_now()''')

# رقم الإصدار
rep('''ADMIN_PASSWORD = "admin"''', '''ADMIN_PASSWORD = "admin"
APP_VERSION = "1.35.0"''')

io.open(OUT, "w", encoding="utf-8").write(src)
print(f"تم إنشاء: {OUT}")
