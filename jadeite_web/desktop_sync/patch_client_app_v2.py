# -*- coding: utf-8 -*-
"""
الدفعة الثانية على نسخة العميل:
  ١) شاشة الخسائر: شريط تمرير حتى تظهر كل الصناديق
  ٢) المصنعين والمركبين والكاستنج: أرقام بلون واحد ثابت مهما كانت القيمة
  ٣) إصلاح خطأ التاريخ: النظام كان يفتح على شهر سابق تلقائياً
  ٤) تحديث الشاشات تلقائياً عند وصول تعديل من لوحة الويب

الاستخدام:  python3 patch_client_app_v2.py rageh-1-34-14-cloud.py
"""
import io
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(SRC, encoding="utf-8").read()


def rep(old, new, count=1):
    global src
    n = src.count(old)
    assert n == count, "MISMATCH (%d != %d):\n%s" % (n, count, old[:200])
    src = src.replace(old, new)


# ==========================================================================
#  ١) إصلاح خطأ التاريخ  ← أخطر مشكلة في هذه الدفعة
#
#  السبب: عند تحميل البيانات كان النظام يضبط الفترة المعروضة على
#  (أحدث شهر فيه حركات) لا على الشهر الحالي. فمع بداية كل شهر جديد،
#  وقبل تسجيل أول حركة فيه، يفتح البرنامج على الشهر السابق.
#  والأخطر: خانات التاريخ تُعبّأ حينها بـ (أول يوم في الشهر السابق)،
#  فتُسجَّل حركات الشهر الجديد بتاريخ الشهر الماضي وتفسد الفترة المحاسبية.
# ==========================================================================
rep('''        active_dates = [
            inv["التاريخ"][:7] for inv in self.invoices.values() 
            if inv.get("التاريخ") and len(inv["التاريخ"]) >= 7 and inv["settled_status"] == "ACTIVE" and inv["النوع"] != "رصيد افتتاحي"
        ]
        if active_dates:
            self.current_display_month = max(active_dates)''',
    '''        # الفترة المعروضة = الشهر الحالي فعلياً حسب تاريخ الجهاز، دائماً.
        #
        # سابقاً كانت تُضبط على (أحدث شهر فيه حركات)، فكان البرنامج يفتح على
        # الشهر السابق في بداية كل شهر جديد قبل تسجيل أول حركة فيه — وتُعبّأ
        # خانات التاريخ بأول يوم من الشهر الماضي، فتُسجَّل حركات الشهر الجديد
        # في الشهر الخطأ. الاختيار اليدوي من قائمة الفترات يبقى متاحاً كما هو.
        self.current_display_month = datetime.datetime.now().strftime("%Y-%m")''')

