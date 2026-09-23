# -*- coding: utf-8 -*-
"""
الدفعة الخامسة:
  ١) "الذهب عند المصنعين/المركبين" = إجمالي الفاقد الزائد، ويصبح صفراً بعد الإقفال
  ٢) عمودا "مسموح/٨" و"مسموح/٤" في كشف حركة المصنعين والمركبين
  ٣) زر تصفير النظام فوق شريط الفترة
  ٤) انتحال شخصية العميل من داخل البرنامج مع سحب بياناته ومزامنة لحظية

الاستخدام:  python3 patch_client_app_v5.py rageh-1-34-14-cloud.py
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
#  ١) الذهب عند المصنعين/المركبين = الفاقد الزائد، وصفر بعد الإقفال
# ==========================================================================
rep('''    def get_current_unclosed_khayas(self, cat):''',
    '''    def get_section_excess_loss(self, cat_name, target_month=None):
        """إجمالي (الفاقد الزائد) لكل عمال القسم — وهو ما يظهر أسفل الجدول"""
        total = 0.0
        for n in self.categories.get(cat_name, []):
            res = self.calculate_single_ledger(n, cat_name, target_month=target_month)
            total += res.get("الفاقد الزائد", 0.0)
        return round(total, 2)

    def get_gold_at_section(self, cat_name):
        """الذهب الموجود فعلياً عند القسم الآن.

        = إجمالي الفاقد الزائد، ناقص ما سبق إقفاله.
        بعد الإقفال يصبح صفراً، لأن المُقفل رُحّل لحساب الخسائر ولم يعد ذهباً نملكه.
        الشريط البارز والجدول أسفله لا يتأثران — يبقيان يعرضان الأرقام التفصيلية كما هي.
        """
        if cat_name not in ("المصنعين", "المركبين"):
            return self.get_current_unclosed_khayas(cat_name)

        excess = self.get_section_excess_loss(cat_name)
        closed = self.get_box_closed_total(cat_name)

        # كل الخياس مُقفل: لم يبقَ ذهب عند القسم إطلاقاً
        if self.get_current_unclosed_khayas(cat_name) <= 0.005:
            return 0.0

        if closed > 0:
            return round(max(excess - closed, 0.0), 2)
        return excess

    def get_current_unclosed_khayas(self, cat):''')

# لوحة (الذهب عند القسم) في شاشة صناديق الخياس
rep('''        # لوحة (الذهب عند القسم) = إجمالي عمود الفاقد الكلي للقسم المعروض حالياً
        if hasattr(self, 'lbl_dash_alert'):
            gold_at_section = tot.get("الفاقد الكلي", 0.0)
            self.lbl_dash_alert.configure(text=f"الذهب عند {self.get_display_label(self.current_view_cat)}: {gold_at_section:.2f} جم")''',
    '''        # لوحة (الذهب عند القسم) = إجمالي الفاقد الزائد، ويصبح صفراً بعد الإقفال
        if hasattr(self, 'lbl_dash_alert'):
            gold_at_section = self.get_gold_at_section(self.current_view_cat)
            self.lbl_dash_alert.configure(
                text=f"الذهب عند {self.get_display_label(self.current_view_cat)}: {gold_at_section:.2f} جم")''')

# الرصيد الحالي يعتمد الرقم نفسه (فيصبح صفراً بعد الإقفال)
rep('''        # الذهب عند المصنعين والمركبين (الفاقد اللحظي غير المُقفل)
        total += self.get_actual_section_khayas("المصنعين")
        total += self.get_actual_section_khayas("المركبين")''',
    '''        # الذهب عند المصنعين والمركبين — يصبح صفراً بعد إقفال خياسهم
        total += self.get_gold_at_section("المصنعين")
        total += self.get_gold_at_section("المركبين")''')

rep('''        parts = [("الخزينة", getattr(self, "current_treasury_balance", 0.0)),
                 ("المصنعين", self.get_actual_section_khayas("المصنعين")),
                 ("المركبين", self.get_actual_section_khayas("المركبين"))]''',
    '''        parts = [("الخزينة", getattr(self, "current_treasury_balance", 0.0)),
                 ("المصنعين", self.get_gold_at_section("المصنعين")),
                 ("المركبين", self.get_gold_at_section("المركبين"))]''')


# ==========================================================================
#  ٢) عمودا مسموح/٨ ومسموح/٤ في كشف حركة المصنعين والمركبين
# ==========================================================================
rep('''        elif cat == "المركبين":
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "ليز", "سلك راجع", "عيار", "الفاقد اللحظي", "البيان")
        else: # المصنعين
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "مفنش 8", "مفنش 4", "بوليش", "ليز", "سلك راجع", "عيار", "الفاقد اللحظي", "البيان")''',
    '''        elif cat == "المركبين":
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "ليز", "سلك راجع", "عيار", "الفاقد اللحظي",
                    "مسموح/٨", "مسموح/٤", "البيان")
        else: # المصنعين
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "مفنش 8", "مفنش 4", "بوليش", "ليز", "سلك راجع", "عيار",
                    "الفاقد اللحظي", "مسموح/٨", "مسموح/٤", "البيان")''')

# صفوف المركبين
rep('''                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", note), tags=row_tags)''',
    '''                # المسموح في المركبين يُحتسب على القبض (نفس معادلة شاشة صناديق الخياس)
                allow8 = round(data['قبض'] * ALLOWANCE_8, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", f"{allow8:.3f}", "-", note), tags=row_tags)''')

# صفوف المصنعين
rep('''                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}", f"{data['مفنش 4']:.2f}", f"{data['بوليش']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", note), tags=row_tags)''',
    '''                # المسموح في المصنعين يُحتسب على المفنش ٨ و٤ (نفس معادلة شاشة صناديق الخياس)
                allow8 = round(data['مفنش 8'] * ALLOWANCE_8, 2)
                allow4 = round(data['مفنش 4'] * ALLOWANCE_4, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["مسموح 4"] = round(tot["مسموح 4"] + allow4, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}", f"{data['مفنش 4']:.2f}", f"{data['بوليش']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", f"{allow8:.3f}", f"{allow4:.3f}", note), tags=row_tags)''')

# مجاميع الأعمدة الجديدة
rep('''        tot = {k: 0.0 for k in ("صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع", "قبل", "بعد", "الخياس", "trees", "فاقد")}''',
    '''        tot = {k: 0.0 for k in ("صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع",
                                "قبل", "بعد", "الخياس", "trees", "فاقد", "مسموح 8", "مسموح 4")}''')

# سطر الإجمالي
rep('''                self.op_ledger_tree.insert("", "end", values=("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot['فاقد']:.2f}", "-"), tags=("total_tag",))''',
    '''                self.op_ledger_tree.insert("", "end", values=("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", "-", "-"), tags=("total_tag",))''')

rep('''                self.op_ledger_tree.insert("", "end", values=("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['مفنش 8']:.2f}", f"{tot['مفنش 4']:.2f}", f"{tot['بوليش']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot['فاقد']:.2f}", "-"), tags=("total_tag",))''',
    '''                self.op_ledger_tree.insert("", "end", values=("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['مفنش 8']:.2f}", f"{tot['مفنش 4']:.2f}", f"{tot['بوليش']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", f"{tot['مسموح 4']:.3f}", "-"), tags=("total_tag",))''')

# ثوابت المسموح في مكان واحد
rep('''APP_VERSION = "1.35.0"''',
    '''APP_VERSION = "1.36.0"

# نسب المسموح — معرّفة هنا في مكان واحد لتبقى شاشة صناديق الخياس
# وكشف حركة المصنعين/المركبين متطابقتين دائماً
ALLOWANCE_8 = 0.008    # ٨ بالألف
ALLOWANCE_4 = 0.004    # ٤ بالألف''')

# توحيد المصدر في حساب الكشف
rep('''            ledger["مسموح 8"] = round(ledger["القبض"] * 0.008, 2)''',
    '''            ledger["مسموح 8"] = round(ledger["القبض"] * ALLOWANCE_8, 2)''')
rep('''            ledger["مسموح 8"] = round(ledger["المفنش ٨ بالالف"] * 0.008, 2)
            ledger["مسموح 4"] = round(ledger["المفنش ٤ بالالف"] * 0.004, 2)''',
    '''            ledger["مسموح 8"] = round(ledger["المفنش ٨ بالالف"] * ALLOWANCE_8, 2)
            ledger["مسموح 4"] = round(ledger["المفنش ٤ بالالف"] * ALLOWANCE_4, 2)''')


# ==========================================================================
#  ٣) زر تصفير النظام فوق شريط الفترة
# ==========================================================================
rep('''        btn_clear_system.pack(side="left", padx=10, pady=25)''',
    '''        # يُوضع فوق شريط الفترة في عمود واحد بدل جانبه
        period_column = ctk.CTkFrame(top_frame, fg_color="transparent")
        period_column.pack(side="right", padx=10, pady=8)

        btn_clear_system.master = period_column
        btn_clear_system.pack(in_=period_column, pady=(0, 4))''')

rep('''        period_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        period_frame.pack(side="right", padx=10, pady=20)''',
    '''        period_frame = ctk.CTkFrame(period_column, fg_color="transparent")
        period_frame.pack()''')


# ==========================================================================
#  ٤) انتحال شخصية العميل من البرنامج مع سحب بياناته ومزامنة لحظية
# ==========================================================================
rep('''    def open_as_client(self, client_id, business_name):
        """انتحال شخصية العميل: يفتح البرنامج الكامل ببياناته هو، باستخدام صلاحيات المدير"""
        self.withdraw()
        app = GoldSystemApp(client_id=client_id, client_name=business_name,
                             supabase_client=get_supabase_admin_client(), is_admin_session=True)
        app.mainloop()
        self.deiconify()''',
    '''    def open_as_client(self, client_id, business_name):
        """انتحال شخصية العميل: يسحب بياناته من السحابة أولاً ثم يفتح نظامه كاملاً.

        بدون السحب كان المدير يرى قاعدة فارغة على جهازه هو، لأن بيانات العميل
        موجودة في السحابة لا على جهاز المدير. وبعد الفتح يبقى محرك المزامنة
        شغّالاً فتصل أي حركة يسجّلها العميل خلال ثوانٍ.
        """
        global CURRENT_SYNC_TOKEN

        sb_admin = get_supabase_admin_client()

        # رمز مزامنة العميل يُقرأ من السحابة ويبقى في الذاكرة فقط
        CURRENT_SYNC_TOKEN = None
        try:
            res = sb_admin.table("tenants").select("sync_token").eq("id", client_id).limit(1).execute()
            if res.data:
                CURRENT_SYNC_TOKEN = res.data[0].get("sync_token")
        except Exception as e:
            log_cloud_error("تعذّر قراءة رمز مزامنة العميل", e)

        self.withdraw()

        # تجهيز بيانات العميل على جهاز المدير قبل فتح النظام
        if SYNC_AVAILABLE and CURRENT_SYNC_TOKEN:
            try:
                db_path = os.path.join(DATA_DIR, f"client_data_{client_id}.db")
                api = _RpcBridge(sb_admin, CURRENT_SYNC_TOKEN)
                prep = ctk.CTkToplevel(self)
                prep.withdraw()
                win = SyncDownWindow(prep, db_path, api, client_id, business_name)
                prep.wait_window(win)
                prep.destroy()
                if win.error:
                    messagebox.showwarning(
                        "تنبيه",
                        f"تعذّر سحب بيانات العميل من السحابة:\\n{win.error}\\n\\n"
                        "سيُفتح النظام بما هو محفوظ على هذا الجهاز.")
            except Exception as e:
                log_cloud_error("تعذّر تجهيز بيانات العميل للمدير", e)
        elif not CURRENT_SYNC_TOKEN:
            messagebox.showwarning(
                "المزامنة غير مفعّلة",
                f"لا يوجد رمز مزامنة لحساب ({business_name}).\\n\\n"
                "شغّل ملف 08_client_login.sql في Supabase لإنشاء رموز المزامنة للعملاء.")

        app = GoldSystemApp(client_id=client_id, client_name=business_name,
                             supabase_client=sb_admin, is_admin_session=True)
        app.mainloop()

        CURRENT_SYNC_TOKEN = None
        self.deiconify()
        self.refresh_clients()''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة الخامسة على:", SRC)
