# -*- coding: utf-8 -*-
"""
الدفعة العشرون — تسريع الترحيل:
  كل ترحيل كان يُعيد بناء ١٨ جدولاً في كل الشاشات دفعة واحدة، فيبطؤ الترحيل
  وظهور العملية في الجدول. الآن تُحدَّث **الشاشة المعروضة فقط** فوراً، وتُعلَّم
  البقية كـ«تحتاج تحديثاً» فتُحدَّث لحظة الانتقال إليها — فالنتيجة نفسها
  تماماً، لكن بزمن أقل بكثير.

الاستخدام:  python3 patch_client_app_v30.py rageh-1-34-14-cloud.py
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
#  ١) تحديث كسول: الشاشة المعروضة فوراً، والبقية عند فتحها
# ==========================================================================
rep('''        self.refresh_inquiry_table()
        if hasattr(self, 'refresh_inout_tables'):
            self.refresh_inout_tables()
        if hasattr(self, 'calculate_and_refresh_monthly_report'):
            self.calculate_and_refresh_monthly_report()
        if hasattr(self, 'refresh_invoice_archive_table'):
            self.refresh_invoice_archive_table()
        if hasattr(self, 'refresh_journal_entries_table'):
            self.refresh_journal_entries_table()
        if hasattr(self, 'refresh_losses_tab'):
            self.refresh_losses_tab()
        if hasattr(self, 'refresh_chart_of_accounts'):
            self.refresh_chart_of_accounts()
        if hasattr(self, 'refresh_op_ledger_table'):
            self.refresh_op_ledger_table()
        if hasattr(self, 'refresh_casting_table'):
            self.refresh_casting_table()
        if hasattr(self, 'refresh_polish_table'):
            self.refresh_polish_table()
        if hasattr(self, 'refresh_polish_buff_table'):
            self.refresh_polish_buff_table()
        if hasattr(self, 'sales_ops_table_frame'):
            self.refresh_sales_ops_table()
        if getattr(self, 'sets_profit_table_frame', None):
            self.refresh_sets_profit_tab()
        if getattr(self, 'cloud_sync', None):
            self.cloud_sync.sync_now()
        # تحديث جداول الأقسام المضافة ديناميكياً أيضاً حتى تبقى إجمالياتها مطابقة بعد أي تعديل
        if hasattr(self, 'dynamic_stage_widgets'):
            for _stage_name in list(self.dynamic_stage_widgets.keys()):
                self.refresh_generic_stage_table(_stage_name)
        if hasattr(self, 'refresh_suppliers_table'):
            self.refresh_suppliers_table()
        if hasattr(self, 'refresh_sales_table'):
            self.refresh_sales_table()
        if hasattr(self, 'refresh_opening_table'):
            self.refresh_opening_table()
        if hasattr(self, 'refresh_factory_boxes_table'):
            self.refresh_factory_boxes_table()''',
    '''        # تحديث الشاشة المعروضة فقط، وتأجيل البقية إلى لحظة فتحها.
        # الأرصدة أعلاه حُسبت كاملة، فالأرقام صحيحة دائماً — المؤجَّل هو
        # إعادة رسم الجداول غير الظاهرة فقط.
        self.mark_all_screens_dirty()
        self.refresh_visible_screen()

        if getattr(self, 'cloud_sync', None):
            self.cloud_sync.sync_now()''')

rep('''    def refresh_screen_info_bar(self):''',
    '''    # خريطة: اسم الشاشة ← الدوال التي تُعيد بناء جداولها
    SCREEN_REFRESHERS = {
        "مراحل التصنيع": ("refresh_op_ledger_table", "refresh_casting_table",
                          "refresh_polish_table", "refresh_polish_buff_table",
                          "_refresh_dynamic_stages"),
        "صناديق الخياس": ("refresh_inquiry_table",),
        "الوارد/قبض": ("refresh_inout_tables",),
        "المبيعات": ("refresh_sales_table", "refresh_sales_ops_table"),
        "التقرير الشهري": ("calculate_and_refresh_monthly_report",),
        "أرشيف الفواتير": ("refresh_invoice_archive_table",),
        "القيود اليومية": ("refresh_journal_entries_table",),
        "شاشة الخسائر": ("refresh_losses_tab",),
        "شجرة الحسابات": ("refresh_chart_of_accounts", "refresh_suppliers_table"),
        "الرصيد الافتتاحي": ("refresh_opening_table",),
        "صناديق المصنع": ("refresh_factory_boxes_table",),
        "ربح/خسارة الطقم": ("refresh_sets_profit_tab",),
    }

    def _refresh_dynamic_stages(self):
        """يُعيد بناء جداول الأقسام المضافة ديناميكياً"""
        for stage_name in list(getattr(self, "dynamic_stage_widgets", {}).keys()):
            self.refresh_generic_stage_table(stage_name)

    def mark_all_screens_dirty(self):
        """يُعلّم كل الشاشات بأنها تحتاج إعادة رسم عند فتحها"""
        self._dirty_screens = set(self.SCREEN_REFRESHERS.keys())

    def refresh_screen(self, name):
        """يُعيد بناء جداول شاشة واحدة ويزيل علامة الحاجة للتحديث عنها"""
        for fn_name in self.SCREEN_REFRESHERS.get(name, ()):
            fn = getattr(self, fn_name, None)
            if fn is None:
                continue
            try:
                fn()
            except Exception as e:
                log_cloud_error(f"تعذّر تحديث ({name}) عبر {fn_name}", e)
        if hasattr(self, "_dirty_screens"):
            self._dirty_screens.discard(name)

    def refresh_visible_screen(self):
        """يُحدّث الشاشة المفتوحة حالياً فقط — هذا ما يراه المستخدم فعلاً"""
        current = getattr(getattr(self, "tabview", None), "current_screen", None)
        if current:
            self.refresh_screen(current)

    def refresh_pending_screen(self, name):
        """يُحدّث شاشة عند فتحها إن كانت بحاجة لذلك (تحديث كسول)"""
        if name in getattr(self, "_dirty_screens", set()):
            self.refresh_screen(name)

    def refresh_screen_info_bar(self):''')

# التحديث عند الانتقال لأي شاشة
rep('''        self.tabview.show(name)
        self.refresh_screen_info_bar()''',
    '''        # تحديث كسول: الشاشة تُعاد بناؤها الآن فقط إن تغيّرت بياناتها منذ آخر عرض
        self.refresh_pending_screen(name)
        self.tabview.show(name)
        self.refresh_screen_info_bar()''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق التحديث الكسول على:", SRC)
