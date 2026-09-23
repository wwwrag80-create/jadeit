# -*- coding: utf-8 -*-
"""
الدفعة الثالثة والعشرون — إصلاح حرج بعد حادثة تلف بيانات العميل:

  ما حدث: نسخة العميل كانت **تسحب** من السحابة عند الدخول وتدمج ما فيها في
  قاعدتها. وبما أن السحابة كانت تحمل بيانات جهاز المدير (بفتراتها الخاطئة
  ٧/٨/٩)، انتقلت تلك البيانات إلى جهاز العميل وطمست بياناته.

  القاعدة الصحيحة — اتجاه واحد فقط:
      • نسخة العميل: مصدر الحقيقة. ترفع فقط، ولا تسحب شيئاً أبداً.
      • نسخة المدير: مرآة للقراءة. تسحب فقط، ولا ترفع شيئاً أبداً.
  بهذا يستحيل أن تصل بيانات المدير إلى جهاز العميل.

  وأُضيفت شاشة استعادة النسخ الاحتياطية ليرجع العميل لبياناته السابقة.

الاستخدام:  python3 patch_client_app_v33.py rageh-1-34-14-cloud.py
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
#  ١) نسخة العميل لا تسحب من السحابة إطلاقاً
# ==========================================================================
rep('''    def _work(self):
        try:
            # نسخة المدير: نبدأ من قاعدة نظيفة دائماً، فما يُعرض هو أحدث نسخة
            # سحابية للعميل حصراً — لا بقايا من جلسة سابقة على هذا الجهاز
            if self.cloud_only:
                self._progress("جارٍ تجهيز نسخة سحابية نظيفة…", 0.03)
                reset_local_cache(self.db_path)

            install_sync_schema(self.db_path)''',
    '''    def _work(self):
        try:
            # ═══════════════════════════════════════════════════════════════
            #  اتجاه المزامنة — قاعدة صارمة لا استثناء لها:
            #
            #  نسخة العميل (IS_ADMIN_BUILD = False):
            #      بياناتها المحلية هي مصدر الحقيقة. تُرفع للسحابة فقط،
            #      ولا يُسحب إليها شيء إطلاقاً. سحب السحابة إليها كان يطمس
            #      بياناته ببيانات جهاز المدير — وهي الحادثة التي وقعت.
            #
            #  نسخة المدير (IS_ADMIN_BUILD = True):
            #      مرآة للقراءة فقط: تمسح نسختها المؤقتة وتسحب من السحابة،
            #      ولا ترفع شيئاً أبداً.
            # ═══════════════════════════════════════════════════════════════
            if not IS_ADMIN_BUILD:
                self._progress("جارٍ رفع بياناتك للسحابة…", 0.15)
                install_sync_schema(self.db_path)
                uploader = CloudSync(db_path=self.db_path, api=self.api,
                                     tenant_id=self.tenant_id, app_version=APP_VERSION)
                pending = uploader.pending_count()
                if pending > 0:
                    uploader.flush(max_batches=500)
                self._progress("تم رفع بياناتك ✔", 1.0)
                self.error = None
                self._done()
                return

            # نسخة المدير: نبدأ من قاعدة نظيفة دائماً، فما يُعرض هو أحدث نسخة
            # سحابية للعميل حصراً — لا بقايا من جلسة سابقة على هذا الجهاز
            if self.cloud_only:
                self._progress("جارٍ تجهيز نسخة سحابية نظيفة…", 0.03)
                reset_local_cache(self.db_path)

            install_sync_schema(self.db_path)''')

# تعديلات المدير لا تنزل للعميل
rep('''    def _on_remote_change(self, count):''',
    '''    def _on_remote_change(self, count):
        # نسخة العميل لا تستقبل أي تغيير من السحابة: بياناتها مصدر الحقيقة
        if not IS_ADMIN_BUILD:
            return''')

# محرك المزامنة في نسخة المدير لا يرفع شيئاً
rep('''    def start_cloud_sync_engine(self):''',
    '''    def start_cloud_sync_engine(self):
        # نسخة المدير مرآة للقراءة: لا تُشغّل محرك الرفع إطلاقاً، فلا يمكن
        # لبياناتها المؤقتة أن تصعد للسحابة وتطمس بيانات العميل
        if IS_ADMIN_BUILD:
            return''')


# ==========================================================================
#  ٢) شاشة استعادة النسخ الاحتياطية
# ==========================================================================
rep('''    def recover_corrupt_database(self):''',
    '''    def describe_backup(self, path):
        """وصف مقروء لنسخة احتياطية: وقتها، حجمها، وعدد حركاتها"""
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            size_kb = max(1, os.path.getsize(path) // 1024)
        except Exception:
            return None

        rows = periods = "?"
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            rows = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
            cols = [c[1] for c in con.execute("PRAGMA table_info(invoices)")]
            if "period" in cols:
                periods = con.execute(
                    "SELECT COUNT(DISTINCT COALESCE(NULLIF(period,''), substr(date_time,1,7))) "
                    "FROM invoices").fetchone()[0]
            else:
                periods = con.execute(
                    "SELECT COUNT(DISTINCT substr(date_time,1,7)) FROM invoices").fetchone()[0]
            con.close()
        except Exception:
            pass

        delta = datetime.datetime.now() - mtime
        if delta.days >= 1:
            ago = f"قبل {delta.days} يوم"
        elif delta.seconds >= 3600:
            ago = f"قبل {delta.seconds // 3600} ساعة"
        else:
            ago = f"قبل {max(1, delta.seconds // 60)} دقيقة"

        return {"path": path, "when": mtime.strftime("%Y-%m-%d  %H:%M"), "ago": ago,
                "rows": rows, "periods": periods, "size": f"{size_kb} كيلوبايت"}

    def open_backup_restore_window(self):
        """شاشة استعادة نسخة احتياطية سابقة.

        تعرض كل النسخ المحفوظة بوقتها وعدد حركاتها وفتراتها، فيختار المستخدم
        النسخة الصحيحة بنفسه — لا تخمين ولا استعادة عمياء.
        """
        backups = self.list_local_backups()
        if not backups:
            messagebox.showinfo(
                "لا توجد نسخ",
                f"لم يُعثر على نسخ احتياطية في:\\n{self.backup_dir}")
            return

        win = ctk.CTkToplevel(self)
        win.title("استعادة نسخة احتياطية")
        win.geometry("820x560")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="🗄️ استعادة نسخة احتياطية سابقة",
                     font=("Cairo", 20, "bold"), text_color="#d4af37").pack(pady=(16, 2))
        ctk.CTkLabel(win,
                     text="اختر النسخة التي تريد الرجوع إليها — الأحدث أولاً.\\n"
                          "قبل الاستعادة تُحفظ نسخة من وضعك الحالي تلقائياً، فلا تفقد شيئاً.",
                     font=("Cairo", 12), text_color="#8b8f95", justify="center").pack(pady=(0, 10))

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=18, pady=6)

        cols = ("وقت النسخة", "منذ", "عدد الحركات", "عدد الفترات", "الحجم")
        tree = self.create_standard_treeview(frame, cols, height=14)
        for c, w in zip(cols, (200, 130, 130, 120, 130)):
            tree.column(c, width=w, anchor="center")

        info_by_iid = {}
        for path in backups:
            info = self.describe_backup(path)
            if not info:
                continue
            iid = tree.insert("", "end", values=(
                info["when"], info["ago"], info["rows"], info["periods"], info["size"]))
            info_by_iid[iid] = info

        if not info_by_iid:
            messagebox.showwarning("تعذّر", "لم يمكن قراءة أي نسخة احتياطية.", parent=win)
            win.destroy()
            return

        def do_restore():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "اختر النسخة المراد استعادتها.", parent=win)
                return
            info = info_by_iid[sel[0]]

            if not messagebox.askyesno(
                    "تأكيد الاستعادة",
                    f"استعادة نسخة {info['when']} ({info['ago']})\\n"
                    f"عدد حركاتها: {info['rows']}  |  فتراتها: {info['periods']}\\n\\n"
                    "سيُستبدل وضعك الحالي ببيانات هذه النسخة.\\n"
                    "وستُحفظ نسخة من وضعك الحالي قبل ذلك تلقائياً.\\n\\n"
                    "هل تريد المتابعة؟", parent=win):
                return

            ok, msg = self.restore_from_backup(info["path"])
            win.destroy()
            if ok:
                messagebox.showinfo(
                    "تمت الاستعادة",
                    f"تمت استعادة نسخة {info['when']} بنجاح.\\n\\n"
                    "سيُغلق البرنامج الآن — افتحه من جديد لتظهر بياناتك المستعادة.")
                self.destroy()
            else:
                messagebox.showerror("تعذّرت الاستعادة", msg)

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(pady=12)
        ctk.CTkButton(btns, text="↩️ استعادة النسخة المحددة", font=("Cairo", 15, "bold"),
                      fg_color="#1e8449", hover_color="#145a32", width=250, height=44,
                      command=do_restore).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="📂 فتح مجلد النسخ", font=("Cairo", 13),
                      fg_color="#555555", hover_color="#333333", width=160, height=44,
                      command=lambda: self.open_folder(self.backup_dir)).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="إغلاق", font=("Cairo", 13), fg_color="#555555",
                      hover_color="#333333", width=120, height=44,
                      command=win.destroy).pack(side="left", padx=6)

    def restore_from_backup(self, backup_path):
        """يستعيد قاعدة البيانات من نسخة احتياطية.

        الترتيب مقصود: نحفظ الوضع الحالي أولاً، ثم نتحقق من سلامة النسخة
        المختارة، ثم نستبدل — فلا يُفقد شيء حتى لو كانت النسخة تالفة.
        يرجع: (نجح؟، رسالة)
        """
        try:
            # (١) حفظ الوضع الحالي قبل أي تغيير
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safety = os.path.join(self.backup_dir, f"before_restore_{stamp}.db")
            with sqlite3.connect(self.db_path) as srccon, sqlite3.connect(safety) as dst:
                srccon.backup(dst)

            # (٢) التحقق من سلامة النسخة المختارة قبل الاعتماد عليها
            probe = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
            try:
                integrity = probe.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    return False, f"النسخة تالفة (فحص السلامة: {integrity}).\\nلم يتغيّر شيء."
                probe.execute("SELECT COUNT(*) FROM invoices").fetchone()
            finally:
                probe.close()

            # (٣) الاستبدال
            with sqlite3.connect(backup_path) as srccon, sqlite3.connect(self.db_path) as dst:
                srccon.backup(dst)

            log_cloud_error("تمت استعادة نسخة احتياطية",
                            Exception(f"{backup_path} (نسخة الأمان: {safety})"))
            return True, "تمت الاستعادة"
        except Exception as e:
            return False, f"تعذّرت الاستعادة:\\n{e}\\n\\nلم يتغيّر شيء في بياناتك الحالية."

    def open_folder(self, path):
        """يفتح مجلداً في مستكشف الملفات"""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showinfo("المسار", f"{path}\\n\\n({e})")

    def recover_corrupt_database(self):''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة الثالثة والعشرين على:", SRC)
