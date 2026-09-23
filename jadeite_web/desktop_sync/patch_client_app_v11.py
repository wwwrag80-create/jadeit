# -*- coding: utf-8 -*-
"""
الدفعة العاشرة — الجزء الثاني (شاشة مراحل التصنيع):
  ١) المصنعين/المركبين: عمود (الاسم) برتقالي كامل، متزامن تمريره مع الجدول
     الرئيسي (Treeview لا يلوّن خلية مفردة، فالحل تقني: جدول عمود واحد ملاصق)
  ٢) عمود (الراجع/عيار) بعد عمود (عيار) = سلك_راجع × عيار ÷ ٧٥٠
  ٣) معادلة (ذهب/باقي) تخصم الآن (الراجع/عيار) أيضاً — وذهب/صافي يرثها تلقائياً
  ٤) تعديل مباشر بالنقر المزدوج: «الاسم» لإعادة تخصيص الحركة لعامل آخر،
     و«رقم التشغيل» لتصحيحه — لكل صفوف مجموعة الصف نفسها
  ٥) زر «👁️ عرض» بجانب «تعديل الحركة المحددة» في كل قسم (ثابت أو مضاف)
     يفتح الجدول كاملاً بملء الشاشة مع صف إجمالي ثابت

الاستخدام:  python3 patch_client_app_v11.py rageh-1-34-14-cloud.py
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
#  ١) جدول ذو عمود اسم منفصل بلون برتقالي ثابت، متزامن التمرير مع الجدول الرئيسي
# ==========================================================================
rep('''    def create_standard_treeview(self, parent, columns, height=15):''',
    '''    def create_two_pane_ledger_tree(self, parent, main_cols, height=11,
                                    name_col_width=110, main_col_widths=None):
        """جدولان متلاصقان: عمود (الاسم) برتقالي بالكامل + الجدول الرئيسي بجانبه،
        يتحرّكان معاً عند التمرير أو عجلة الفأرة.

        السبب التقني: Treeview يُلوَّن على مستوى الصف كاملاً لا الخلية المفردة،
        فلا توجد طريقة لجعل عمود واحد برتقالياً بينما بقية أعمدة نفس الصف
        سوداء/حمراء حسب حالتها — حاولت ذلك بوسوم الصف فتعارضت الألوان.
        الحل: عمود الاسم في جدول منفصل ملاصق، بلا تعارض تلوين إطلاقاً.

        يرجع: (الجدول الرئيسي, جدول الاسم)
        """
        row = ttk.Frame(parent)
        row.pack(fill="both", expand=True)

        name_frame = ttk.Frame(row)
        name_frame.pack(side="right", fill="y")
        name_tree = ttk.Treeview(name_frame, columns=("الاسم",), show="headings", height=height)
        name_tree.heading("الاسم", text="الاسم")
        name_tree.column("الاسم", width=name_col_width, anchor="center", stretch=False)
        name_tree.tag_configure("orange_name", foreground="#e67e22", font=("Cairo", 13, "bold"))
        name_tree.pack(fill="y")

        main_frame = ttk.Frame(row)
        main_frame.pack(side="right", fill="both", expand=True)
        main_tree = self.create_standard_treeview(main_frame, main_cols, height=height)
        if main_col_widths:
            for col, w in main_col_widths.items():
                main_tree.column(col, width=w, anchor="center", stretch=False)

        # تزامن التمرير في الاتجاهين: تحريك أي من الجدولين يحرّك الآخر بنفس القدر
        orig_cmd = main_tree.cget("yscrollcommand")

        def on_main_scroll(first, last):
            if orig_cmd:
                self.tk.call(orig_cmd, first, last)
            name_tree.yview_moveto(first)

        main_tree.configure(yscrollcommand=on_main_scroll)
        name_tree.bind("<MouseWheel>",
                       lambda e: (main_tree.yview_scroll(int(-1 * (e.delta / 120)), "units"), "break"))
        name_tree.bind("<Button-4>", lambda e: (main_tree.yview_scroll(-1, "units"), "break"))
        name_tree.bind("<Button-5>", lambda e: (main_tree.yview_scroll(1, "units"), "break"))

        return main_tree, name_tree

    def create_standard_treeview(self, parent, columns, height=15):''')


# ==========================================================================
#  ٢) الأعمدة: الراجع/عيار بعد عيار، وتوحيد نسبة التحويل ٧٥٠
# ==========================================================================
rep('''ALLOWANCE_4 = 0.004    # ٤ بالألف''',
    '''ALLOWANCE_4 = 0.004    # ٤ بالألف
RAJI_PURITY = 750.0    # عيار المرجع لتحويل السلك الراجع (الراجع/عيار = سلك_راجع × عيار ÷ 750)


def raji_ayar(wire_back, karat):
    """يحوّل وزن السلك الراجع لمعادله بعيار ٧٥٠ حسب العيار المُقاس فعلياً"""
    try:
        return round((float(wire_back or 0) * float(karat or 0)) / RAJI_PURITY, 3)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0''')

rep('''        elif cat == "المركبين":
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "ليز", "سلك راجع", "عيار", "الفاقد اللحظي",
                    "مسموح/٨", "مسموح/٤", "ذهب/صافي", "البيان")
        else: # المصنعين
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "مفنش 8", "مفنش 4", "بوليش", "ليز", "سلك راجع", "عيار",
                    "الفاقد اللحظي", "مسموح/٨", "مسموح/٤", "ذهب/صافي", "البيان")''',
    '''        elif cat == "المركبين":
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "ليز", "سلك راجع", "عيار", "الراجع/عيار",
                    "الفاقد اللحظي", "مسموح/٨", "مسموح/٤", "ذهب/صافي", "البيان")
        else: # المصنعين
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "مفنش 8", "مفنش 4", "بوليش", "ليز", "سلك راجع", "عيار",
                    "الراجع/عيار", "الفاقد اللحظي", "مسموح/٨", "مسموح/٤", "ذهب/صافي", "البيان")''')

rep('''            elif c in ("ذهب/صافي", "الفاقد اللحظي"):
                w = 88''',
    '''            elif c in ("ذهب/صافي", "الفاقد اللحظي", "الراجع/عيار"):
                w = 88''')


# ==========================================================================
#  ٣) تحويل الجدول ليصبح جدولين متلاصقين (اسم + رئيسي) للمصنعين والمركبين فقط
# ==========================================================================
rep('''        cols = self.build_op_ledger_columns(worker_name, cat)
        self.op_ledger_tree = self.create_standard_treeview(self.op_ledger_table_frame, cols, height=11)
        self.op_ledger_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        self.op_ledger_tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))
        self.op_ledger_tree.bind("<Double-1>", lambda e: self.op_ledger_edit_selected())''',
    '''        cols = self.build_op_ledger_columns(worker_name, cat)
        show_name_pane = cat in ("المصنعين", "المركبين") and worker_name not in ("الكاستينج", "التلميع النهائي")
        self.op_ledger_name_tree = None

        if show_name_pane:
            self.op_ledger_tree, self.op_ledger_name_tree = self.create_two_pane_ledger_tree(
                self.op_ledger_table_frame, cols, height=11)
        else:
            self.op_ledger_tree = self.create_standard_treeview(self.op_ledger_table_frame, cols, height=11)

        self.op_ledger_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        self.op_ledger_tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))
        self.op_ledger_tree.bind("<Double-1>", self._on_op_ledger_double_click)
        if self.op_ledger_name_tree:
            self.op_ledger_name_tree.bind(
                "<Double-1>", lambda e: self.reassign_op_ledger_row(worker_name, cat))''')

# ربط قيم عمود الاسم بكل صف يُدرج + إدراج صف الإجمالي في جدول الاسم أيضاً
rep('''            if row_id is not None:
                self.op_ledger_group_map[row_id] = gkey''',
    '''            if row_id is not None:
                self.op_ledger_group_map[row_id] = gkey
                if self.op_ledger_name_tree is not None:
                    self.op_ledger_name_tree.insert("", "end", values=(worker_name,), tags=("orange_name",))''')

rep('''        if hasattr(self, 'lbl_op_ledger_totals'):
            self.lbl_op_ledger_totals.configure(text=totals_txt)

    def op_ledger_delete_selected(self):''',
    '''        if hasattr(self, 'lbl_op_ledger_totals'):
            self.lbl_op_ledger_totals.configure(text=totals_txt)

        # صف إجمالي فارغ يقابل صف الإجمالي في الجدول الرئيسي، حتى يبقى الجدولان
        # متطابقَي عدد الصفوف تماماً (شرط أساسي لتزامن التمرير بينهما)
        if self.op_ledger_name_tree is not None and ordered:
            self.op_ledger_name_tree.insert("", "end", values=("الإجمالي",), tags=("orange_name",))

    def _on_op_ledger_double_click(self, event):
        """يميّز نقرة عمود (رقم التشغيل) لفتح تعديل سريع لها، وأي عمود آخر يفتح
        نافذة تعديل الحركة الكاملة كما كان."""
        col = self.op_ledger_tree.identify_column(event.x)
        try:
            cols = self.op_ledger_tree["columns"]
            idx = int(col.replace("#", "")) - 1
            col_name = cols[idx] if 0 <= idx < len(cols) else ""
        except (ValueError, IndexError):
            col_name = ""

        if col_name == "رقم التشغيل":
            self.rename_op_ledger_set_number()
        else:
            self.op_ledger_edit_selected()

    def rename_op_ledger_set_number(self):
        """تعديل سريع لقيمة (رقم التشغيل) لصف محدد، بلا فتح نافذة التعديل الكاملة"""
        sel = self.op_ledger_tree.selection() if self.op_ledger_tree else []
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الصف المراد تعديل رقم تشغيله أولاً.")
            return
        gkey = self.op_ledger_group_map.get(sel[0])
        if gkey is None:
            return
        if not self.check_edit_permission():
            return

        worker_name = self.combo_op_name.get()
        current_vals = self.op_ledger_tree.item(sel[0], "values")
        current_set = current_vals[1] if len(current_vals) > 1 else ""

        new_val = ctk.CTkInputDialog(
            title="تعديل رقم التشغيل",
            text=f"رقم التشغيل الجديد لهذا الصف (الحالي: {current_set or '-'})"
        ).get_input()
        if new_val is None:
            return
        new_val = new_val.strip()

        target_ids = [inv["رقم الفاتورة"] for inv in self.invoices.values()
                     if inv.get("الاسم") == worker_name
                     and inv.get("settled_status") == "ACTIVE"
                     and (inv.get("row_number", "") or "") == gkey
                     and inv.get("التاريخ", "").startswith(self.current_display_month)]
        if not target_ids:
            messagebox.showwarning("تنبيه", "لم يعد لهذا الصف حركات مسجّلة.")
            return

        blocked = False
        for inv_id in target_ids:
            updated = dict(self.invoices[inv_id])
            updated["set_number"] = new_val
            if not self.save_invoice_to_db(inv_id, updated):
                blocked = True
        if blocked:
            return
        self.recalculate_all()
        messagebox.showinfo("تم", f"تم تحديث رقم التشغيل إلى ({new_val or '-'}) لكل حركات هذا الصف.")

    def reassign_op_ledger_row(self, current_worker, cat):
        """يعيد تخصيص كل حركات الصف المحدد لعامل آخر من نفس القسم — عبر
        النقر المزدوج على عمود الاسم المنفصل."""
        sel = self.op_ledger_name_tree.selection() if self.op_ledger_name_tree else []
        if not sel:
            return
        # صفا الأسماء والجدول الرئيسي متطابقا الترتيب دائماً (يُدرَجان معاً سطراً بسطر)
        idx = self.op_ledger_name_tree.index(sel[0])
        main_children = self.op_ledger_tree.get_children()
        if idx >= len(main_children):
            return
        main_iid = main_children[idx]
        gkey = self.op_ledger_group_map.get(main_iid)
        if gkey is None:
            messagebox.showinfo("تنبيه", "هذا السطر إجمالي، لا يمكن إعادة تخصيصه.")
            return
        if not self.check_edit_permission():
            return

        others = [n for n in self.categories.get(cat, []) if n != current_worker]
        if not others:
            messagebox.showinfo("تنبيه", f"لا يوجد عامل آخر مسجَّل في قسم ({cat}) لإعادة التخصيص إليه.")
            return

        win = ctk.CTkToplevel(self)
        win.title("إعادة تخصيص الحركة")
        win.geometry("380x220")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"نقل حركات هذا الصف من ({current_worker}) إلى:",
                     font=("Cairo", 14, "bold"), wraplength=340, justify="center").pack(pady=(20, 10))
        combo = ctk.CTkComboBox(win, values=others, font=("Cairo", 14), justify="right",
                                width=240, height=38, state="readonly")
        combo.set(others[0])
        combo.pack(pady=6)

        def do_reassign():
            new_worker = combo.get()
            target_ids = [inv["رقم الفاتورة"] for inv in self.invoices.values()
                         if inv.get("الاسم") == current_worker
                         and inv.get("settled_status") == "ACTIVE"
                         and (inv.get("row_number", "") or "") == gkey
                         and inv.get("التاريخ", "").startswith(self.current_display_month)]
            if not target_ids:
                messagebox.showwarning("تنبيه", "لم يعد لهذا الصف حركات مسجّلة.", parent=win)
                win.destroy()
                return
            blocked = False
            for inv_id in target_ids:
                updated = dict(self.invoices[inv_id])
                updated["الاسم"] = new_worker
                if not self.save_invoice_to_db(inv_id, updated):
                    blocked = True
            win.destroy()
            if blocked:
                return
            self.recalculate_all()
            messagebox.showinfo("تم", f"تم نقل {len(target_ids)} حركة إلى ({new_worker}).")

        ctk.CTkButton(win, text="نقل الحركات", font=("Cairo", 14, "bold"), fg_color="#1e8449",
                      hover_color="#145a32", width=180, height=40, command=do_reassign).pack(pady=16)

    def op_ledger_delete_selected(self):''')

# دمج الراجع/عيار في الحساب والقيم المُدرجة — المركبين
rep('''            elif cat == "المركبين":
                faqid = round(data['صرف'] - data['قبض'] + data['ليز'], 2)
                tot["فاقد"] = round(tot["فاقد"] + faqid, 2)
                row_tags = ("red_tag",) if (color_negative and faqid < 0) else ()
                # المسموح في المركبين يُحتسب على القبض (نفس معادلة شاشة صناديق الخياس)
                allow8 = round(data['قبض'] * ALLOWANCE_8, 2)
                # ذهب/صافي = الفاقد اللحظي بعد خصم المسموح (المركبين بلا مسموح/٤)
                net_gold = round(faqid - allow8, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["ذهب صافي"] = round(tot["ذهب صافي"] + net_gold, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", f"{allow8:.3f}", "-", f"{net_gold:.2f}", note), tags=row_tags)''',
    '''            elif cat == "المركبين":
                raji_v = raji_ayar(data['سلك راجع'], data['عيار'])
                # ذهب/باقي (الفاقد اللحظي) يخصم الآن (الراجع/عيار) أيضاً
                faqid = round(data['صرف'] - data['قبض'] + data['ليز'] - raji_v, 2)
                tot["فاقد"] = round(tot["فاقد"] + faqid, 2)
                tot["راجع عيار"] = round(tot.get("راجع عيار", 0.0) + raji_v, 2)
                row_tags = ("red_tag",) if (color_negative and faqid < 0) else ()
                # المسموح في المركبين يُحتسب على القبض (نفس معادلة شاشة صناديق الخياس)
                allow8 = round(data['قبض'] * ALLOWANCE_8, 2)
                # ذهب/صافي = الفاقد اللحظي (بعد خصم الراجع/عيار) بعد خصم المسموح
                net_gold = round(faqid - allow8, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["ذهب صافي"] = round(tot["ذهب صافي"] + net_gold, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{raji_v:.3f}", f"{faqid:.2f}", f"{allow8:.3f}", "-", f"{net_gold:.2f}", note), tags=row_tags)''')

# دمج الراجع/عيار — المصنعين
rep('''            else:
                faqid = round(data['صرف'] - data['قبض'] - data['بوليش'] + data['ليز'] - data['مفنش 8'] - data['مفنش 4'], 2)
                tot["فاقد"] = round(tot["فاقد"] + faqid, 2)
                row_tags = ("red_tag",) if (color_negative and faqid < 0) else ()
                # المسموح في المصنعين يُحتسب على المفنش ٨ و٤ (نفس معادلة شاشة صناديق الخياس)
                allow8 = round(data['مفنش 8'] * ALLOWANCE_8, 2)
                allow4 = round(data['مفنش 4'] * ALLOWANCE_4, 2)
                # ذهب/صافي = الفاقد اللحظي بعد خصم المسموح ٨ و٤
                net_gold = round(faqid - allow8 - allow4, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["مسموح 4"] = round(tot["مسموح 4"] + allow4, 2)
                tot["ذهب صافي"] = round(tot["ذهب صافي"] + net_gold, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}", f"{data['مفنش 4']:.2f}", f"{data['بوليش']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", f"{allow8:.3f}", f"{allow4:.3f}", f"{net_gold:.2f}", note), tags=row_tags)''',
    '''            else:
                raji_v = raji_ayar(data['سلك راجع'], data['عيار'])
                # ذهب/باقي (الفاقد اللحظي) يخصم الآن (الراجع/عيار) أيضاً
                faqid = round(data['صرف'] - data['قبض'] - data['بوليش'] + data['ليز'] - data['مفنش 8'] - data['مفنش 4'] - raji_v, 2)
                tot["فاقد"] = round(tot["فاقد"] + faqid, 2)
                tot["راجع عيار"] = round(tot.get("راجع عيار", 0.0) + raji_v, 2)
                row_tags = ("red_tag",) if (color_negative and faqid < 0) else ()
                # المسموح في المصنعين يُحتسب على المفنش ٨ و٤ (نفس معادلة شاشة صناديق الخياس)
                allow8 = round(data['مفنش 8'] * ALLOWANCE_8, 2)
                allow4 = round(data['مفنش 4'] * ALLOWANCE_4, 2)
                # ذهب/صافي = الفاقد اللحظي (بعد خصم الراجع/عيار) بعد خصم المسموح ٨ و٤
                net_gold = round(faqid - allow8 - allow4, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["مسموح 4"] = round(tot["مسموح 4"] + allow4, 2)
                tot["ذهب صافي"] = round(tot["ذهب صافي"] + net_gold, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}", f"{data['مفنش 4']:.2f}", f"{data['بوليش']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{raji_v:.3f}", f"{faqid:.2f}", f"{allow8:.3f}", f"{allow4:.3f}", f"{net_gold:.2f}", note), tags=row_tags)''')

# سطور الإجمالي: أضف عمود الراجع/عيار
rep('''            elif cat == "المركبين":
                self.op_ledger_tree.insert("", "end", values=("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", "-", f"{tot['ذهب صافي']:.2f}", "-"), tags=("total_tag",))''',
    '''            elif cat == "المركبين":
                self.op_ledger_tree.insert("", "end", values=("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot.get('راجع عيار', 0.0):.3f}", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", "-", f"{tot['ذهب صافي']:.2f}", "-"), tags=("total_tag",))''')

rep('''            else:
                self.op_ledger_tree.insert("", "end", values=("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['مفنش 8']:.2f}", f"{tot['مفنش 4']:.2f}", f"{tot['بوليش']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", f"{tot['مسموح 4']:.3f}", f"{tot['ذهب صافي']:.2f}", "-"), tags=("total_tag",))
                totals_txt = f"الإجماليات — مدين (صرف): {tot['صرف']:.2f}  |  دائن (قبض/كسر+٨+٤+بوليش): {round(tot['قبض'] + tot['مفنش 8'] + tot['مفنش 4'] + tot['بوليش'], 2):.2f}  |  الخياس (الفاقد): {tot['فاقد']:.2f} جم"''',
    '''            else:
                self.op_ledger_tree.insert("", "end", values=("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['مفنش 8']:.2f}", f"{tot['مفنش 4']:.2f}", f"{tot['بوليش']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot.get('راجع عيار', 0.0):.3f}", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", f"{tot['مسموح 4']:.3f}", f"{tot['ذهب صافي']:.2f}", "-"), tags=("total_tag",))
                totals_txt = f"الإجماليات — مدين (صرف): {tot['صرف']:.2f}  |  دائن (قبض/كسر+٨+٤+بوليش): {round(tot['قبض'] + tot['مفنش 8'] + tot['مفنش 4'] + tot['بوليش'], 2):.2f}  |  الخياس (الفاقد): {tot['فاقد']:.2f} جم"''')

rep('''        tot = {k: 0.0 for k in ("صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع",
                                "قبل", "بعد", "الخياس", "trees", "فاقد", "مسموح 8", "مسموح 4",
                                "ذهب صافي")}''',
    '''        tot = {k: 0.0 for k in ("صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع",
                                "قبل", "بعد", "الخياس", "trees", "فاقد", "مسموح 8", "مسموح 4",
                                "ذهب صافي", "راجع عيار")}''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الثاني من الدفعة العاشرة على:", SRC)