# تنبيه واضح عند العمل في فترة غير الشهر الحالي + مراقبة تغيّر الشهر
rep('''    def get_smart_default_date(self):
        curr_sys_month = datetime.datetime.now().strftime("%Y-%m")
        if self.current_display_month == curr_sys_month:
            return datetime.datetime.now().strftime("%Y-%m-%d")
        else:
            return f"{self.current_display_month}-01"''',
    '''    def get_smart_default_date(self):
        curr_sys_month = datetime.datetime.now().strftime("%Y-%m")
        if self.current_display_month == curr_sys_month:
            return datetime.datetime.now().strftime("%Y-%m-%d")
        else:
            # فترة سابقة/لاحقة مختارة يدوياً: نبدأ من أول يوم فيها
            return f"{self.current_display_month}-01"

    def update_period_warning(self):
        """مؤشر واضح بجوار مختار الفترة عندما تكون الفترة المعروضة ليست الشهر الحالي.

        الهدف: ألا يُسجّل المستخدم حركات في شهر خطأ وهو لا ينتبه.
        """
        if not hasattr(self, 'lbl_period_warning'):
            return
        curr = datetime.datetime.now().strftime("%Y-%m")
        if self.current_display_month == curr:
            self.lbl_period_warning.configure(text="")
        else:
            self.lbl_period_warning.configure(
                text=f"⚠️ أنت تعمل في فترة سابقة ({self.current_display_month}) — الشهر الحالي {curr}")

    def watch_system_month(self):
        """يراقب تغيّر شهر النظام والبرنامج مفتوح (يعمل ليلاً عند نهاية الشهر).

        بدون هذا يبقى البرنامج مفتوحاً من ٣١ يوليو إلى ١ أغسطس وهو ما زال
        يسجّل في يوليو، لأن الفترة تُحسب مرة واحدة عند التشغيل فقط.
        """
        try:
            curr = datetime.datetime.now().strftime("%Y-%m")
            last = getattr(self, "_last_seen_system_month", None)
            if last is None:
                self._last_seen_system_month = curr
            elif curr != last:
                self._last_seen_system_month = curr
                if messagebox.askyesno(
                        "بداية شهر جديد",
                        f"بدأ شهر جديد ({curr}).\\n\\n"
                        f"هل تريد الانتقال للفترة الجديدة الآن؟\\n"
                        f"(إن اخترت لا، ستبقى في فترة {self.current_display_month} "
                        f"وستُسجَّل حركاتك فيها)"):
                    self.current_display_month = curr
                    self.update_period_selector()
                    self.on_period_changed(curr)
        except Exception:
            pass
        finally:
            self.after(300000, self.watch_system_month)   # كل ٥ دقائق''')

# تشغيل المراقبة وتحديث المؤشر
rep('''        self.update_edit_status_ui()
        self.start_cloud_sync_engine()''',
    '''        self.update_edit_status_ui()
        self.update_period_warning()
        self.watch_system_month()
        self.start_cloud_sync_engine()''')

rep('''    def on_period_changed(self, selected_period):
        self.current_display_month = selected_period
        self.recalculate_all()''',
    '''    def on_period_changed(self, selected_period):
        self.current_display_month = selected_period
        self.recalculate_all()
        self.update_period_warning()''')

# مؤشر التنبيه بجوار مختار الفترة
rep('''        self.combo_active_period.configure(values=sorted_months)
        self.combo_active_period.set(self.current_display_month)''',
    '''        self.combo_active_period.configure(values=sorted_months)
        self.combo_active_period.set(self.current_display_month)
        self.update_period_warning()''')


# ==========================================================================
#  ٢) الألوان: أرقام بلون واحد ثابت في المصنعين والمركبين والكاستنج
# ==========================================================================
rep('''                # لون واحد لكل الصفوف، عدا الصف الذي يكون فاقده اللحظي سالباً فيظهر بالأحمر
                row_tags = ("red_tag",) if faqid < 0 else ()
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}"''',
    '''                # لون واحد ثابت لكل صفوف المركبين مهما كانت قيمة الفاقد (موجبة أو سالبة)
                row_tags = ()
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}"''')

rep('''                # لون واحد لكل الصفوف، عدا الصف الذي يكون فاقده اللحظي سالباً فيظهر بالأحمر
                row_tags = ("red_tag",) if faqid < 0 else ()
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}"''',
    '''                # لون واحد ثابت لكل صفوف المصنعين مهما كانت قيمة الفاقد (موجبة أو سالبة)
                row_tags = ()
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}"''')

# جداول شاشات العمليات (الكاستنج/الصب والتلميع والبف): لون ثابت أيضاً
rep('''            # اللون الأحمر لأي صف يكون فيه الدائن (القبض) أكبر من المدين (الصرف)
            tags = ("red_tag",) if g["دائن"] > g["مدين"] else ()''',
    '''            # لون واحد ثابت لكل الصفوف مهما كانت قيمة الخياس (موجبة أو سالبة).
            # الإجماليات أسفل الجدول هي المرجع لقراءة الوضع، لا لون السطر.
            tags = ()''')


