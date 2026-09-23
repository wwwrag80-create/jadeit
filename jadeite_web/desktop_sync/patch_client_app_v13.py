# -*- coding: utf-8 -*-
"""
الدفعة الحادية عشرة — الجزء الأول:
  ١) إخفاء الشريط العلوي العام عند دخول أي شاشة، فتتوسّع الشاشة والجدول
     ويظهر بدلاً منه شريط الشاشة نفسه: زر القائمة الرئيسية يساراً،
     واسم الشاشة + الأرصدة + الفترة يميناً — تناسق أنظمة محاسبية.
  ٥) نسخة المدير: لا تسترجع بيانات الجهاز المحلية إطلاقاً، بل تسحب أحدث
     نسخة سحابية للعميل دائماً، وتعديلاتها ترجع للعميل عبر المزامنة.

الاستخدام:  python3 patch_client_app_v13.py rageh-1-34-14-cloud.py
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
#  ١) شريط الشاشة: أرصدة مصغّرة + فترة، والشريط العام يختفي
# ==========================================================================
rep('''        top_bar = ctk.CTkFrame(wrapper, fg_color=("gray85", "gray17"), height=52, corner_radius=10)
        top_bar.pack(fill="x", padx=5, pady=(5, 8))
        btn_back = ctk.CTkButton(top_bar, text="🏠 القائمة الرئيسية", font=("Cairo", 15, "bold"),
                                  fg_color="#555555", hover_color="#333333", width=170, height=38,
                                  command=self._go_home)
        btn_back.pack(side="left", padx=10, pady=7)
        ctk.CTkLabel(top_bar, text=name, font=ctk.CTkFont(family="Cairo", size=17, weight="bold"),
                     text_color="#d4af37").pack(side="right", padx=15, pady=7)''',
    '''        top_bar = ctk.CTkFrame(wrapper, fg_color=("gray85", "gray17"), height=52, corner_radius=10)
        top_bar.pack(fill="x", padx=5, pady=(5, 6))

        # يسار الشريط: العودة للقائمة الرئيسية
        btn_back = ctk.CTkButton(top_bar, text="🏠 القائمة الرئيسية", font=("Cairo", 15, "bold"),
                                  fg_color="#555555", hover_color="#333333", width=170, height=38,
                                  command=self._go_home)
        btn_back.pack(side="left", padx=10, pady=7)

        # يمين الشريط: اسم الشاشة
        ctk.CTkLabel(top_bar, text=name, font=ctk.CTkFont(family="Cairo", size=17, weight="bold"),
                     text_color="#d4af37").pack(side="right", padx=15, pady=7)

        # وسط الشريط: الفترة والأرصدة مصغّرة — كل ما كان يشغل الشريط العام
        # بارتفاع ٩٥ بكسل صار هنا في سطر واحد، فتُفرَّغ المساحة كلها للجدول
        info_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        info_box.pack(side="right", padx=8, pady=6)

        lbl_period = ctk.CTkLabel(info_box, text="", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                                   text_color="#1f77b4")
        lbl_period.pack(side="right", padx=8)

        lbl_treasury = ctk.CTkLabel(info_box, text="", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                                     text_color="#d4af37")
        lbl_treasury.pack(side="right", padx=8)

        lbl_total = ctk.CTkLabel(info_box, text="", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                                  text_color="#2ecc71")
        lbl_total.pack(side="right", padx=8)

        self._screen_info_labels[name] = {
            "period": lbl_period, "treasury": lbl_treasury, "total": lbl_total}''')

rep('''        self._contents = {}   # name -> إطار المحتوى (نفس ما كانت ترجعه tabview.tab())
        self._wrappers = {}   # name -> الإطار الكامل (شريط علوي + محتوى)
        self.go_home_callback = go_home_callback''',
    '''        self._contents = {}   # name -> إطار المحتوى (نفس ما كانت ترجعه tabview.tab())
        self._wrappers = {}   # name -> الإطار الكامل (شريط علوي + محتوى)
        self._screen_info_labels = {}   # name -> عناوين الفترة والأرصدة في شريط الشاشة
        self.go_home_callback = go_home_callback
        self.current_screen = None

    def update_screen_info(self, period_text, treasury_text, total_text):
        """يحدّث الفترة والأرصدة في شريط كل شاشة (تُستدعى من recalculate_all)"""
        for labels in self._screen_info_labels.values():
            try:
                labels["period"].configure(text=period_text)
                labels["treasury"].configure(text=treasury_text)
                labels["total"].configure(text=total_text)
            except Exception:
                pass''')

rep('''    def show(self, name):
        self.pack(fill="both", expand=True)''',
    '''    def show(self, name):
        self.current_screen = name
        self.pack(fill="both", expand=True)''')

# إخفاء/إظهار الشريط العام
rep('''    def create_layout(self):
        top_frame = ctk.CTkFrame(self, height=95, corner_radius=12)
        top_frame.pack(fill="x", padx=15, pady=10)''',
    '''    def create_layout(self):
        top_frame = ctk.CTkFrame(self, height=95, corner_radius=12)
        top_frame.pack(fill="x", padx=15, pady=10)
        self.top_frame = top_frame''')

rep('''    def navigate_to_screen(self, name):
        if getattr(self, 'home_arrange_mode', False):
            self.toggle_home_arrange_mode()
        if hasattr(self, 'home_frame') and self.home_frame:
            self.home_frame.pack_forget()
        self.tabview.show(name)

    def show_home_screen(self):
        if hasattr(self, 'home_frame') and self.home_frame:
            self.home_frame.pack(fill="both", expand=True)''',
    '''    def navigate_to_screen(self, name):
        if getattr(self, 'home_arrange_mode', False):
            self.toggle_home_arrange_mode()
        if hasattr(self, 'home_frame') and self.home_frame:
            self.home_frame.pack_forget()

        # الشريط العام يختفي داخل الشاشات: مساحته كاملة تذهب للجدول،
        # وبياناته (الفترة والأرصدة) تظهر مصغّرة في شريط الشاشة نفسها
        if hasattr(self, 'top_frame'):
            self.top_frame.pack_forget()

        self.tabview.show(name)
        self.refresh_screen_info_bar()

    def show_home_screen(self):
        # العودة للقائمة الرئيسية تُرجع الشريط العام كاملاً في مكانه الأصلي
        if hasattr(self, 'top_frame'):
            self.top_frame.pack(fill="x", padx=15, pady=10, before=self.main_shell)
        if hasattr(self, 'home_frame') and self.home_frame:
            self.home_frame.pack(fill="both", expand=True)

    def refresh_screen_info_bar(self):
        """يحدّث الفترة والأرصدة المصغّرة في شريط كل شاشة"""
        if not hasattr(self, 'tabview'):
            return
        try:
            self.tabview.update_screen_info(
                f"الفترة: {self.current_display_month}",
                f"الخزينة: {en(getattr(self, 'current_treasury_balance', 0.0))} جم",
                f"الرصيد الحالي: {en(getattr(self, 'current_total_gold', 0.0))} جم")
        except Exception:
            pass''')

# تحديث شريط الشاشة مع كل إعادة حساب
rep('''            self.lbl_total_gold.configure(text=f"الرصيد الحالي: {en(self.current_total_gold)} جم")''',
    '''            self.lbl_total_gold.configure(text=f"الرصيد الحالي: {en(self.current_total_gold)} جم")
        self.refresh_screen_info_bar()''')


# ==========================================================================
#  ٥) نسخة المدير: سحابية بحتة — لا تعتمد على قاعدة الجهاز المحلية
# ==========================================================================
rep('''    def open_as_client(self, client_id, business_name):''',
    '''    ADMIN_CLOUD_ONLY = True   # نسخة المدير لا تعتمد على بيانات الجهاز المحلية إطلاقاً

    def open_as_client(self, client_id, business_name):''')

rep('''        # تجهيز بيانات العميل على جهاز المدير قبل فتح النظام.
        # مفتاح الخدمة يعمل حتى بدون رمز مزامنة صريح، فنحاول السحب دائماً
        # طالما وحدات المزامنة متاحة — لا نمنعها فقط لغياب الرمز.
        if SYNC_AVAILABLE:
            try:
                db_path = os.path.join(DATA_DIR, f"client_data_{client_id}.db")
                api = _RpcBridge(sb_admin, CURRENT_SYNC_TOKEN)''',
    '''        # تجهيز بيانات العميل على جهاز المدير قبل فتح النظام.
        # مفتاح الخدمة يعمل حتى بدون رمز مزامنة صريح، فنحاول السحب دائماً
        # طالما وحدات المزامنة متاحة — لا نمنعها فقط لغياب الرمز.
        if SYNC_AVAILABLE:
            try:
                db_path = os.path.join(DATA_DIR, f"client_data_{client_id}.db")

                # نسخة المدير سحابية بحتة: نبدأ من قاعدة نظيفة في كل مرة، فما
                # يُعرض هو أحدث نسخة سحابية للعميل حصراً — لا بقايا من جلسة
                # سابقة على جهاز المدير قد تُظهر أرقاماً قديمة أو محذوفة عند العميل.
                if getattr(self, "ADMIN_CLOUD_ONLY", True):
                    self.reset_admin_local_cache(db_path)

                api = _RpcBridge(sb_admin, CURRENT_SYNC_TOKEN)''')

rep('''    ADMIN_CLOUD_ONLY = True   # نسخة المدير لا تعتمد على بيانات الجهاز المحلية إطلاقاً''',
    '''    ADMIN_CLOUD_ONLY = True   # نسخة المدير لا تعتمد على بيانات الجهاز المحلية إطلاقاً

    @staticmethod
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
                log_cloud_error("تعذّر تنظيف النسخة المؤقتة على جهاز المدير", e)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة الحادية عشرة على:", SRC)
