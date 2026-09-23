# -*- coding: utf-8 -*-
"""
الدفعة الرابعة: شريط (الرصيد الحالي) = رصيد الخزينة + كل الذهب في صناديق الخياس.

  رصيد الخزينة  = الذهب الموجود فعلياً في الخزينة (بعد خصم ما خرج للورش)
  الرصيد الحالي = الخزينة + ما هو عند المصنعين والمركبين والكاستنج والتلميع
                  وأي صندوق خياس آخر — أي إجمالي الذهب الذي نملكه فعلياً

الشريطان بنفس التنسيق، والرصيد الحالي أسفل رصيد الخزينة مباشرة.

الاستخدام:  python3 patch_client_app_v4.py rageh-1-34-14-cloud.py
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
#  ١) دالة حساب إجمالي الذهب
# ==========================================================================
rep('''    def get_box_closed_total(self, cat):''',
    '''    def get_total_gold_balance(self):
        """إجمالي الذهب الذي نملكه فعلياً الآن = الخزينة + كل ما هو خارجها في الورش.

        رصيد الخزينة يخصم الذهب الذي خرج لصناديق الخياس (المصنعين، المركبين،
        الكاستنج، التلميع، وأي صندوق آخر) لأنه لم يعد بين يدينا في الخزينة.
        لكنه ما زال ذهبنا. هذه الدالة تعيده لنعرف الإجمالي الحقيقي.

        الخياس المُقفل لا يُحتسب: عند إقفاله يُرحَّل لحساب الخسائر بقيد مزدوج،
        فيصبح فاقداً فعلياً لا ذهباً نملكه.
        """
        total = getattr(self, "current_treasury_balance", 0.0)

        # الذهب عند المصنعين والمركبين (الفاقد اللحظي غير المُقفل)
        total += self.get_actual_section_khayas("المصنعين")
        total += self.get_actual_section_khayas("المركبين")

        # كل صناديق الخياس: الثابتة والمضافة حديثاً — تُقرأ ديناميكياً
        # فأي صندوق يُضاف مستقبلاً يدخل في الحساب تلقائياً بلا تعديل كود
        for cat in self.get_all_stage_categories():
            total += self.get_box_khayas_cumulative(cat)

        return round(total, 2)

    def get_gold_balance_breakdown(self):
        """تفصيل الرصيد الحالي لعرضه عند الطلب (تلميح الشريط)"""
        parts = [("الخزينة", getattr(self, "current_treasury_balance", 0.0)),
                 ("المصنعين", self.get_actual_section_khayas("المصنعين")),
                 ("المركبين", self.get_actual_section_khayas("المركبين"))]
        for cat in self.get_all_stage_categories():
            parts.append((self.get_display_label(cat), self.get_box_khayas_cumulative(cat)))
        return parts

    def get_box_closed_total(self, cat):''')


# ==========================================================================
#  ٢) الشريطان في أعلى الشاشة
# ==========================================================================
rep('''        self.lbl_live_treasury = ctk.CTkLabel(treasury_display_frame, text="رصيد الخزينة الحالي: 0.00 جم", font=ctk.CTkFont(family="Cairo", size=20, weight="bold"), text_color="#d4af37")
        self.lbl_live_treasury.pack()''',
    '''        # ====== شريط رصيد الخزينة ======
        treasury_bar = ctk.CTkFrame(treasury_display_frame, corner_radius=10,
                                     fg_color=("#f3e6c0", "#2a2318"), border_width=2, border_color="#d4af37")
        treasury_bar.pack(fill="x", pady=(0, 4))

        self.lbl_live_treasury = ctk.CTkLabel(treasury_bar, text="رصيد الخزينة الحالي: 0.00 جم", font=ctk.CTkFont(family="Cairo", size=19, weight="bold"), text_color="#d4af37")
        self.lbl_live_treasury.pack(padx=16, pady=6)

        # ====== شريط الرصيد الحالي (الخزينة + كل صناديق الخياس) ======
        total_bar = ctk.CTkFrame(treasury_display_frame, corner_radius=10,
                                  fg_color=("#d9ecd9", "#16261a"), border_width=2, border_color="#2ecc71")
        total_bar.pack(fill="x", pady=(0, 6))

        self.lbl_total_gold = ctk.CTkLabel(total_bar, text="الرصيد الحالي: 0.00 جم", font=ctk.CTkFont(family="Cairo", size=19, weight="bold"), text_color="#2ecc71")
        self.lbl_total_gold.pack(padx=16, pady=6)
        self.lbl_total_gold.bind("<Button-1>", lambda e: self.show_gold_balance_breakdown())

        ctk.CTkLabel(treasury_display_frame, text="(الخزينة + الذهب عند الورش — اضغط للتفصيل)",
                     font=ctk.CTkFont(family="Cairo", size=10), text_color="#8b8f95").pack(pady=(0, 4))''')


# ==========================================================================
#  ٣) تحديث الشريط مع كل إعادة حساب
# ==========================================================================
rep('''        if hasattr(self, 'lbl_gems_stones_balance'):
            self.lbl_gems_stones_balance.configure(text=f"رصيد فصوص وأحجار الحالي: {self.get_material_balance('فصوص وأحجار'):.2f}")''',
    '''        # الرصيد الحالي: يُحسب بعد الخزينة مباشرة لأنه يعتمد عليها
        self.current_total_gold = self.get_total_gold_balance()
        if hasattr(self, 'lbl_total_gold'):
            self.lbl_total_gold.configure(text=f"الرصيد الحالي: {self.current_total_gold:.2f} جم")

        if hasattr(self, 'lbl_gems_stones_balance'):
            self.lbl_gems_stones_balance.configure(text=f"رصيد فصوص وأحجار الحالي: {self.get_material_balance('فصوص وأحجار'):.2f}")''')


# ==========================================================================
#  ٤) نافذة تفصيل الرصيد
# ==========================================================================
rep('''    def get_total_gold_balance(self):''',
    '''    def show_gold_balance_breakdown(self):
        """يعرض من أين تكوّن الرصيد الحالي، ليطمئن المستخدم أن الرقم مفهوم لا سحري"""
        parts = self.get_gold_balance_breakdown()
        total = round(sum(v for _, v in parts), 2)

        win = ctk.CTkToplevel(self)
        win.title("تفصيل الرصيد الحالي")
        win.geometry("430x520")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="💰 تفصيل الرصيد الحالي", font=("Cairo", 18, "bold"),
                     text_color="#2ecc71").pack(pady=(16, 4))
        ctk.CTkLabel(win, text="إجمالي الذهب الذي نملكه الآن، أينما كان",
                     font=("Cairo", 11), text_color="#8b8f95").pack(pady=(0, 10))

        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=6)

        for label, value in parts:
            if abs(value) < 0.005:
                continue      # لا نزحم القائمة بأصفار
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, font=("Cairo", 13, "bold"), anchor="e").pack(side="right")
            ctk.CTkLabel(row, text=f"{value:.2f} جم", font=("Cairo", 13),
                         text_color="#d4af37" if value >= 0 else "#e74c3c").pack(side="left")

        sep = ctk.CTkFrame(win, height=2, fg_color="#d4af37")
        sep.pack(fill="x", padx=18, pady=8)

        ctk.CTkLabel(win, text=f"الإجمالي: {total:.2f} جم", font=("Cairo", 17, "bold"),
                     text_color="#2ecc71").pack(pady=(0, 6))
        ctk.CTkLabel(
            win,
            text="ملاحظة: الخياس المُقفل لا يظهر هنا لأنه رُحّل لحساب الخسائر\\nوأصبح فاقداً فعلياً لا ذهباً نملكه.",
            font=("Cairo", 10), text_color="#8b8f95", justify="center").pack(pady=(0, 10))

        ctk.CTkButton(win, text="إغلاق", font=("Cairo", 14, "bold"), width=140, height=38,
                      command=win.destroy).pack(pady=(0, 14))

    def get_total_gold_balance(self):''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم إضافة شريط الرصيد الحالي إلى:", SRC)
