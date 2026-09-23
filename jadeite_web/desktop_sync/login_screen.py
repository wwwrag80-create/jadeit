# -*- coding: utf-8 -*-
"""
جاديت — شاشة تسجيل الدخول الإجبارية لبرنامج سطح المكتب
========================================================

تظهر عند كل فتح للبرنامج. لا يوجد أي ملف جلسة على القرص.

التسلسل:
    دخول بالبريد وكلمة المرور  →  التحقق من Supabase  →  معرفة المصنع
    →  رفع ما لم يُرفع بعد  →  سحب بيانات المصنع  →  فتح النظام

الاستخدام في البرنامج الرئيسي:

    from login_screen import require_login

    session = require_login(app_version="1.34.14")
    if session is None:
        sys.exit(0)                      # المستخدم أغلق الشاشة

    app = GoldSystemApp(
        db_path=session["db_path"],
        api=session["api"],
        tenant_id=session["tenant_id"],
        business_name=session["business_name"],
        can_edit=session["can_edit"],
    )
    app.mainloop()
"""

import os
import threading
import tkinter as tk

import customtkinter as ctk

from supabase_api import AuthError, NetworkError, SupabaseAPI
from sync_down import sync_down, tenant_db_path

# مجلد بيانات النظام على القرص المحلي (نفس مجلد النسخة الحالية)
DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "JadeiteERP", "Data",
)

GOLD = "#d4af37"
DARK = "#13161a"
CARD = "#1c2026"


