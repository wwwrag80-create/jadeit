# -*- coding: utf-8 -*-
"""
الدفعة الحادية والعشرون:
  ١) التاريخ حيّ: يتتبّع تاريخ الجهاز فوراً بلا إعادة تشغيل
  ٢) العمليات تُسجَّل في الفترة المعروضة، بيوم اليوم ووقته الحيّ
  ٣) حذف العامل لا يحذف حركاته + زر تراجع عن آخر خطوة
  ٤) ترتيب الأسماء العربية يظهر صحيحاً في القوائم
  ٥) Enter في آخر خانة يرحّل العملية، وEnter يؤكّد الإشعار

الاستخدام:  python3 patch_client_app_v31.py rageh-1-34-14-cloud.py
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
#  ١+٢) التاريخ الحيّ داخل الفترة المعروضة
# ==========================================================================
rep('''    def get_smart_default_date(self):
        curr_sys_month = datetime.datetime.now().strftime("%Y-%m")
        if self.current_display_month == curr_sys_month:
            return datetime.datetime.now().strftime("%Y-%m-%d")
        else:
            # فترة سابقة/لاحقة مختارة يدوياً: نبدأ من أول يوم فيها
            return f"{self.current_display_month}-01"''',
    '''    def get_smart_default_date(self):
        """تاريخ العملية الافتراضي: يوم اليوم داخل الفترة المعروضة.

        القاعدة المحاسبية: العملية تُثبَّت في **الفترة التي يعمل فيها المستخدم**،
        لا في شهر تاريخ الجهاز. فلو كان اليوم ٢٠٢٦-٠٩-٠١ والمستخدم في فترة
        ٢٠٢٦-٠٨، تُسجَّل بتاريخ ٢٠٢٦-٠٨-٠١ — نفس رقم اليوم، داخل فترته.
        ولو تجاوز رقم اليوم أيام ذلك الشهر (مثل ٣١ في شهر من ٣٠ يوماً) يُثبَّت
        على آخر يوم فيه بدل تاريخ غير موجود.

        وهو يُقرأ لحظياً في كل استدعاء، فيتتبّع تغيّر تاريخ الجهاز فوراً.
        """
        now = datetime.datetime.now()
        if self.current_display_month == now.strftime("%Y-%m"):
            return now.strftime("%Y-%m-%d")

        try:
            year, month = (int(x) for x in self.current_display_month.split("-")[:2])
            last_day = calendar.monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-{min(now.day, last_day):02d}"
        except (ValueError, IndexError):
            return f"{self.current_display_month}-01"

    def get_operation_datetime(self):
        """تاريخ ووقت العملية: التاريخ داخل الفترة المعروضة، والوقت حيٌّ دائماً"""
        return f"{self.get_smart_default_date()} {datetime.datetime.now().strftime('%H:%M:%S')}"

    def refresh_live_date_fields(self):
        """يحدّث خانات التاريخ المعروضة عند تغيّر تاريخ الجهاز والبرنامج مفتوح.

        بدون هذا كانت الخانات تحتفظ بتاريخ لحظة فتح الشاشة، فيبقى النظام
        على تاريخ الأمس حتى يُعاد تشغيله.
        """
        try:
            expected = self.get_smart_default_date()
            last = getattr(self, "_last_live_date", None)
            if last != expected:
                for attr in ("date_entry", "sale_date", "in_date", "op_date",
                             "cast_date", "polish_date", "pbuff_date"):
                    widget = getattr(self, attr, None)
                    if widget is None:
                        continue
                    try:
                        current = widget.get().strip()
                        # لا نلمس تاريخاً عدّله المستخدم بنفسه
                        if current in ("", last):
                            widget.delete(0, "end")
                            widget.insert(0, expected)
                    except Exception:
                        continue

                for stage in getattr(self, "dynamic_stage_widgets", {}).values():
                    widget = stage.get("date")
                    if widget is None:
                        continue
                    try:
                        current = widget.get().strip()
                        if current in ("", last):
                            widget.delete(0, "end")
                            widget.insert(0, expected)
                    except Exception:
                        continue

                self._last_live_date = expected
        except Exception as e:
            log_cloud_error("تعذّر تحديث التاريخ الحيّ", e)
        finally:
            self.after(30000, self.refresh_live_date_fields)   # كل ٣٠ ثانية''')

rep('''        self.update_period_warning()
        self.watch_system_month()''',
    '''        self.update_period_warning()
        self.watch_system_month()
        self.refresh_live_date_fields()''')

rep('''import sqlite3''', '''import calendar
import sqlite3''')


# ==========================================================================
#  ٣) حذف العامل بلا حذف حركاته + تراجع
# ==========================================================================
rep('''    def delete_worker_from_db(self, worker_name, category):
        """يرجع True لو تم الحذف فعلياً، أو False لو تم المنع (الحذف مسموح دائماً)"""
        if not self.check_delete_permission():
            return False
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM names WHERE name = ? AND category = ?", (worker_name, category))
            cursor.execute("DELETE FROM invoices WHERE name = ? AND settled_status = 'ACTIVE'", (worker_name,))
            conn.commit()
            
        if worker_name in self.categories[category]:
            self.categories[category].remove(worker_name)
        self.invoices = {k: v for k, v in self.invoices.items() if v["الاسم"] != worker_name}
        self.mark_backup_dirty()
        return True''',
    '''    def delete_worker_from_db(self, worker_name, category, keep_transactions=True):
        """يحذف اسم العامل من شجرة الحسابات.

        keep_transactions=True (الافتراضي): **حركاته المحاسبية تبقى كما هي**.
        حذف حركات عامل يغيّر رصيد الخزينة وإجمالي الفواقد بأثر رجعي ويُفسد
        فترات مقفلة — والاسم مجرد تسمية، أما الحركات فقيود محاسبية.
        تمرير False يحذفها معه (يُستخدم عند حذف صندوق خياس بكامله بعد تأكيد
        المستخدم على عدد حركاته).
        """
        if not self.check_delete_permission():
            return False

        # لقطة للتراجع قبل أي تغيير
        self.push_undo(f"حذف الاسم ({worker_name})")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM names WHERE name = ? AND category = ?", (worker_name, category))
            if not keep_transactions:
                cursor.execute("DELETE FROM invoices WHERE name = ? AND settled_status = 'ACTIVE'",
                               (worker_name,))
            conn.commit()

        if worker_name in self.categories.get(category, []):
            self.categories[category].remove(worker_name)
        if not keep_transactions:
            self.invoices = {k: v for k, v in self.invoices.items() if v["الاسم"] != worker_name}
        self.mark_backup_dirty()
        return True

    # =====================================================================
    # --- التراجع عن آخر خطوة (مثل Ctrl+Z) ---
    # =====================================================================
    UNDO_LIMIT = 20

    def push_undo(self, label):
        """يحفظ لقطة من الحالة قبل عملية قابلة للتراجع.

        اللقطة نسخة من الحركات وشجرة الأسماء — وهما مصدر كل الأرقام في النظام،
        فاستعادتهما تُرجع الوضع كما كان تماماً.
        """
        try:
            import copy
            if not hasattr(self, "_undo_stack"):
                self._undo_stack = []
            self._undo_stack.append({
                "label": label,
                "invoices": copy.deepcopy(self.invoices),
                "categories": copy.deepcopy(self.categories),
                "counter": self.invoice_counter,
            })
            if len(self._undo_stack) > self.UNDO_LIMIT:
                self._undo_stack.pop(0)
            self.update_undo_buttons()
        except Exception as e:
            log_cloud_error("تعذّر حفظ لقطة التراجع", e)

    def can_undo(self):
        return bool(getattr(self, "_undo_stack", []))

    def update_undo_buttons(self):
        """يفعّل أو يعطّل أزرار التراجع حسب توفّر خطوة سابقة"""
        label = "↩️ تراجع"
        if self.can_undo():
            label = f"↩️ تراجع: {self._undo_stack[-1]['label']}"
        for btn in getattr(self, "_undo_buttons", []):
            try:
                btn.configure(text=label if len(label) < 34 else "↩️ تراجع",
                              state="normal" if self.can_undo() else "disabled")
            except Exception:
                continue

    def register_undo_button(self, btn):
        if not hasattr(self, "_undo_buttons"):
            self._undo_buttons = []
        self._undo_buttons.append(btn)
        self.update_undo_buttons()

    def undo_last_action(self):
        """يُرجع الحالة إلى ما قبل آخر خطوة قابلة للتراجع"""
        if not self.can_undo():
            messagebox.showinfo("لا يوجد", "لا توجد خطوة يمكن التراجع عنها.")
            return
        if not self.check_edit_permission():
            return

        snap = self._undo_stack[-1]
        if not messagebox.askyesno(
                "تأكيد التراجع",
                f"سيتم التراجع عن: {snap['label']}\\n\\n"
                "وتعود البيانات كما كانت قبل هذه الخطوة. هل تريد المتابعة؟"):
            return

        snap = self._undo_stack.pop()
        try:
            self.invoices = snap["invoices"]
            self.categories = snap["categories"]
            self.invoice_counter = snap["counter"]
            self.rewrite_database_from_memory()
            self.recalculate_all()
            self.update_undo_buttons()
            messagebox.showinfo("تم التراجع", f"تم التراجع عن: {snap['label']}")
        except Exception as e:
            log_cloud_error("تعذّر التراجع", e)
            messagebox.showerror("خطأ", f"تعذّر إتمام التراجع:\\n{e}")

    def rewrite_database_from_memory(self):
        """يُعيد كتابة جدولَي الحركات والأسماء من الذاكرة (تنفيذ التراجع).

        تُكتب في معاملة واحدة: إما أن ينجح كل شيء أو لا يتغيّر شيء —
        فلا تبقى القاعدة في حالة نصفية لو انقطع التنفيذ.
        """
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("BEGIN")
            try:
                cur.execute("DELETE FROM invoices")
                cur.execute("DELETE FROM names")
                for inv in self.invoices.values():
                    cur.execute("""INSERT INTO invoices
                        (invoice_id, date_time, name, op_type, weight, before_w, after_w,
                         note, settled_status, trees_count, set_number, row_number, manual_no)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (inv.get("رقم الفاتورة"), inv.get("التاريخ"), inv.get("الاسم"),
                         inv.get("النوع"), inv.get("الوزن", 0.0), inv.get("قبل", 0.0),
                         inv.get("بعد", 0.0), inv.get("البيان", ""),
                         inv.get("settled_status", "ACTIVE"), inv.get("trees_count", 0.0),
                         inv.get("set_number", ""), inv.get("row_number", ""),
                         inv.get("رقم الفاتورة اليدوي", "")))
                for cat, names in self.categories.items():
                    for n in names:
                        cur.execute("INSERT OR IGNORE INTO names (name, category) VALUES (?, ?)",
                                    (n, cat))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        self.mark_backup_dirty()''')

# حذف صندوق الخياس يحذف الحركات صراحةً (سلوكه المقصود)
rep('''        for worker in list(self.categories.get(stage_name, [])):
            self.delete_worker_from_db(worker, stage_name)''',
    '''        for worker in list(self.categories.get(stage_name, [])):
            # هنا الحذف الكامل مقصود: المستخدم أكّد على عدد حركات الصندوق
            self.delete_worker_from_db(worker, stage_name, keep_transactions=False)''')

# رسالة حذف العامل توضّح أن الحركات تبقى
rep('''        if messagebox.askyesno("تأكيد حذف العامل", f"هل أنت متأكد من حذف ({worker_name})؟"):
            if not self.delete_worker_from_db(worker_name, self.current_view_cat):
                return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
            self.recalculate_all()
            messagebox.showinfo("تم الحذف", f"تم الحذف بنجاح.")''',
    '''        if messagebox.askyesno(
                "تأكيد حذف الاسم",
                f"هل أنت متأكد من حذف الاسم ({worker_name})؟\\n\\n"
                "ملاحظة: تُحذف التسمية فقط، أما حركاته المحاسبية فتبقى مسجّلة كما هي.\\n"
                "ويمكنك التراجع عن هذه الخطوة بزر (تراجع)."):
            if not self.delete_worker_from_db(worker_name, self.current_view_cat):
                return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
            self.recalculate_all()
            messagebox.showinfo(
                "تم الحذف",
                "تم حذف الاسم. حركاته المحاسبية باقية كما هي،\\n"
                "ويمكنك التراجع بزر (تراجع) إن كان الحذف بالخطأ.")''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة الحادية والعشرين على:", SRC)
