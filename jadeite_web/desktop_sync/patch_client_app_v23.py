# -*- coding: utf-8 -*-
"""
الدفعة الخامسة عشرة — إصلاح محاسبي حاسم:
  خياس البوليش وخياس المركب وصافي الطقم كانت تُسجَّل بحالة SETTLED_INOUT
  ظنّاً أنها مستثناة من الحسابات. والحقيقة أن هذه الحالة تعني في هذا النظام
  «مُقفَل لكنه ما زال محسوباً»، فكل فلاتر النظام تقبلها:
        if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
  فكانت تُخصم من الخزينة وتظهر في كشف حسابها — عكس المطلوب تماماً.

  الحل: حالة مستقلة "MEMO" ترفضها كل تلك الفلاتر تلقائياً (لأنها ليست في
  القائمة)، ونسمح بها صراحةً فقط حيث نحتاج قراءتها: إعادة بناء سطور الفاتورة
  عند التعديل، وحذف الفاتورة، وكشوف الطقوم.

الاستخدام:  python3 patch_client_app_v23.py rageh-1-34-14-cloud.py
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
#  ١) تعريف الحالة المعلوماتية
# ==========================================================================
rep('''KHAYAS_MARK_ASSEMBLER = 5.0  # خياس المركب (مأخوذ من مراحل التصنيع، معلوماتي هنا)''',
    '''KHAYAS_MARK_ASSEMBLER = 5.0  # خياس المركب (مأخوذ من مراحل التصنيع، معلوماتي هنا)

# ══════════════════════════════════════════════════════════════════════════
#  حالة السطور المعلوماتية (Memo)
#
#  كل فلاتر النظام المحاسبية مكتوبة هكذا:
#      if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
#  لذلك أي حالة خارج هاتين تُستبعد تلقائياً من: رصيد الخزينة، كشف حسابها،
#  أرصدة المواد، صناديق الخياس، الفواقد، والتقارير — بلا تعديل أي منها.
#
#  تُستخدم لسطور تُحفظ مع الفاتورة للعرض وإعادة البناء فقط:
#  خياس البوليش، وخياس المركب (محمّل أصلاً على صندوق المركبين)، وصافي الطقم.
# ══════════════════════════════════════════════════════════════════════════
MEMO_STATUS = "MEMO"

# الحالات التي تُقرأ عند إعادة بناء فاتورة مبيعات أو حذفها
SALE_READ_STATUSES = ("ACTIVE", "SETTLED_INOUT", MEMO_STATUS)''')


# ==========================================================================
#  ٢) السطور الثلاثة تُسجَّل بحالة MEMO
# ==========================================================================
rep('''                    "settled_status": "SETTLED_INOUT", "trees_count": KHAYAS_MARK_POLISH, "قبل": 0.0, "بعد": 0.0,''',
    '''                    "settled_status": MEMO_STATUS, "trees_count": KHAYAS_MARK_POLISH, "قبل": 0.0, "بعد": 0.0,''')

rep('''                    "settled_status": "SETTLED_INOUT", "trees_count": KHAYAS_MARK_ASSEMBLER,''',
    '''                    "settled_status": MEMO_STATUS, "trees_count": KHAYAS_MARK_ASSEMBLER,''')

rep('''                    "settled_status": "SETTLED_INOUT", "trees_count": KHAYAS_MARK_NET, "قبل": 0.0, "بعد": 0.0,''',
    '''                    "settled_status": MEMO_STATUS, "trees_count": KHAYAS_MARK_NET, "قبل": 0.0, "بعد": 0.0,''')

# تصحيح التعليقات الشارحة
rep('''            # خياس البوليش يُسجَّل ولا يدخل صندوق (خياس التلميع النهائي):
            # حالته SETTLED_INOUT فيُستثنى من مدين الصندوق ومن خصم الخزينة،
            # ويبقى محفوظاً ليُسترجع عند تعديل الفاتورة ويظهر في القالب والصافي.''',
    '''            # خياس البوليش: حالته MEMO فيُستثنى من الخزينة وكشفها ومن صندوق
            # خياس التلميع النهائي، ويبقى محفوظاً للعرض وإعادة البناء والقالب.''')

rep('''            # سطر الصافي: معلوماتي بحت — يُسجَّل بحالة SETTLED_INOUT فيُستثنى من
            # كل حسابات الخزينة والفواقد، ووظيفته الوحيدة عرض الصافي في صندوق
            # خياس الطقوم بلا إعادة حسابه من عدة حركات متفرقة''',
    '''            # سطر الصافي: معلوماتي بحت بحالة MEMO — خارج كل حسابات الخزينة
            # والفواقد، ووظيفته الوحيدة عرض الصافي بلا إعادة حسابه من حركات متفرقة''')

rep('''            # خياس المركب: مصدره حركات المركبين في مراحل التصنيع وهو محمّل هناك
            # أصلاً على صندوق المركبين. يُسجَّل هنا معلوماتياً فقط (SETTLED_INOUT)
            # لحفظه مع الفاتورة وحساب الصافي — تحميله ثانيةً يعني احتساب الفاقد مرتين.''',
    '''            # خياس المركب: مصدره حركات المركبين في مراحل التصنيع وهو محمّل هناك
            # أصلاً على صندوق المركبين. يُسجَّل هنا بحالة MEMO لحفظه مع الفاتورة
            # وحساب الصافي — تحميله ثانيةً يعني احتساب الفاقد مرتين.''')


# ==========================================================================
#  ٣) السماح بقراءة MEMO حيث نحتاجها فعلاً (إعادة البناء والحذف والكشوف)
# ==========================================================================
rep('''    def get_sale_invoice_groups(self, month=None):
        """يجمع حركات المبيعات في فواتير: مفتاح كل فاتورة (رقم الفاتورة اليدوي + التاريخ + الاسم).
        يرجع قائمة قواميس بإجماليات كل فاتورة وقائمة أرقام حركاتها."""
        groups = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"):
                continue''',
    '''    def get_sale_invoice_groups(self, month=None):
        """يجمع حركات المبيعات في فواتير: مفتاح كل فاتورة (رقم الفاتورة اليدوي + التاريخ + الاسم).
        يرجع قائمة قواميس بإجماليات كل فاتورة وقائمة أرقام حركاتها.

        تشمل السطور المعلوماتية (MEMO) لأنها جزء من الفاتورة عرضاً وتعديلاً،
        لكنها مستبعدة من كل الحسابات المالية في مواضعها."""
        groups = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") not in SALE_READ_STATUSES:
                continue''')

rep('''    def get_sale_invoice_records(self, key):
        """كل حركات فاتورة مبيعات واحدة حسب مفتاحها (رقم يدوي + تاريخ + اسم)"""
        manual_no, date_str, name = key
        recs = []
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"):
                continue''',
    '''    def get_sale_invoice_records(self, key):
        """كل حركات فاتورة مبيعات واحدة حسب مفتاحها (رقم يدوي + تاريخ + اسم).

        تشمل السطور المعلوماتية ليُعاد بناؤها عند التعديل، ولتُحذف مع الفاتورة
        فلا تبقى سطور يتيمة بلا فاتورة."""
        manual_no, date_str, name = key
        recs = []
        for inv in self.invoices.values():
            if inv.get("settled_status") not in SALE_READ_STATUSES:
                continue''')

# كشوف الطقوم تقرأ سطور MEMO
rep('''        for inv in self.invoices.values():
            if inv.get("النوع") != "خياس طقوم":
                continue
            if (inv.get("trees_count", 0.0) or 0.0) != KHAYAS_MARK_NET:
                continue''',
    '''        for inv in self.invoices.values():
            if inv.get("النوع") != "خياس طقوم":
                continue
            if (inv.get("trees_count", 0.0) or 0.0) != KHAYAS_MARK_NET:
                continue
            if inv.get("settled_status") not in SALE_READ_STATUSES:
                continue''')

rep('''        for inv in self.invoices.values():
            if inv.get("النوع") != "خياس طقوم":
                continue
            if not str(inv.get("التاريخ", "")).startswith(month):
                continue
            mark = inv.get("trees_count", 0.0) or 0.0''',
    '''        for inv in self.invoices.values():
            if inv.get("النوع") != "خياس طقوم":
                continue
            if inv.get("settled_status") not in SALE_READ_STATUSES:
                continue
            if not str(inv.get("التاريخ", "")).startswith(month):
                continue
            mark = inv.get("trees_count", 0.0) or 0.0''')

# قالب الطباعة يقرأ سطور MEMO
rep('''    def get_invoice_group_data(self, set_number, date_str, name):''',
    '''    SALE_READ_STATUSES_FOR_PRINT = SALE_READ_STATUSES

    def get_invoice_group_data(self, set_number, date_str, name):''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة الخامسة عشرة على:", SRC)
