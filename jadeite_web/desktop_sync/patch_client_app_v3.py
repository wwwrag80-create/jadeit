# -*- coding: utf-8 -*-
"""
الدفعة الثالثة: زر صغير في كل قسم من مراحل التصنيع لتفعيل/إلغاء تلوين السالب.

  • مفعّل  → الأرقام والخياس السالب في الصف تظهر بالأحمر
  • ملغى   → كل الأرقام بلون واحد

الإعداد محفوظ لكل قسم على حدة في قاعدة البيانات، فيبقى بعد إغلاق البرنامج،
ويظهر تلقائياً في أي قسم يُضاف مستقبلاً بلا تعديل كود.

الاستخدام:  python3 patch_client_app_v3.py rageh-1-34-14-cloud.py
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
#  ١) البنية المشتركة: قراءة/تبديل الإعداد + بناء الزر
# ==========================================================================
rep('''    def get_discount_percentages(self):''',
    '''    # =====================================================================
    # --- تلوين الأرقام السالبة: إعداد مستقل لكل قسم، محفوظ ويبقى بعد الإغلاق ---
    # =====================================================================
    def negative_color_enabled(self, section):
        """هل تلوين السالب مفعّل في هذا القسم؟ (الافتراضي: غير مفعّل)"""
        return self.get_setting(f"neg_color_{section}", "0") == "1"

    def toggle_negative_color(self, section, refresh_callback=None):
        """يبدّل حالة التلوين لهذا القسم ويعيد رسم جدوله فوراً"""
        new_value = "0" if self.negative_color_enabled(section) else "1"
        self.set_setting(f"neg_color_{section}", new_value)
        self.update_negative_color_button(section)
        if refresh_callback:
            try:
                refresh_callback()
            except Exception:
                pass

    def build_negative_color_button(self, parent, section, refresh_callback=None):
        """زر صغير يظهر في أعلى جدول كل قسم (بما فيها الأقسام المضافة لاحقاً)"""
        if not hasattr(self, "neg_color_buttons"):
            self.neg_color_buttons = {}

        btn = ctk.CTkButton(
            parent, text="", font=("Cairo", 12, "bold"), width=105, height=28,
            command=lambda s=section, cb=refresh_callback: self.toggle_negative_color(s, cb))
        btn.pack(side="left", padx=5)

        self.neg_color_buttons[section] = btn
        self.update_negative_color_button(section)
        return btn

    def update_negative_color_button(self, section):
        """يحدّث شكل الزر ليعكس حالته الحالية بوضوح"""
        btn = getattr(self, "neg_color_buttons", {}).get(section)
        if btn is None:
            return
        if self.negative_color_enabled(section):
            btn.configure(text="🔴 تلوين السالب", fg_color="#8b0000", hover_color="#a52a2a")
        else:
            btn.configure(text="⚪ لون واحد", fg_color="#555555", hover_color="#333333")

    def get_discount_percentages(self):''')


# ==========================================================================
#  ٢) جداول الأقسام (الكاستنج/التلميع/البف/المضافة): التلوين حسب إعداد القسم
# ==========================================================================
rep('''    def render_stage_ops_table(self, table_frame, madin_type, qabd_type, height=11,
                               with_trees=False, on_edit=None, totals_label=None,
                               fixed_color=False):''',
    '''    def render_stage_ops_table(self, table_frame, madin_type, qabd_type, height=11,
                               with_trees=False, on_edit=None, totals_label=None,
                               section=None):''')

rep('''            # fixed_color: لون ثابت لكل الصفوف (قسم الصب/الكاستنج فقط).
            # باقي الأقسام تبقى كما كانت: الأحمر عندما يكون الدائن أكبر من المدين.
            tags = () if fixed_color else (("red_tag",) if g["دائن"] > g["مدين"] else ())''',
    '''            # التلوين حسب إعداد القسم نفسه: الأحمر فقط لو كان الخياس سالباً
            # (أي أن القبض أكبر من الصرف) والزر مفعّل في هذا القسم.
            tags = ("red_tag",) if (color_negative and khayas < 0) else ()''')

rep('''        rows_map = {}
        tot_madin = tot_daen = tot_trees = 0.0
        for row_num, name, g in self.collect_stage_ops_rows(madin_type, qabd_type):''',
    '''        color_negative = self.negative_color_enabled(section) if section else False

        rows_map = {}
        tot_madin = tot_daen = tot_trees = 0.0
        for row_num, name, g in self.collect_stage_ops_rows(madin_type, qabd_type):''')

# تمرير اسم القسم من كل جدول
rep('''            self.cast_table_frame, "صرف كاستنج", "قبض كاستنج", height=11, with_trees=True,
            fixed_color=True,''',
    '''            self.cast_table_frame, "صرف كاستنج", "قبض كاستنج", height=11, with_trees=True,
            section="الكاستنج",''')

rep('''            self.polish_table_frame, "صرف تلميع", "قبض تلميع", height=11,''',
    '''            self.polish_table_frame, "صرف تلميع", "قبض تلميع", height=11, section="التلميع",''')

rep('''            self.pbuff_table_frame, "صرف تلميع بف", "قبض تلميع بف", height=11,''',
    '''            self.pbuff_table_frame, "صرف تلميع بف", "قبض تلميع بف", height=11, section="التلميع/البف",''')

rep('''            w["table_frame"], madin_type, qabd_type, height=10,''',
    '''            w["table_frame"], madin_type, qabd_type, height=10, section=stage_name,''')


# ==========================================================================
#  ٣) كشف حركة المصنعين/المركبين: التلوين حسب إعداد كل قسم
# ==========================================================================
rep('''                # المركبين: الأحمر عند الفاقد اللحظي السالب (كما كان)
                row_tags = ("red_tag",) if faqid < 0 else ()''',
    '''                row_tags = ("red_tag",) if (color_negative and faqid < 0) else ()''')

rep('''                # لون واحد ثابت لكل صفوف المصنعين مهما كانت قيمة الفاقد (موجبة أو سالبة)
                row_tags = ()''',
    '''                row_tags = ("red_tag",) if (color_negative and faqid < 0) else ()''')

rep('''        # التجميع في كشف الحركة: برقم الصف لقسمي المصنعين والمركبين، وبالتاريخ لباقي الأقسام (الآلة/المكائن) كما كان
        group_by_row = cat in ("المصنعين", "المركبين")''',
    '''        # تلوين السالب حسب إعداد القسم المعروض حالياً
        color_negative = self.negative_color_enabled(cat)
        self.update_negative_color_button(cat)

        # التجميع في كشف الحركة: برقم الصف لقسمي المصنعين والمركبين، وبالتاريخ لباقي الأقسام (الآلة/المكائن) كما كان
        group_by_row = cat in ("المصنعين", "المركبين")''')


# ==========================================================================
#  ٤) إضافة الزر في أعلى جدول كل قسم
# ==========================================================================
# الكاستنج
rep('''        btn_edit_cast = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_casting_row)''',
    '''        self.build_negative_color_button(table_top, "الكاستنج", self.refresh_casting_table)

        btn_edit_cast = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_casting_row)''')

# التلميع
rep('''        btn_del_pol = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.delete_selected_polish_row)
        btn_del_pol.pack(side="left", padx=5)''',
    '''        btn_del_pol = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.delete_selected_polish_row)
        btn_del_pol.pack(side="left", padx=5)

        self.build_negative_color_button(table_top, "التلميع", self.refresh_polish_table)''')

# التلميع/البف
rep('''        btn_del = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.delete_selected_polish_buff_row)
        btn_del.pack(side="left", padx=5)''',
    '''        btn_del = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.delete_selected_polish_buff_row)
        btn_del.pack(side="left", padx=5)

        self.build_negative_color_button(table_top, "التلميع/البف", self.refresh_polish_buff_table)''')

# الأقسام المضافة ديناميكياً — الزر يظهر فيها تلقائياً
rep('''        btn_del = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=lambda: self.delete_selected_generic_stage_row(stage_name))
        btn_del.pack(side="left", padx=5)''',
    '''        btn_del = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=lambda: self.delete_selected_generic_stage_row(stage_name))
        btn_del.pack(side="left", padx=5)

        self.build_negative_color_button(
            table_top, stage_name, lambda s=stage_name: self.refresh_generic_stage_table(s))''')

# المصنعين/المركبين — زر واحد يتبع القسم المعروض
rep('''        btn_del_row = ctk.CTkButton(ledger_header, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.op_ledger_delete_selected)
        btn_del_row.pack(side="left", padx=5)''',
    '''        btn_del_row = ctk.CTkButton(ledger_header, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.op_ledger_delete_selected)
        btn_del_row.pack(side="left", padx=5)

        # زر التلوين لقسمي المصنعين والمركبين: يتبع القسم المعروض حالياً،
        # وإعداده محفوظ لكل قسم على حدة
        self.btn_ledger_neg_color = ctk.CTkButton(
            ledger_header, text="⚪ لون واحد", font=("Cairo", 12, "bold"), width=105, height=28,
            fg_color="#555555", hover_color="#333333",
            command=lambda: self.toggle_negative_color(self.current_op_cat, self.refresh_op_ledger_table))
        self.btn_ledger_neg_color.pack(side="left", padx=5)

        if not hasattr(self, "neg_color_buttons"):
            self.neg_color_buttons = {}
        for _c in ("المصنعين", "المركبين", "الآلة/المكائن"):
            self.neg_color_buttons[_c] = self.btn_ledger_neg_color''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق زر تلوين السالب على:", SRC)