class LoginScreen(ctk.CTk):
    """نافذة الدخول: تُرجع الجلسة عبر self.result بعد نجاح كل المراحل."""

    def __init__(self, app_version="", data_dir=None, api=None):
        super().__init__()

        self.app_version = app_version
        self.data_dir = data_dir or DATA_DIR
        self.api = api or SupabaseAPI()
        self.result = None
        self._busy = False

        ctk.set_appearance_mode("dark")
        self.title("جاديت — تسجيل الدخول")
        self.geometry("520x600")
        self.resizable(False, False)
        self.configure(fg_color=DARK)
        self._center()

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.entry_email.focus_set()

    # ------------------------------------------------------------- الواجهة
    def _center(self):
        self.update_idletasks()
        w, h = 520, 600
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=18)
        card.pack(expand=True, fill="both", padx=30, pady=30)

        ctk.CTkLabel(card, text="💎", font=("Cairo", 46)).pack(pady=(28, 4))
        ctk.CTkLabel(card, text="جاديت", font=("Cairo", 30, "bold"),
                     text_color=GOLD).pack()
        ctk.CTkLabel(card, text="نظام إدارة مصانع الذهب", font=("Cairo", 14),
                     text_color="#9aa0a6").pack(pady=(2, 22))

        # ---- البريد ----
        ctk.CTkLabel(card, text="البريد الإلكتروني", font=("Cairo", 13, "bold"),
                     anchor="e").pack(fill="x", padx=38, pady=(0, 4))
        self.entry_email = ctk.CTkEntry(
            card, height=42, font=("Cairo", 14), justify="right",
            placeholder_text="name@factory.com")
        self.entry_email.pack(fill="x", padx=38)

        # ---- كلمة المرور ----
        ctk.CTkLabel(card, text="كلمة المرور", font=("Cairo", 13, "bold"),
                     anchor="e").pack(fill="x", padx=38, pady=(14, 4))

        pwd_row = ctk.CTkFrame(card, fg_color="transparent")
        pwd_row.pack(fill="x", padx=38)

        self.entry_pass = ctk.CTkEntry(
            pwd_row, height=42, font=("Cairo", 14), justify="right", show="●")
        self.entry_pass.pack(side="right", fill="x", expand=True)

        self._show_pass = False
        self.btn_eye = ctk.CTkButton(
            pwd_row, text="👁", width=42, height=42, fg_color="#2a2f36",
            hover_color="#3a4048", command=self._toggle_password)
        self.btn_eye.pack(side="left", padx=(6, 0))

        # ---- الرسالة ----
        self.lbl_msg = ctk.CTkLabel(
            card, text="", font=("Cairo", 12, "bold"), text_color="#e74c3c",
            wraplength=400, justify="right")
        self.lbl_msg.pack(fill="x", padx=38, pady=(14, 0))

        # ---- شريط التقدّم ----
        self.progress = ctk.CTkProgressBar(card, height=8, progress_color=GOLD)
        self.progress.set(0)

        # ---- زر الدخول ----
        self.btn_login = ctk.CTkButton(
            card, text="دخول", height=46, font=("Cairo", 17, "bold"),
            fg_color=GOLD, hover_color="#b8941f", text_color="#000000",
            command=self._on_login)
        self.btn_login.pack(fill="x", padx=38, pady=(18, 6))

        ctk.CTkLabel(
            card,
            text="بياناتك محفوظة في حسابك السحابي — سجّل دخولك من أي جهاز\n"
                 "وسيجهّز البرنامج نسخة مصنعك تلقائياً",
            font=("Cairo", 11), text_color="#7f858c", justify="center",
        ).pack(pady=(6, 0))

        ctk.CTkLabel(card, text=f"الإصدار {self.app_version}", font=("Cairo", 10),
                     text_color="#585d63").pack(side="bottom", pady=10)

        self.bind("<Return>", lambda _e: self._on_login())

    def _toggle_password(self):
        self._show_pass = not self._show_pass
        self.entry_pass.configure(show="" if self._show_pass else "●")

    # ------------------------------------------------------------ المساعدات
    def _msg(self, text, color="#e74c3c"):
        self.lbl_msg.configure(text=text, text_color=color)

    def _set_busy(self, busy, label="جارٍ التحقق…"):
        self._busy = busy
        self.btn_login.configure(state="disabled" if busy else "normal",
                                 text=label if busy else "دخول")
        self.entry_email.configure(state="disabled" if busy else "normal")
        self.entry_pass.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.pack(fill="x", padx=38, pady=(12, 0))
            self.progress.set(0)
        else:
            self.progress.pack_forget()

    def _on_close(self):
        if self._busy:
            # الإغلاق أثناء السحب يترك القاعدة ناقصة — نمنعه ونوضّح السبب
            self._msg("جارٍ تجهيز بيانات مصنعك… الرجاء الانتظار حتى الاكتمال.", "#f39c12")
            return
        self.result = None
        self.destroy()

    # -------------------------------------------------------------- الدخول
    def _on_login(self):
        if self._busy:
            return

        email = self.entry_email.get().strip()
        password = self.entry_pass.get()

        if not email or not password:
            self._msg("الرجاء إدخال البريد الإلكتروني وكلمة المرور.")
            return

        self._msg("")
        self._set_busy(True)

        # كل الاتصال في خيط منفصل حتى لا تتجمّد النافذة
        threading.Thread(
            target=self._login_worker, args=(email, password), daemon=True
        ).start()

    def _login_worker(self, email, password):
        try:
            # ---------- ١) التحقق من الحساب ----------
            self._ui(lambda: self._progress("جارٍ التحقق من الحساب…", 0.05))
            session = self.api.sign_in(email, password)

            tenant_id = session["tenant_id"]
            db_path = tenant_db_path(self.data_dir, tenant_id)

            self._ui(lambda: self._progress(
                f"مرحباً — {session['business_name']}", 0.12))

            # ---------- ٢) رفع ما لم يُرفع بعد (قبل السحب دائماً) ----------
            from cloud_sync import CloudSync, install_sync_schema
            install_sync_schema(db_path)

            uploader = CloudSync(db_path=db_path, api=self.api,
                                 tenant_id=tenant_id, app_version=self.app_version)
            pending = uploader.pending_count()
            if pending > 0:
                self._ui(lambda: self._progress(
                    f"جارٍ رفع {pending} حركة لم تُرفع بعد…", 0.16))
                uploader.flush(max_batches=200)

            # ---------- ٣) سحب بيانات المصنع ----------
            stats = sync_down(
                db_path, self.api, tenant_id,
                on_progress=lambda text, ratio: self._ui(
                    lambda t=text, r=ratio: self._progress(t, r)),
            )

            # ---------- ٤) تسليم الجلسة للبرنامج الرئيسي ----------
            self.result = {
                "api": self.api,
                "db_path": db_path,
                "tenant_id": tenant_id,
                "business_name": session["business_name"],
                "role": session["role"],
                "can_edit": session["can_edit"],
                "email": email,
                "stats": stats,
            }
            self._ui(self._finish)

        # الرسالة تُحفظ في متغيّر قبل تمريرها: بايثون يحذف `e` بنهاية كتلة except،
        # والدالة تُنفَّذ لاحقاً في خيط الواجهة — فكانت ترمي NameError وتعلق الشاشة
        except (AuthError, NetworkError) as e:
            msg = str(e)
            self._ui(lambda: self._fail(msg))
        except Exception as e:
            msg = f"تعذّر إكمال الدخول:\n{e}"
            self._ui(lambda: self._fail(msg))

    # -------------------------------------------------- تحديثات خيط الواجهة
    def _ui(self, fn):
        """أي تحديث للواجهة يجب أن يمر من هنا — استدعاء Tkinter من خيط آخر يُسقط البرنامج."""
        try:
            self.after(0, fn)
        except (RuntimeError, tk.TclError):
            pass

    def _progress(self, text, ratio=None):
        self._msg(text, "#d4af37")
        if ratio is not None:
            self.progress.set(max(0.0, min(1.0, ratio)))

    def _fail(self, text):
        self._set_busy(False)
        self.progress.set(0)
        self._msg(text)
        self.entry_pass.delete(0, "end")
        self.entry_pass.focus_set()

    def _finish(self):
        stats = self.result.get("stats", {})
        self._msg(
            f"تم تجهيز {stats.get('transactions', 0)} حركة — جارٍ فتح النظام…",
            "#2ecc71")
        self.after(650, self.destroy)


# ==============================================================================
#  الواجهة العامة
# ==============================================================================

def require_login(app_version="", data_dir=None, api=None):
    """يعرض شاشة الدخول ويرجع الجلسة، أو None لو أغلقها المستخدم."""
    screen = LoginScreen(app_version=app_version, data_dir=data_dir, api=api)
    screen.mainloop()
    return screen.result
