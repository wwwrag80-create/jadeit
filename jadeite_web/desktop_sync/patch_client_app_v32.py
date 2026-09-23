# -*- coding: utf-8 -*-
"""
الدفعة الثانية والعشرون — فصل (تاريخ العملية) عن (الفترة المحاسبية):

  المطلوب: أنت في فترة ٢٠٢٦-٠٨ واليوم ٢٠٢٦-٠٩-٠١ ← العملية تُسجَّل وتُعرض
  بتاريخها الحيّ ٢٠٢٦-٠٩-٠١ بوقته الفعلي، لكنها **تُثبَّت في فترة ٢٠٢٦-٠٨**
  ولا تظهر في فترة ٢٠٢٦-٠٩.

  التنفيذ: عمود جديد (period) يحمل الفترة المحاسبية صراحةً، ويبقى (التاريخ)
  هو تاريخ العملية الحقيقي. وكل فلاتر الفترة في النظام تقرأ الفترة من هذا
  العمود، فإن غاب (بيانات قديمة) تُشتق من التاريخ كما كان — فتبقى بيانات
  العملاء الحالية تعمل بلا أي ترحيل.

الاستخدام:  python3 patch_client_app_v32.py rageh-1-34-14-cloud.py
"""
import io
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(SRC, encoding="utf-8").read()


def rep(old, new, count=1):
    global src
    n = src.count(old)
    assert n == count, "MISMATCH (%d != %d):\n%s" % (n, count, old[:220])
    src = src.replace(old, new)


# ==========================================================================
#  ١) دوال قراءة الفترة
# ==========================================================================
rep('''    def get_smart_default_date(self):''',
    '''    @staticmethod
    def inv_period(inv):
        """الفترة المحاسبية لحركة: العمود الصريح إن وُجد، وإلا تُشتق من تاريخها.

        الاشتقاق ضروري لتوافق بيانات العملاء المسجّلة قبل هذا التحديث، حيث
        كانت الفترة = شهر التاريخ دائماً.
        """
        period = (inv.get("period") or "").strip()
        if period:
            return period
        return str(inv.get("التاريخ", ""))[:7]

    @classmethod
    def inv_in_period(cls, inv, month):
        """هل تنتمي الحركة للفترة المطلوبة؟ (فترة فارغة = بلا تقييد)"""
        if not month:
            return True
        return cls.inv_period(inv) == month

    def get_smart_default_date(self):''')


# ==========================================================================
#  ٢) التاريخ الافتراضي = تاريخ اليوم الحيّ دائماً
# ==========================================================================
rep('''        now = datetime.datetime.now()
        if self.current_display_month == now.strftime("%Y-%m"):
            return now.strftime("%Y-%m-%d")

        try:
            year, month = (int(x) for x in self.current_display_month.split("-")[:2])
            last_day = calendar.monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-{min(now.day, last_day):02d}"
        except (ValueError, IndexError):
            return f"{self.current_display_month}-01"''',
    '''        # التاريخ هو تاريخ اليوم الحقيقي دائماً، مهما كانت الفترة المعروضة.
        # أما انتماء العملية للفترة فيحدّده عمود (period) لا التاريخ.
        return datetime.datetime.now().strftime("%Y-%m-%d")''')

rep('''    def get_smart_default_date(self):
        """تاريخ العملية الافتراضي: يوم اليوم داخل الفترة المعروضة.

        القاعدة المحاسبية: العملية تُثبَّت في **الفترة التي يعمل فيها المستخدم**،
        لا في شهر تاريخ الجهاز. فلو كان اليوم ٢٠٢٦-٠٩-٠١ والمستخدم في فترة
        ٢٠٢٦-٠٨، تُسجَّل بتاريخ ٢٠٢٦-٠٨-٠١ — نفس رقم اليوم، داخل فترته.
        ولو تجاوز رقم اليوم أيام ذلك الشهر (مثل ٣١ في شهر من ٣٠ يوماً) يُثبَّت
        على آخر يوم فيه بدل تاريخ غير موجود.

        وهو يُقرأ لحظياً في كل استدعاء، فيتتبّع تغيّر تاريخ الجهاز فوراً.
        """''',
    '''    def get_smart_default_date(self):
        """تاريخ العملية الافتراضي: **تاريخ اليوم الحقيقي** دائماً.

        العملية تُعرض وتُسجَّل بتاريخها الحيّ (مثلاً ٢٠٢٦-٠٩-٠١)، بينما تُثبَّت
        محاسبياً في الفترة المعروضة (مثلاً ٢٠٢٦-٠٨) عبر عمود (period) المستقل.
        فلا يُزوَّر التاريخ ليدخل الفترة، ولا تُحسب العملية في فترة غير فترتها.
        """''')

