# -*- coding: utf-8 -*-
"""
الدفعة السادسة عشرة — الجزء الأول:
  ١) خياس المركب: البحث في كل الفترات لا الشهر المعروض فقط (سبب فشل بعض الأرقام)
  ٢) تعديل اسم العمود: كان يُربط مرة واحدة فقط فيتعطّل بعد أول تحديث للجدول
  ٣) التنقل بالأسهم في خانات المصنعين/المركبين
  ٤) تعديل أسماء أعمدة جدول المبيعات بالضغط عليها

الاستخدام:  python3 patch_client_app_v24.py rageh-1-34-14-cloud.py
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
#  ١) خياس المركب: البحث في كل الفترات
# ==========================================================================
rep('''    def get_assembler_khayas_for_set(self, set_number, month=None):
        """الفاقد اللحظي للمركبين لرقم تشغيل معيّن.

        يبحث في كل عمال قسم (المركبين) عن الحركات المسجّلة بهذا رقم التشغيل،
        ويحسب فاقدها اللحظي بنفس معادلة كشف مراحل التصنيع بالضبط:
            صرف − قبض + ليز − (الراجع/عيار)
        فيبقى الرقم مطابقاً لما يراه المستخدم هناك حرفياً.
        """
        set_number = (set_number or "").strip()
        if not set_number:
            return 0.0

        month = month or self.current_display_month''',
    '''    def get_assembler_khayas_for_set(self, set_number, month=None):
        """الفاقد اللحظي للمركبين لرقم تشغيل معيّن.

        يبحث في كل عمال قسم (المركبين) عن الحركات المسجّلة بهذا رقم التشغيل،
        ويحسب فاقدها اللحظي بنفس معادلة كشف مراحل التصنيع بالضبط:
            صرف − قبض + ليز − (الراجع/عيار)
        فيبقى الرقم مطابقاً لما يراه المستخدم هناك حرفياً.

        مهم: البحث يشمل **كل الفترات** لا الشهر المعروض فقط. رقم التشغيل فريد
        عبر الزمن، والتركيب غالباً يسبق البيع بشهر أو أكثر — فتقييد البحث
        بالشهر الحالي كان يُرجع صفراً لكل طقم رُكّب في شهر سابق.
        (تمرير month صراحةً يقيّد البحث بذلك الشهر عند الحاجة)
        """
        set_number = (set_number or "").strip()
        if not set_number:
            return 0.0''')

rep('''            if (inv.get("set_number", "") or "").strip() != set_number:
                continue
            if month and not str(inv.get("التاريخ", "")).startswith(month):
                continue

            d = per_worker.setdefault(inv["الاسم"], {''',
    '''            if (inv.get("set_number", "") or "").strip() != set_number:
                continue
            if month and not str(inv.get("التاريخ", "")).startswith(month):
                continue

            d = per_worker.setdefault(inv["الاسم"], {''')


# ==========================================================================
#  ٢) تعديل اسم العمود: يُربط مع كل إعادة رسم للجدول
# ==========================================================================
rep('''        if not getattr(self, "_ledger_rename_bound", False):
            self.enable_column_rename(self.op_ledger_tree, ledger_key,
                                      on_renamed=self.refresh_op_ledger_table)
            self._ledger_rename_bound = True''',
    '''        # يُربط في كل مرة: الجدول يُعاد إنشاؤه مع كل تحديث، والعلم القديم كان
        # يمنع الربط على الجدول الجديد فيتعطّل تعديل الأسماء بعد أول تحديث
        self.enable_column_rename(self.op_ledger_tree, ledger_key,
                                  on_renamed=self.refresh_op_ledger_table)''')

# منع تكرار الربط على نفس الأداة (الربط يتراكم بـ add="+")
rep('''        tree.bind("<Button-1>", on_header_click, add="+")''',
    '''        # علم على الأداة نفسها لا على النافذة: كل جدول جديد يُربط مرة واحدة،
        # فلا تتراكم الروابط على الجدول نفسه ولا يُحرم الجدول الجديد من الربط
        if not getattr(tree, "_rename_bound", False):
            tree.bind("<Button-1>", on_header_click, add="+")
            tree._rename_bound = True''')


# ==========================================================================
#  ٣) التنقل بالأسهم في خانات المصنعين/المركبين
# ==========================================================================
rep('''        nav_chain = entries_list + [self.op_note]
        for i, f in enumerate(nav_chain[:-1]):
            f.bind("<Return>", lambda e, nxt=nav_chain[i + 1]: nxt.focus_set() or "break")
        nav_chain[-1].bind("<Return>", lambda e: "break")''',
    '''        nav_chain = entries_list + [self.op_note]
        for i, f in enumerate(nav_chain[:-1]):
            f.bind("<Return>", lambda e, nxt=nav_chain[i + 1]: nxt.focus_set() or "break")
        nav_chain[-1].bind("<Return>", lambda e: "break")
        self.bind_arrow_navigation(nav_chain)''')


# ==========================================================================
#  ٤) تعديل أسماء أعمدة جدول المبيعات
# ==========================================================================
rep('''        self.apply_column_labels(self.pending_sales_tree, "pending_sales")
        self.fit_columns_to_content(self.pending_sales_tree, "pending_sales",
                                     min_width=44, max_width=150)''',
    '''        self.apply_column_labels(self.pending_sales_tree, "pending_sales")
        self.fit_columns_to_content(self.pending_sales_tree, "pending_sales",
                                     min_width=44, max_width=150)
        self.enable_column_rename(self.pending_sales_tree, "pending_sales",
                                  on_renamed=self.refresh_pending_sales_table)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة السادسة عشرة على:", SRC)
