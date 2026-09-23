# -*- coding: utf-8 -*-
"""
الدفعة الرابعة والعشرون — واجهة جديدة بشريط جانبي:

  • شريط تنقّل ثابت على **يمين** الشاشة، أبيض زجاجي بحواف زرقاء لامعة
  • كل شاشة زرٌّ بارز مستقل، والترتيب المطلوب:
        المبيعات/الصادر ← صناديق الخياس ← الوارد/قبض ← شاشة الخسائر
        ← صناديق المصنع ← (أخرى ▾) تفتح باقي الشاشات
  • المساحة الفارغة يملؤها شعار جاديت كبيراً بارزاً
  • القياسات تتكيّف مع حجم الشاشة (كبيرة أو صغيرة)

  البنية آمنة: الشاشات نفسها لم تُمسّ — وُضع الشريط بجانب حاوية الشاشات
  (main_shell) لا داخلها، فيبقى ظاهراً مهما فُتحت شاشة.

الاستخدام:  python3 patch_client_app_v34.py rageh-1-34-14-cloud.py
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
#  ١) هيكل الواجهة: شريط جانبي يمين + حاوية الشاشات
# ==========================================================================
rep('''        self.main_shell = ctk.CTkFrame(self, fg_color="transparent")
        self.main_shell.pack(fill="both", expand=True, padx=15, pady=5)''',
    '''        # جسم الواجهة: الشريط الجانبي يميناً وحاوية الشاشات يساره.
        # main_shell يبقى كما هو تماماً، فلا تتأثر أي شاشة ببنائها الحالي.
        self.body_shell = ctk.CTkFrame(self, fg_color="transparent")
        self.body_shell.pack(fill="both", expand=True, padx=10, pady=5)

        self.sidebar = ctk.CTkFrame(
            self.body_shell, width=self.sidebar_width(), corner_radius=18,
            border_width=2, border_color="#2e86de",
            fg_color=("#ffffff", "#161a20"))
        self.sidebar.pack(side="right", fill="y", padx=(8, 0), pady=2)
        self.sidebar.pack_propagate(False)

        self.main_shell = ctk.CTkFrame(self.body_shell, fg_color="transparent")
        self.main_shell.pack(side="right", fill="both", expand=True, padx=(0, 6))''')

rep('''    def create_layout(self):''',
    '''    # ترتيب الشاشات في الشريط الجانبي كما طلبه المستخدم
    SIDEBAR_PRIMARY = [
        ("المبيعات",        "🧾", "المبيعات / الصادر"),
        ("صناديق الخياس",   "⚖️", "صناديق الخياس"),
        ("الوارد",          "📥", "الوارد / قبض"),
        ("شاشة الخسائر",    "📉", "شاشة الخسائر"),
        ("صناديق المصنع",   "🏭", "صناديق المصنع"),
    ]
    SIDEBAR_SECONDARY = [
        ("مراحل التصنيع",   "⚙️", "مراحل التصنيع"),
        ("ربح/خسارة الطقم", "📈", "ربح / خسارة الطقم"),
        ("كشف حساب",        "📑", "كشف حساب"),
        ("التقرير الشهري",  "📊", "التقرير الشهري"),
        ("أرشيف الفواتير",  "🗂️", "أرشيف الفواتير"),
        ("القيود اليومية",  "📝", "القيود اليومية"),
        ("الحسابات",        "🌳", "شجرة الحسابات"),
        ("الموردين",        "🚚", "الموردين"),
        ("الرصيد الافتتاحي", "🔢", "الرصيد الافتتاحي"),
    ]

    def sidebar_width(self):
        """عرض الشريط حسب حجم الشاشة: لا يبتلع المساحة على الشاشات الصغيرة"""
        try:
            sw = self.winfo_screenwidth()
        except Exception:
            sw = 1366
        if sw >= 1920:
            return 260
        if sw >= 1440:
            return 236
        return 208

    def ui_scale(self):
        """معامل تكبير موحّد يجعل النظام مريحاً على كل مقاسات الشاشات"""
        try:
            sw = self.winfo_screenwidth()
        except Exception:
            sw = 1366
        if sw >= 1920:
            return 1.0
        if sw >= 1440:
            return 0.94
        return 0.86

    def build_sidebar(self):
        """يبني أزرار التنقّل: بطاقات بيضاء زجاجية بحواف زرقاء لامعة"""
        for w in self.sidebar.winfo_children():
            w.destroy()

        scale = self.ui_scale()
        btn_h = int(46 * scale)
        font_size = max(12, int(14 * scale))

        # رأس الشريط: شعار مصغّر واسم النظام
        head = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(14, 8))
        try:
            logo_img = Image.open(io.BytesIO(base64.b64decode(APP_LOGO_B64)))
            w0, h0 = logo_img.size
            dw = int(150 * scale)
            mini = ctk.CTkImage(light_image=logo_img, dark_image=logo_img,
                                size=(dw, max(1, round(dw * h0 / w0))))
            ctk.CTkLabel(head, image=mini, text="").pack()
        except Exception:
            ctk.CTkLabel(head, text="جاديت", font=("Cairo", 20, "bold"),
                         text_color="#d4af37").pack()

        ttk.Separator(self.sidebar, orient="horizontal").pack(fill="x", padx=12, pady=(4, 8))

        nav = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent")
        nav.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        def make_button(parent, name, icon, label, primary=True):
            """بطاقة زجاجية: خلفية بيضاء وحافة زرقاء تلمع عند المرور"""
            card = ctk.CTkFrame(
                parent, corner_radius=12, border_width=2,
                border_color="#2e86de" if primary else "#7f8c8d",
                fg_color=("#f7fbff", "#1d232c"), height=btn_h)
            card.pack(fill="x", pady=4, padx=2)
            card.pack_propagate(False)

            btn = ctk.CTkButton(
                card, text=f"{icon}  {label}", anchor="e",
                font=ctk.CTkFont(family="Cairo", size=font_size, weight="bold"),
                fg_color="transparent", hover_color=("#dceeff", "#243040"),
                text_color=("#1b2a3a", "#e8eef5"),
                corner_radius=10, height=btn_h - 6,
                command=lambda n=name: self.navigate_to_screen(n))
            btn.pack(fill="both", expand=True, padx=3, pady=3)

            # لمعان الحافة عند المرور بالفأرة
            def glow(_e=None):
                card.configure(border_color="#5dade2", fg_color=("#eaf5ff", "#22303f"))

            def unglow(_e=None):
                card.configure(border_color="#2e86de" if primary else "#7f8c8d",
                               fg_color=("#f7fbff", "#1d232c"))

            for widget in (card, btn):
                widget.bind("<Enter>", glow, add="+")
                widget.bind("<Leave>", unglow, add="+")
            return card

        registered = set(getattr(self.tabview, "_contents", {}).keys())
        for name, icon, label in self.SIDEBAR_PRIMARY:
            if name in registered:
                make_button(nav, name, icon, label, primary=True)

        # زر (أخرى) يفتح باقي الشاشات أسفله
        self._sidebar_more_open = False
        more_holder = ctk.CTkFrame(nav, fg_color="transparent")

        def toggle_more():
            self._sidebar_more_open = not self._sidebar_more_open
            if self._sidebar_more_open:
                more_holder.pack(fill="x", pady=(2, 0))
                btn_more.configure(text="▴  أخرى")
            else:
                more_holder.pack_forget()
                btn_more.configure(text="▾  أخرى")

        more_card = ctk.CTkFrame(nav, corner_radius=12, border_width=2,
                                 border_color="#b8860b",
                                 fg_color=("#fffaf0", "#241f16"), height=btn_h)
        more_card.pack(fill="x", pady=(10, 4), padx=2)
        more_card.pack_propagate(False)
        btn_more = ctk.CTkButton(
            more_card, text="▾  أخرى", anchor="e",
            font=ctk.CTkFont(family="Cairo", size=font_size, weight="bold"),
            fg_color="transparent", hover_color=("#fdf0d5", "#2e2718"),
            text_color=("#6b4e00", "#f0d79a"), corner_radius=10, height=btn_h - 6,
            command=toggle_more)
        btn_more.pack(fill="both", expand=True, padx=3, pady=3)

        more_holder.pack_forget()
        for name, icon, label in self.SIDEBAR_SECONDARY:
            if name in registered:
                make_button(more_holder, name, icon, label, primary=False)

    def create_layout(self):''')


# ==========================================================================
#  ٢) الشاشة الرئيسية: الشعار كبيراً في المساحة الفارغة
# ==========================================================================
rep('''    def build_home_screen(self):
        self.home_frame = ctk.CTkFrame(self.main_shell, fg_color="transparent")''',
    '''    def build_home_screen(self):
        # الشريط الجانبي يُبنى بعد تسجيل كل الشاشات، فيعرف أيّها متاح فعلاً
        try:
            self.build_sidebar()
        except Exception as e:
            log_cloud_error("تعذّر بناء الشريط الجانبي", e)

        self.home_frame = ctk.CTkFrame(self.main_shell, fg_color="transparent")''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الشريط الجانبي على:", SRC)
