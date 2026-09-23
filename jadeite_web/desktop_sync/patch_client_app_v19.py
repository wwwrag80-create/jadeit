# -*- coding: utf-8 -*-
"""
الدفعة الثانية عشرة — الجزء الثالث:
  • قسم جديد: (ربح/خسارة الطقم) — عدد الأطقم + صافي/ربح + خسارة، مع كشف تفصيلي
  • حذف عمودي الصافي والخسارة من قسم خياس التلميع النهائي
  • السماح بحذف أي قسم من صناديق الخياس + إزالة قسم الصب نهائياً
  • مراحل التصنيع: مدين ← صرف، دائن ← قبض (عدا المصنعين والمركبين)

الاستخدام:  python3 patch_client_app_v19.py rageh-1-34-14-cloud.py
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
#  ١) حذف عمودي الصافي والخسارة من قسم خياس التلميع النهائي
# ==========================================================================
rep('''        show_net = (cat == "خياس الطقوم")''', '''        show_net = False''')


# ==========================================================================
#  ٢) قسم (ربح/خسارة الطقم)
# ==========================================================================
rep('''    def get_all_stage_categories(self):''',
    '''    PROFIT_SECTION = "ربح/خسارة الطقم"

    def render_sets_profit_inquiry(self):
        """قسم (ربح/خسارة الطقم): عدد الأطقم وصافي الربح والخسارة لكل شهر.

        الفصل المحاسبي: الطقم ذو الصافي الموجب يدخل عمود (صافي/ربح)، وذو الصافي
        السالب يخرج منه كلياً ويظهر في عمود (خسارة) بقيمته المطلقة — فلا يُقاصّ
        ربح طقم خسارة طقم آخر داخل رقم واحد يخفي الحقيقة.
        """
        header_row = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        header_row.pack(side="top", fill="x", padx=4, pady=(0, 4))
        ctk.CTkLabel(header_row,
                     text="اضغط على أي شهر لعرض تفاصيل أطقمه (الضغط على عمود الخسارة يعرض الأطقم الخاسرة فقط)",
                     font=("Cairo", 11), text_color="#8b8f95").pack(side="right", padx=6)

        tree_container = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        tree_container.pack(side="top", fill="both", expand=True)

        columns = ("الشهر والسنة", "عدد الأطقم", "صافي/ربح", "خسارة")
        self.tree = self.create_standard_treeview(tree_container, columns, height=18)
        for col in columns:
            self.tree.column(col, width=180, anchor="center")
        self.tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self._on_sets_profit_click)

        months = sorted({str(inv.get("التاريخ", ""))[:7] for inv in self.invoices.values()
                         if inv.get("النوع") == "خياس طقوم"
                         and (inv.get("trees_count", 0.0) or 0.0) == KHAYAS_MARK_NET
                         and inv.get("التاريخ")})

        self.stage_month_rows_map = {}
        g_count = 0
        g_net = g_loss = 0.0
        rows_cache = []

        for m in months:
            rows = self.get_sets_net_rows(m)
            net_sum = round(sum(r[1] for r in rows), 2)
            loss_sum = round(sum(r[2] for r in rows), 2)
            g_count += len(rows)
            g_net = round(g_net + net_sum, 2)
            g_loss = round(g_loss + loss_sum, 2)

            vals = (m, str(len(rows)),
                    f"{net_sum:.2f}" if net_sum else "-",
                    f"{loss_sum:.2f}" if loss_sum else "-")
            row_id = self.tree.insert("", "end", values=vals)
            self.stage_month_rows_map[row_id] = m
            rows_cache.append(vals)

        totals = None
        if months:
            totals = ("الإجمالي", str(g_count),
                      f"{g_net:.2f}" if g_net else "-",
                      f"{g_loss:.2f}" if g_loss else "-")
            self.tree.insert("", "end", values=totals, tags=("total_tag",))

        self._stage_monthly_rows_cache = rows_cache
        self._stage_monthly_columns_cache = columns
        self._stage_monthly_totals_cache = totals

        cur_rows = self.get_sets_net_rows(self.current_display_month)
        cur_net = round(sum(r[1] for r in cur_rows), 2)
        cur_loss = round(sum(r[2] for r in cur_rows), 2)

        if hasattr(self, 'lbl_dash_alert'):
            self.lbl_dash_alert.configure(
                text=f"صافي أرباح الأطقم ({self.current_display_month}): {en(cur_net)} جم")
        self.last_computed_actual_khayas = 0.0
        self.lbl_section_summary.configure(
            text=(f"(ربح/خسارة الطقم) لشهر ({self.current_display_month}): "
                  f"عدد الأطقم {len(cur_rows)}  |  صافي/ربح {en(cur_net)}  |  "
                  f"خسارة {en(cur_loss)} جم"))

    def _on_sets_profit_click(self, event=None):
        """الضغط على صف شهر يفتح كشف أطقمه؛ وعلى عمود الخسارة يفتح الخاسرة فقط"""
        sel = self.tree.selection()
        if not sel:
            return
        month = self.stage_month_rows_map.get(sel[0])
        if not month:
            return
        col_name = ""
        if event is not None:
            try:
                cols = self.tree["columns"]
                idx = int(self.tree.identify_column(event.x).replace("#", "")) - 1
                col_name = cols[idx] if 0 <= idx < len(cols) else ""
            except (ValueError, IndexError):
                col_name = ""
        self.show_sets_net_detail(month, losses_only=(col_name == "خسارة"))

    def get_all_stage_categories(self):''')

# زر القسم في شاشة صناديق الخياس
rep('''            ("خياس الطقوم", "💍 خياس الطقوم"),''',
    '''            ("خياس الطقوم", "💍 خياس التلميع النهائي"),
            ("ربح/خسارة الطقم", "📈 ربح/خسارة الطقم"),''')

# التوجيه للعارض الصحيح
rep('''        if self.current_view_cat in self.get_all_stage_categories():
            self.render_stage_monthly_inquiry()
            return''',
    '''        if self.current_view_cat == self.PROFIT_SECTION:
            self.render_sets_profit_inquiry()
            return

        if self.current_view_cat in self.get_all_stage_categories():
            self.render_stage_monthly_inquiry()
            return''')


# ==========================================================================
#  ٣) السماح بحذف أي صندوق خياس + إزالة قسم الصب
# ==========================================================================
rep('''    def get_deletable_khayas_boxes(self):
        """الصناديق القابلة للحذف: المضافة يدوياً فقط.

        الصناديق الأساسية (الكاستنج/التلميع/البف/خياس الطقوم) مرتبطة بمنطق
        محاسبي ثابت في النظام، وحذفها يكسر شاشات وحسابات قائمة.
        """
        return list(self.categories.get("أقسام_خياس_إضافية", []))''',
    '''    def get_deletable_khayas_boxes(self):
        """كل صناديق الخياس قابلة للحذف — الأساسية والمضافة.

        تنبيه: حذف صندوق أساسي يحذف حركاته ومسترجعه ويغيّر رصيد الخزينة
        وإجمالي الفواقد، ويُخفي شاشته من مراحل التصنيع. نافذة الحذف تعرض
        عدد حركاته وتطلب تأكيدين قبل التنفيذ.
        """
        return list(self.get_all_stage_categories())''')

rep('''    def ensure_default_khayas_boxes(self):
        """ينشئ صندوق (الصب) تلقائياً لو لم يكن موجوداً.

        يُعامل كأي صندوق خياس: صرف/قبض/مسترجع/إقفال، ويظهر في مراحل التصنيع
        وصناديق الخياس وشاشة الخسائر والرصيد الحالي — كالكاستنج والبوليش تماماً.
        """
        DEFAULTS = ["الصب"]''',
    '''    def ensure_default_khayas_boxes(self):
        """لا صناديق تُنشأ تلقائياً بعد الآن (أُلغي إنشاء قسم الصب).

        تُركت الدالة لأن نقاط استدعائها قائمة، وإفراغ قائمتها أوضح وأأمن من
        حذف الاستدعاءات المتفرقة.
        """
        DEFAULTS = []''')

# إزالة قسم الصب من قواعد العملاء الحالية
rep('''        self.ensure_default_khayas_boxes()''',
    '''        self.ensure_default_khayas_boxes()
        self.remove_legacy_casting_box()''')

rep('''    def get_all_stage_categories(self):''',
    '''    def remove_legacy_casting_box(self):
        """يزيل قسم (الصب) الذي كان يُنشأ تلقائياً في نسخة سابقة.

        الحذف يقتصر على القسم الفارغ: لو كانت عليه حركات مسجّلة نُبقيه ونُنبّه،
        لأن حذف حركات محاسبية بلا علم المستخدم غير مقبول.
        """
        try:
            if "الصب" not in self.categories.get("أقسام_خياس_إضافية", []):
                return
            if self.count_box_transactions("الصب") > 0:
                return   # عليه حركات: يبقى، ويستطيع المستخدم حذفه يدوياً
            self.categories["أقسام_خياس_إضافية"].remove("الصب")
            self.categories.pop("الصب", None)
            self.delete_worker_from_db("الصب", "أقسام_خياس_إضافية")
        except Exception as e:
            log_cloud_error("تعذّر إزالة قسم الصب القديم", e)

    def get_all_stage_categories(self):''')


# ==========================================================================
#  ٤) مراحل التصنيع: مدين ← صرف، دائن ← قبض (عدا المصنعين والمركبين)
# ==========================================================================
rep('''        name_col = ("الاسم",) if show_name else ()
        if with_trees:
            cols = ("الصف",) + name_col + ("مدين", "دائن", "الخياس", "عدد الأشجار", "خياس كل شجرة", "البيان")
        else:
            cols = ("الصف",) + name_col + ("مدين", "دائن", "الخياس", "البيان")''',
    '''        name_col = ("الاسم",) if show_name else ()
        # هذه الأقسام عمليات صرف وقبض فعلية، فالتسمية المحاسبية الأوضح للمستخدم
        # هي (صرف/قبض) لا (مدين/دائن) — والمصنعون والمركبون لهم جدولهم المستقل
        if with_trees:
            cols = ("الصف",) + name_col + ("صرف", "قبض", "الخياس", "عدد الأشجار", "خياس كل شجرة", "البيان")
        else:
            cols = ("الصف",) + name_col + ("صرف", "قبض", "الخياس", "البيان")''')

rep('''            txt = f"الإجماليات — مدين: {tot_madin:.2f}  |  دائن: {tot_daen:.2f}  |  الخياس: {tot_khayas:.2f} جم"''',
    '''            txt = f"الإجماليات — صرف: {tot_madin:.2f}  |  قبض: {tot_daen:.2f}  |  الخياس: {tot_khayas:.2f} جم"''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الثالث من الدفعة الثانية عشرة على:", SRC)