# ==========================================================================
#  ٣) شاشة الخسائر: شريط تمرير
# ==========================================================================
rep('''    def build_losses_tab(self):
        tab = self.tabview.tab("شاشة الخسائر")

        ctk.CTkLabel(tab, text="📉 شاشة الخسائر - إقفال صناديق الخياس"''',
    '''    def build_losses_tab(self):
        outer = self.tabview.tab("شاشة الخسائر")

        # إطار قابل للتمرير: عدد الصناديق يزيد مع الأقسام المضافة،
        # وبدون تمرير كانت البطاقات الأخيرة وأزرار الكشف والطباعة تختفي أسفل الشاشة
        tab = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        tab.pack(fill="both", expand=True, padx=4, pady=4)

        ctk.CTkLabel(tab, text="📉 شاشة الخسائر - إقفال صناديق الخياس"''')


# ==========================================================================
#  ٤) تحديث الشاشات عند وصول تعديل من لوحة الويب
# ==========================================================================
rep('''            self.cloud_sync = CloudSync(
                db_path=self.db_path,
                api=api,
                tenant_id=self.client_id,
                app_version=APP_VERSION,
                on_status=self._on_sync_status,
            )''',
    '''            self.cloud_sync = CloudSync(
                db_path=self.db_path,
                api=api,
                tenant_id=self.client_id,
                app_version=APP_VERSION,
                on_status=self._on_sync_status,
                on_remote_change=self._on_remote_change,
            )''')

rep('''    def _on_sync_status(self, text):
        """تُستدعى من الخيط الخلفي — نمرّرها لخيط الواجهة عبر after"""
        try:
            self.after(0, lambda: self.lbl_cloud_sync.configure(text=text))
        except Exception:
            pass''',
    '''    def _on_sync_status(self, text):
        """تُستدعى من الخيط الخلفي — نمرّرها لخيط الواجهة عبر after"""
        try:
            self.after(0, lambda: self.lbl_cloud_sync.configure(text=text))
        except Exception:
            pass

    def _on_remote_change(self, count):
        """وصلت تعديلات من لوحة الإدارة على الويب: نعيد تحميل البيانات ونحدّث الشاشات.

        تُستدعى من الخيط الخلفي، فكل العمل يمر عبر after حتى لا يُسقط Tkinter.
        """
        def apply():
            try:
                self.load_data_from_db()
                self.update_period_selector()
                self.recalculate_all()
                if hasattr(self, 'lbl_cloud_sync'):
                    self.lbl_cloud_sync.configure(
                        text=f"🔄 وصل {count} تحديث من الإدارة")
                    self.after(6000, lambda: self.lbl_cloud_sync.configure(
                        text=self.cloud_sync.status_text() if self.cloud_sync else ""))
            except Exception as e:
                log_cloud_error("تعذّر تطبيق تحديثات الإدارة", e)

        try:
            self.after(0, apply)
        except Exception:
            pass''')

# مؤشر تنبيه الفترة في الشريط العلوي
rep('''        self.lbl_cloud_sync = ctk.CTkLabel(status_box, text="☁️ المزامنة: —", font=ctk.CTkFont(family="Cairo", size=11), text_color="#aaaaaa")
        self.lbl_cloud_sync.pack(padx=10)''',
    '''        self.lbl_cloud_sync = ctk.CTkLabel(status_box, text="☁️ المزامنة: —", font=ctk.CTkFont(family="Cairo", size=11), text_color="#aaaaaa")
        self.lbl_cloud_sync.pack(padx=10)

        # تنبيه واضح لو كانت الفترة المعروضة ليست الشهر الحالي
        self.lbl_period_warning = ctk.CTkLabel(status_box, text="", font=ctk.CTkFont(family="Cairo", size=11, weight="bold"), text_color="#e67e22")
        self.lbl_period_warning.pack(padx=10)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة الثانية على:", SRC)
