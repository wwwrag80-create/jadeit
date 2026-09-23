# -*- coding: utf-8 -*-
"""
الدفعة التاسعة (ب):
  ٤) صندوق (الصب) الجديد + زر حذف صندوق خياس بكل ما يخصه
  ٥) الأرقام بالصيغة الإنجليزية في أشرطة الذهب والخزينة والرصيد الحالي

الاستخدام:  python3 patch_client_app_v9b.py rageh-1-34-14-cloud.py
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
#  ٥) أرقام إنجليزية في الأشرطة
# ==========================================================================
rep('''ALLOWANCE_8 = 0.008    # ٨ بالألف''',
    '''# علامة الاتجاه من اليسار لليمين: تُجبر النص المختلط على عرض الأرقام
# بالصيغة الإنجليزية (5) بدل العربية الهندية (٥) داخل الجمل العربية
LTR_MARK = "\\u200e"


def en(value, decimals=2, thousands=True):
    """يُنسّق رقماً بالصيغة الإنجليزية ويثبّت اتجاهه داخل النص العربي"""
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return LTR_MARK + "0.00"
    fmt = "{:,.%df}" % decimals if thousands else "{:.%df}" % decimals
    return LTR_MARK + fmt.format(num)


ALLOWANCE_8 = 0.008    # ٨ بالألف''')

# شريط الخزينة والرصيد الحالي
rep('''            self.lbl_live_treasury.configure(text=f"رصيد الخزينة الحالي: {self.current_treasury_balance:.2f} جم")''',
    '''            self.lbl_live_treasury.configure(text=f"رصيد الخزينة الحالي: {en(self.current_treasury_balance)} جم")''')

rep('''            self.lbl_total_gold.configure(text=f"الرصيد الحالي: {self.current_total_gold:.2f} جم")''',
    '''            self.lbl_total_gold.configure(text=f"الرصيد الحالي: {en(self.current_total_gold)} جم")''')


# ==========================================================================
#  ٤) حذف صندوق خياس بكل ما يخصه
# ==========================================================================
rep('''        ctk.CTkButton(btn_row, text="➕ إضافة حساب", font=("Cairo", 13, "bold"), fg_color="#1f77b4", hover_color="#144d75", width=140, height=38, command=self.open_add_account_dialog).pack(side="left", padx=5)''',
    '''        ctk.CTkButton(btn_row, text="➕ إضافة حساب", font=("Cairo", 13, "bold"), fg_color="#1f77b4", hover_color="#144d75", width=140, height=38, command=self.open_add_account_dialog).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="🗑️ حذف صندوق خياس", font=("Cairo", 13, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=170, height=38, command=self.delete_khayas_box_dialog).pack(side="left", padx=5)''')

rep('''    def open_add_account_dialog(self):''',
    '''    def get_deletable_khayas_boxes(self):
        """الصناديق القابلة للحذف: المضافة يدوياً فقط.

        الصناديق الأساسية (الكاستنج/التلميع/البف/خياس الطقوم) مرتبطة بمنطق
        محاسبي ثابت في النظام، وحذفها يكسر شاشات وحسابات قائمة.
        """
        return list(self.categories.get("أقسام_خياس_إضافية", []))

    def count_box_transactions(self, stage_name):
        """عدد الحركات المرتبطة بالصندوق (صرف/قبض/مسترجع/قيود حسابه)"""
        madin, qabd, mustarja = self.get_stage_config(stage_name)
        box_account = self.get_box_account_name(stage_name)
        n = 0
        for inv in self.invoices.values():
            t = inv.get("النوع")
            name = inv.get("الاسم")
            if t in (madin, qabd) or name == mustarja or name == box_account or name == stage_name:
                n += 1
        return n

    def delete_khayas_box_dialog(self):
        """حذف صندوق خياس مضاف، مع كل ما يخصه: حركاته ومسترجعه وحسابه وعمّاله"""
        boxes = self.get_deletable_khayas_boxes()
        if not boxes:
            messagebox.showinfo(
                "لا يوجد",
                "لا توجد صناديق خياس مضافة يمكن حذفها.\\n\\n"
                "الصناديق الأساسية (الكاستنج، التلميع، التلميع/البف، خياس الطقوم) "
                "مرتبطة بمنطق النظام ولا يمكن حذفها.")
            return

        win = ctk.CTkToplevel(self)
        win.title("حذف صندوق خياس")
        win.geometry("460x360")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="🗑️ حذف صندوق خياس", font=("Cairo", 18, "bold"),
                     text_color="#e74c3c").pack(pady=(16, 4))
        ctk.CTkLabel(win, text="سيُحذف الصندوق وكل ما يخصه نهائياً", font=("Cairo", 12),
                     text_color="#8b8f95").pack(pady=(0, 12))

        combo = ctk.CTkComboBox(win, values=boxes, font=("Cairo", 15), justify="right",
                                width=280, height=40, state="readonly")
        combo.set(boxes[0])
        combo.pack(pady=6)

        lbl_info = ctk.CTkLabel(win, text="", font=("Cairo", 12, "bold"), text_color="#e67e22",
                                wraplength=400, justify="center")
        lbl_info.pack(pady=10)

        def refresh_info(_=None):
            box = combo.get()
            n = self.count_box_transactions(box)
            lbl_info.configure(
                text=f"الحركات المرتبطة بهذا الصندوق: {n}" if n
                else "لا توجد حركات مرتبطة — الحذف آمن تماماً")

        combo.configure(command=refresh_info)
        refresh_info()

        def do_delete():
            box = combo.get()
            n = self.count_box_transactions(box)
            if not messagebox.askyesno(
                    "تأكيد الحذف النهائي",
                    f"سيتم حذف صندوق ({box}) نهائياً، ومعه:\\n\\n"
                    f"• {n} حركة مسجّلة (صرف/قبض/مسترجع/قيود)\\n"
                    f"• حساب المسترجع الخاص به\\n"
                    f"• شاشته في مراحل التصنيع وصناديق الخياس وشاشة الخسائر\\n\\n"
                    "لا يمكن التراجع عن هذه العملية. هل أنت متأكد؟", parent=win):
                return

            if n > 0 and not messagebox.askyesno(
                    "تحذير أخير",
                    f"هذا الصندوق عليه {n} حركة محاسبية مسجّلة.\\n"
                    "حذفها سيغيّر رصيد الخزينة وإجمالي الفواقد.\\n\\n"
                    "هل تريد المتابعة فعلاً؟", parent=win):
                return

            self.perform_khayas_box_deletion(box)
            win.destroy()

        ctk.CTkButton(win, text="🗑️ حذف نهائياً", font=("Cairo", 15, "bold"), fg_color="#8b0000",
                      hover_color="#a52a2a", width=180, height=42, command=do_delete).pack(pady=8)
        ctk.CTkButton(win, text="إلغاء", font=("Cairo", 13), fg_color="#555555",
                      hover_color="#333333", width=120, height=34, command=win.destroy).pack()

    def perform_khayas_box_deletion(self, stage_name):
        """التنفيذ الفعلي للحذف: الحركات ثم الحسابات ثم إعادة بناء الشاشات"""
        madin, qabd, mustarja = self.get_stage_config(stage_name)
        box_account = self.get_box_account_name(stage_name)

        # ١) حذف كل الحركات المرتبطة
        to_delete = [inv["رقم الفاتورة"] for inv in self.invoices.values()
                     if inv.get("النوع") in (madin, qabd)
                     or inv.get("الاسم") in (mustarja, box_account, stage_name)]
        blocked = 0
        for inv_id in to_delete:
            if not self.delete_invoice_from_db(inv_id):
                blocked += 1

        # ٢) حذف عمّال القسم من شجرة الحسابات
        for worker in list(self.categories.get(stage_name, [])):
            self.delete_worker_from_db(worker, stage_name)
        self.categories.pop(stage_name, None)

        # ٣) حذف القسم نفسه
        if stage_name in self.categories.get("أقسام_خياس_إضافية", []):
            self.categories["أقسام_خياس_إضافية"].remove(stage_name)
        self.delete_worker_from_db(stage_name, "أقسام_خياس_إضافية")

        # ٤) إزالة إعداداته المحفوظة (لون التلوين مثلاً) حتى لا تتراكم
        try:
            self.set_setting(f"neg_color_{stage_name}", "")
        except Exception:
            pass

        # ٥) إعادة بناء كل الشاشات المرتبطة
        for fn in ("refresh_stage_buttons", "refresh_khayas_category_buttons",
                   "refresh_losses_cards", "refresh_chart_of_accounts"):
            if hasattr(self, fn):
                try:
                    getattr(self, fn)()
                except Exception as e:
                    log_cloud_error(f"تعذّر تحديث {fn} بعد حذف الصندوق", e)

        self.update_period_selector()
        self.recalculate_all()

        msg = f"تم حذف صندوق ({stage_name}) وكل ما يخصه."
        if blocked:
            msg += f"\\n\\nتنبيه: تعذّر حذف {blocked} حركة (التعديل مقفول من المدير)."
        messagebox.showinfo("تم الحذف", msg)

    def open_add_account_dialog(self):''')


# ==========================================================================
#  ٤-ب) صندوق (الصب) يُنشأ تلقائياً عند أول تشغيل
# ==========================================================================
rep('''    def get_all_stage_categories(self):''',
    '''    def ensure_default_khayas_boxes(self):
        """ينشئ صندوق (الصب) تلقائياً لو لم يكن موجوداً.

        يُعامل كأي صندوق خياس: صرف/قبض/مسترجع/إقفال، ويظهر في مراحل التصنيع
        وصناديق الخياس وشاشة الخسائر والرصيد الحالي — كالكاستنج والبوليش تماماً.
        """
        DEFAULTS = ["الصب"]
        added = False
        for box in DEFAULTS:
            existing = self.categories.get("أقسام_خياس_إضافية", [])
            if box in existing:
                continue
            # لا نُنشئه لو كان الاسم مستخدماً لحساب آخر (تفادياً لالتباس محاسبي)
            if box in self.get_account_statement_options():
                continue
            self.categories.setdefault("أقسام_خياس_إضافية", []).append(box)
            self.save_name_to_db(box, "أقسام_خياس_إضافية")
            self.categories.setdefault(box, [])
            added = True
        return added

    def get_all_stage_categories(self):''')

rep('''        self.build_gold_price_bar()''',
    '''        self.ensure_default_khayas_boxes()
        self.build_gold_price_bar()''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة التاسعة (ب) على:", SRC)
