# -*- coding: utf-8 -*-
"""
الدفعة الثانية عشرة — الجزء الأول:
  أ) صندوق خياس الطقوم: خياس التلميع النهائي فقط (خياس البوليش يخرج منه)
  ب) المصنعين/المركبين: فصل الخياس الفعلي إلى:
        • خياس فاقد (٨/٤)  = إجمالي مسموح ٨ + إجمالي مسموح ٤
        • خياس العمال      = مجموع الأرصدة السالبة في عمود الخياس
     والإقفال يقفلهما معاً، وشاشة الخسائر تعرضهما مفصولين.
  ج) إعادة تسمية القسم: خياس الطقوم ← خياس التلميع النهائي

الاستخدام:  python3 patch_client_app_v17.py rageh-1-34-14-cloud.py
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
#  أ) خياس البوليش يخرج من صندوق خياس الطقوم
# ==========================================================================
rep('''            # خياس البوليش: نفس معاملة خياس التلميع النهائي محاسبياً (كلاهما فاقد
            # يُرحّل لصندوق خياس الطقوم)، ويُميَّز بعلامة ليُفصل في العرض والتعديل
            if khayas_polish_v > 0:''',
    '''            # خياس البوليش يُسجَّل ولا يدخل صندوق (خياس التلميع النهائي):
            # حالته SETTLED_INOUT فيُستثنى من مدين الصندوق ومن خصم الخزينة،
            # ويبقى محفوظاً ليُسترجع عند تعديل الفاتورة ويظهر في القالب والصافي.
            if khayas_polish_v > 0:''')

rep('''                    "النوع": "خياس طقوم", "الوزن": khayas_polish_v, "البيان": "خياس بوليش",
                    "settled_status": "ACTIVE", "trees_count": KHAYAS_MARK_POLISH, "قبل": 0.0, "بعد": 0.0,''',
    '''                    "النوع": "خياس طقوم", "الوزن": khayas_polish_v, "البيان": "خياس بوليش",
                    "settled_status": "SETTLED_INOUT", "trees_count": KHAYAS_MARK_POLISH, "قبل": 0.0, "بعد": 0.0,''')


# ==========================================================================
#  ب) فصل خياس المصنعين/المركبين إلى: فاقد (٨/٤) + خياس العمال
# ==========================================================================
rep('''    def get_actual_section_khayas(self, cat_name, target_month=None, include_settled=False):''',
    '''    def get_section_khayas_split(self, cat_name, target_month=None, include_settled=False):
        """يفصل خياس قسم المصنعين/المركبين إلى مكوّنيه المحاسبيين:

          • خياس فاقد (٨/٤): إجمالي (مسموح ٨) + (مسموح ٤) — وهو الفاقد المسموح
            به نظامياً على المفنش، لا يُحمَّل على العامل.
          • خياس العمال: مجموع الأرصدة السالبة فقط في عمود الخياس — أي ما زاد
            عن المسموح فعلاً عند العمال. الأرصدة الموجبة لا تُقاصّ السالبة،
            لأن فائض عامل لا يُلغي عجز عامل آخر محاسبياً.

        يرجع: (خياس_فاقد_٨_٤، خياس_العمال، المجموع)
        """
        allowance = workers = 0.0
        for n in self.categories.get(cat_name, []):
            res = self.calculate_single_ledger(n, cat_name, target_month=target_month,
                                                include_settled=include_settled)
            allowance += res.get("مسموح 8", 0.0) + res.get("مسموح 4", 0.0)
            khayas_val = res.get("الخياس", 0.0)
            if khayas_val < 0:
                workers += abs(khayas_val)

        allowance = round(allowance, 2)
        workers = round(workers, 2)
        return allowance, workers, round(allowance + workers, 2)

    def get_actual_section_khayas(self, cat_name, target_month=None, include_settled=False):''')

# الشريط البارز: عرض المكوّنين
rep('''        self.lbl_section_summary.configure(text=f"إجمالي الخياس الفعلي لـ ({self.current_view_cat}): {final_actual_khayas:.2f} جم")''',
    '''        if self.current_view_cat in ("المصنعين", "المركبين"):
            allow_k, workers_k, total_k = self.get_section_khayas_split(self.current_view_cat)
            self.lbl_section_summary.configure(
                text=(f"({self.get_display_label(self.current_view_cat)}) — "
                      f"خياس فاقد (٨/٤): {en(allow_k)}  |  "
                      f"خياس العمال: {en(workers_k)}  |  "
                      f"الإجمالي: {en(total_k)} جم"))
        else:
            self.lbl_section_summary.configure(text=f"إجمالي الخياس الفعلي لـ ({self.current_view_cat}): {final_actual_khayas:.2f} جم")''')


# ==========================================================================
#  ب-٢) الإقفال يقفل المكوّنين معاً بقيدين منفصلين
# ==========================================================================
rep('''    def close_khayas_box(self, cat):
        current = self.get_current_unclosed_khayas(cat)
        display_name = self.get_display_label(cat)
        if current == 0:''',
    '''    def _post_closing_entry(self, box_account_name, amount, bayan, full_dt):
        """يسجّل قيد إقفال مزدوجاً (مدين الخسائر / دائن الصندوق أو العكس).

        الفصل في قيود منفصلة مقصود: يظهر في كشف حساب الخسائر سبب كل مبلغ
        (فاقد ٨/٤ أم خياس عمال) بدل مبلغ واحد مجمّع لا يُفسَّر لاحقاً.
        """
        if abs(amount) < 0.005:
            return
        entry_ref = f"JE-{self.invoice_counter + 1}"
        if amount > 0:
            from_name, to_name = "حساب الخسائر", box_account_name
        else:
            from_name, to_name = box_account_name, "حساب الخسائر"
        value = abs(amount)

        for name, op_type in ((from_name, "قيد يومي مدين"), (to_name, "قيد يومي دائن")):
            self.invoice_counter += 1
            inv = {"رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                   "النوع": op_type, "الوزن": value, "البيان": bayan, "settled_status": "ACTIVE",
                   "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": entry_ref}
            self.invoices[self.invoice_counter] = inv
            self.save_invoice_to_db(self.invoice_counter, inv)

    def close_split_khayas_box(self, cat):
        """إقفال خياس المصنعين/المركبين بمكوّنيه المفصولين في قيدين مستقلين"""
        display_name = self.get_display_label(cat)
        allow_k, workers_k, total_k = self.get_section_khayas_split(cat)
        already_closed = self.get_box_closed_total(cat)
        remaining = round(total_k - already_closed, 2)

        if abs(remaining) < 0.005:
            messagebox.showinfo("لا يوجد خياس",
                                f"لا يوجد خياس غير مُقفل حالياً لصندوق ({display_name}).")
            return

        if not messagebox.askyesno(
                "تأكيد الإقفال",
                f"إقفال خياس صندوق ({display_name}):\\n\\n"
                f"• خياس فاقد (٨/٤): {en(allow_k)} جم\\n"
                f"• خياس العمال: {en(workers_k)} جم\\n"
                f"• الإجمالي: {en(total_k)} جم\\n"
                f"• سبق إقفاله: {en(already_closed)} جم\\n"
                f"• المتبقّي للإقفال الآن: {en(remaining)} جم\\n\\n"
                "سيُرحَّل المتبقّي لحساب الخسائر بقيدين منفصلين. هل تريد المتابعة؟"):
            return

        box_account_name = self.get_box_account_name(cat)
        full_dt = f"{self.get_smart_default_date()} {datetime.datetime.now().strftime('%H:%M:%S')}"

        # نوزّع المتبقّي على المكوّنين بنسبتهما، فلا يُقفل شيء أُقفل سابقاً
        if total_k > 0:
            share_allow = round(remaining * (allow_k / total_k), 2)
        else:
            share_allow = 0.0
        share_workers = round(remaining - share_allow, 2)

        self._post_closing_entry(box_account_name, share_allow, "إقفال خياس فاقد (٨/٤)", full_dt)
        self._post_closing_entry(box_account_name, share_workers, "إقفال خياس العمال", full_dt)

        self.recalculate_all()
        messagebox.showinfo(
            "تم الإقفال",
            f"تم إقفال خياس صندوق ({display_name}):\\n"
            f"فاقد (٨/٤): {en(share_allow)} جم  |  خياس العمال: {en(share_workers)} جم")
        self.refresh_losses_tab()

    def close_khayas_box(self, cat):
        # المصنعون والمركبون لهم مكوّنان مفصولان، فيُقفلان بمسار مستقل
        if cat in ("المصنعين", "المركبين"):
            return self.close_split_khayas_box(cat)

        current = self.get_current_unclosed_khayas(cat)
        display_name = self.get_display_label(cat)
        if current == 0:''')


# ==========================================================================
#  ب-٣) شاشة الخسائر: بطاقتا المصنعين/المركبين تعرضان المكوّنين
# ==========================================================================
rep('''    def get_current_unclosed_khayas(self, cat):''',
    '''    def get_box_breakdown_text(self, cat):
        """نص تفصيلي لبطاقة الصندوق في شاشة الخسائر"""
        if cat not in ("المصنعين", "المركبين"):
            return ""
        allow_k, workers_k, _ = self.get_section_khayas_split(cat)
        return f"فاقد (٨/٤): {en(allow_k)}   |   خياس العمال: {en(workers_k)}"

    def get_current_unclosed_khayas(self, cat):''')


# ==========================================================================
#  ج) إعادة التسمية: خياس الطقوم ← خياس التلميع النهائي
# ==========================================================================
rep('''    def get_display_label(self, cat):''',
    '''    BOX_DISPLAY_OVERRIDES = {"خياس الطقوم": "خياس التلميع النهائي"}

    def get_display_label(self, cat):''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة الثانية عشرة على:", SRC)