rep('''    def get_operation_datetime(self):
        """تاريخ ووقت العملية: التاريخ داخل الفترة المعروضة، والوقت حيٌّ دائماً"""
        return f"{self.get_smart_default_date()} {datetime.datetime.now().strftime('%H:%M:%S')}"''',
    '''    def get_operation_datetime(self):
        """تاريخ ووقت العملية الحقيقيان (الفترة تُحدَّد بعمود period لا بالتاريخ)"""
        return f"{self.get_smart_default_date()} {datetime.datetime.now().strftime('%H:%M:%S')}"

    def stamp_period(self, inv_data, date_value=None):
        """يختم الحركة بالفترة المحاسبية التي تنتمي إليها.

        الأساس: الفترة المعروضة وقت التسجيل. ولو كان تاريخ الحركة يقع داخل
        فترة معروضة أخرى (كتعديل حركة قديمة) تُترك فترتها كما هي.
        """
        if not inv_data.get("period"):
            inv_data["period"] = self.current_display_month
        return inv_data''')


# ==========================================================================
#  ٣) تخزين العمود الجديد
# ==========================================================================
rep('''                INSERT OR REPLACE INTO invoices (invoice_id, date_time, name, op_type, weight, before_w, after_w, note, settled_status, trees_count, set_number, row_number, manual_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (inv_id, inv_data["التاريخ"], inv_data["الاسم"], inv_data["النوع"], 
                  inv_data["الوزن"], inv_data.get("قبل", 0.0), inv_data.get("بعد", 0.0), 
                  inv_data["البيان"], inv_data.get("settled_status", "ACTIVE"), inv_data.get("trees_count", 0.0), inv_data.get("set_number", ""), inv_data.get("row_number", ""),
                  inv_data.get("رقم الفاتورة اليدوي", existing_manual)))''',
    '''                INSERT OR REPLACE INTO invoices (invoice_id, date_time, name, op_type, weight, before_w, after_w, note, settled_status, trees_count, set_number, row_number, manual_no, period)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (inv_id, inv_data["التاريخ"], inv_data["الاسم"], inv_data["النوع"], 
                  inv_data["الوزن"], inv_data.get("قبل", 0.0), inv_data.get("بعد", 0.0), 
                  inv_data["البيان"], inv_data.get("settled_status", "ACTIVE"), inv_data.get("trees_count", 0.0), inv_data.get("set_number", ""), inv_data.get("row_number", ""),
                  inv_data.get("رقم الفاتورة اليدوي", existing_manual),
                  inv_data.get("period") or str(inv_data.get("التاريخ", ""))[:7]))''')

# ترحيل قاعدة العميل: إضافة العمود إن لم يكن موجوداً
rep('''    def init_database(self):''',
    '''    def ensure_period_column(self):
        """يضيف عمود (period) لقواعد العملاء القديمة، ويملؤه من تواريخ حركاتها.

        الملء بالتاريخ يحفظ السلوك السابق حرفياً: كانت الفترة = شهر التاريخ،
        فلا تتغيّر أرقام أي فترة سابقة بعد التحديث.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cols = [c[1] for c in cur.execute("PRAGMA table_info(invoices)")]
                if "period" not in cols:
                    cur.execute("ALTER TABLE invoices ADD COLUMN period TEXT DEFAULT ''")
                cur.execute("UPDATE invoices SET period = substr(date_time, 1, 7) "
                            "WHERE period IS NULL OR period = ''")
                conn.commit()
        except Exception as e:
            log_cloud_error("تعذّر تجهيز عمود الفترة", e)

    def init_database(self):''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة الثانية والعشرين على:", SRC)
