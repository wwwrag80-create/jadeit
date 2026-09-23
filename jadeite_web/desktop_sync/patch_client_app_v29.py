# -*- coding: utf-8 -*-
"""
الدفعة التاسعة عشرة:
  ١) خياس المركب: يقرأ نفس ما يعرضه الكشف — يجد الصف برقم التشغيل حتى لو كان
     مسجّلاً على بعض حركات الصف فقط (بيانات النسخة القديمة)، ولا يُخفي أخطاءه
  ٢) المصنعين/المركبين: زر (تعديل الحركة المحددة) يفتح نافذة بكل خانات الصف
     قابلة للتعديل، والنقر المزدوج يبقى لعرض كشف الصف
  ٣) شريط الإجمالي أسفل الجدول: ارتفاع ثابت لا يمكن أن ينكمش فيختفي

الاستخدام:  python3 patch_client_app_v29.py rageh-1-34-14-cloud.py
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
#  ١) خياس المركب: البحث بالصف لا بالحركة المفردة
# ==========================================================================
old_start = src.index("    def get_assembler_khayas_for_set(self, set_number, month=None):")
old_end = src.index("\n    def autofill_assembler_khayas", old_start)

new_fn = '''    def get_assembler_khayas_for_set(self, set_number, month=None):
        """قيمة عمود (مسموح/٨) لرقم تشغيل معيّن من شاشة مراحل التصنيع.

        لماذا البحث بالصف لا بالحركة المفردة:
        رقم التشغيل قد يكون مسجّلاً على **بعض** حركات الصف فقط — وهذا هو حال
        البيانات المُدخلة في نسخ سابقة. فلو بحثنا عن حركة (قبض ذهب) تحمل رقم
        التشغيل مباشرةً لم نجدها، ورجعنا صفراً رغم أن الكشف يعرض الرقم أمام
        المستخدم. لذلك: نحدّد أولاً **صفوف** العمال التي يظهر فيها رقم التشغيل
        على أي حركة، ثم نحسب مسموح/٨ من حركات تلك الصفوف كاملة.

        معادلة مسموح/٨ تختلف بين القسمين فتُحسب لكل قسم بمعادلته:
            • المركبين: القبض × ٨ بالألف
            • المصنعين: المفنش ٨ بالالف × ٨ بالألف
        والبحث يشمل كل الفترات (رقم التشغيل فريد عبر الزمن).
        """
        set_number = (set_number or "").strip()
        if not set_number:
            return 0.0

        sections = {}
        for cat, base_type in (("المركبين", "قبض ذهب"),
                               ("المصنعين", "المفنش ٨ بالالف")):
            for name in self.categories.get(cat, []):
                sections.setdefault(name, base_type)

        if not sections:
            return 0.0

        def in_scope(inv):
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"):
                return False
            if inv.get("الاسم") not in sections:
                return False
            if month and not str(inv.get("التاريخ", "")).startswith(month):
                return False
            return True

        # (١) صفوف العمال التي يظهر فيها رقم التشغيل على أي حركة
        target_rows = set()
        for inv in self.invoices.values():
            if not in_scope(inv):
                continue
            if (inv.get("set_number", "") or "").strip() == set_number:
                target_rows.add((inv.get("الاسم"), (inv.get("row_number", "") or "").strip()))

        if not target_rows:
            return 0.0

        # (٢) مسموح/٨ من حركات تلك الصفوف بمعادلة قسم كل عامل
        totals = {}
        for inv in self.invoices.values():
            if not in_scope(inv):
                continue
            key = (inv.get("الاسم"), (inv.get("row_number", "") or "").strip())
            if key not in target_rows:
                continue
            if inv.get("النوع") != sections[inv.get("الاسم")]:
                continue
            totals[key] = totals.get(key, 0.0) + inv.get("الوزن", 0.0)

        return round(sum(v * ALLOWANCE_8 for v in totals.values()), 2)
'''

src = src[:old_start] + new_fn + src[old_end:]

# لا نُخفي أخطاء الجلب: نسجّلها ونوضّح للمستخدم أن الرقم لم يُوجد
rep('''    def autofill_assembler_khayas(self, event=None):
        """يملأ خانة (خياس المركب) تلقائياً حسب رقم التشغيل المكتوب"""
        if not hasattr(self, "sale_khayas_assembler"):
            return
        try:
            value = self.get_assembler_khayas_for_set(self.sale_set_number.get())
            self.sale_khayas_assembler.delete(0, 'end')
            if abs(value) > 0.0001:
                self.sale_khayas_assembler.insert(0, f"{value:g}")
            if hasattr(self, "_recompute_sale_totals"):
                self._recompute_sale_totals()
        except Exception:
            pass   # الجلب التلقائي مساعدة: فشله يجب ألا يمنع الإدخال اليدوي''',
    '''    def autofill_assembler_khayas(self, event=None):
        """يملأ خانة (خياس المركب) تلقائياً حسب رقم التشغيل المكتوب.

        الأخطاء تُسجَّل ولا تُكتم: كتمها سابقاً جعل فشل الجلب يبدو كأن الرقم
        غير موجود، فيصعب تشخيص السبب.
        """
        if not hasattr(self, "sale_khayas_assembler"):
            return
        try:
            value = self.get_assembler_khayas_for_set(self.sale_set_number.get())
            self.sale_khayas_assembler.delete(0, 'end')
            if abs(value) > 0.0001:
                self.sale_khayas_assembler.insert(0, f"{value:g}")
            if hasattr(self, "_recompute_sale_totals"):
                self._recompute_sale_totals()
        except Exception as e:
            log_cloud_error("تعذّر جلب خياس المركب تلقائياً", e)''')


# ==========================================================================
#  ٢) نافذة تعديل كل خانات الصف في المصنعين/المركبين
# ==========================================================================
rep('''        # المصنعين والمركبين: التجميع أصبح برقم الصف، فنعرض تفصيل كل عملية بتاريخها الخاص بدل التعديل المجمّع
        if worker_category in ("المصنعين", "المركبين"):
            self.open_row_operations_detail(worker_name, ref_key)
            return''',
    '''        # المصنعين والمركبين: نافذة تعديل بكل خانات الصف (النقر المزدوج يعرض الكشف)
        if worker_category in ("المصنعين", "المركبين"):
            self.open_row_full_edit_dialog(worker_name, worker_category, ref_key)
            return''')

rep('''    def op_ledger_edit_selected(self):''',
    '''    ROW_EDIT_FIELDS = {
        "المصنعين": [("صرف ذهب", "صرف"), ("قبض ذهب", "قبض/كسر"),
                     ("المفنش ٨ بالالف", "قبض/٨"), ("المفنش ٤ بالالف", "قبض/٤"),
                     ("البوليش", "بوليش"), ("الليز", "الليز"),
                     ("السلك الراجع", "سلك راجع"), ("العيار بعد الفحص", "العيار بعد الفحص")],
        "المركبين": [("صرف ذهب", "صرف"), ("قبض ذهب", "قبض"), ("الليز", "الليز"),
                     ("السلك الراجع", "سلك راجع"), ("العيار بعد الفحص", "العيار بعد الفحص")],
    }

    def open_row_full_edit_dialog(self, worker_name, cat, row_key):
        """تعديل كل خانات صف واحد في كشف المصنعين/المركبين.

        كل عملية في الصف لها حركة مستقلة في الدفاتر. النافذة تعرض قيمة كل
        عملية، والحفظ: يُحدّث الموجود، ويُنشئ ما أُدخل جديداً، ويحذف ما صُفِّر —
        فيبقى الصف مطابقاً لما يظهر في الجدول تماماً.
        """
        if not self.check_edit_permission():
            return

        fields = self.ROW_EDIT_FIELDS.get(cat)
        if not fields:
            return

        row_key = (row_key or "").strip()
        month = self.current_display_month
        row_invs = [inv for inv in self.invoices.values()
                    if inv.get("الاسم") == worker_name
                    and inv.get("settled_status") == "ACTIVE"
                    and (inv.get("row_number", "") or "").strip() == row_key
                    and str(inv.get("التاريخ", "")).startswith(month)]

        if not row_invs:
            messagebox.showwarning("تنبيه", "لم يعد لهذا الصف حركات مسجّلة. حدّث الشاشة وحاول مجدداً.")
            return

        row_invs.sort(key=lambda x: x.get("رقم الفاتورة", 0))
        base = row_invs[0]
        ref_dt = base.get("التاريخ", "")
        cur_set = next((i.get("set_number", "") for i in row_invs if i.get("set_number")), "")
        cur_note = next((i.get("البيان", "") for i in row_invs if i.get("البيان")), "")

        by_type = {}
        for inv in row_invs:
            by_type.setdefault(inv.get("النوع"), inv)

        win = ctk.CTkToplevel(self)
        win.title(f"تعديل الصف ({row_key or 'بدون ترقيم'}) — {worker_name}")
        win.geometry("560x680")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"✏️ تعديل كل خانات الصف ({row_key or 'بدون ترقيم'})",
                     font=("Cairo", 17, "bold"), text_color="#d4af37").pack(pady=(14, 2))
        ctk.CTkLabel(win, text=f"{worker_name} — {cat}", font=("Cairo", 12),
                     text_color="#8b8f95").pack(pady=(0, 8))

        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=4)

        def add_row(label_text, value=""):
            holder = ctk.CTkFrame(body, fg_color="transparent")
            holder.pack(fill="x", pady=4)
            ctk.CTkLabel(holder, text=label_text, font=("Cairo", 14, "bold"),
                         width=160, anchor="e").pack(side="right", padx=8)
            ent = ctk.CTkEntry(holder, justify="center", font=("Cairo", 14), width=150, height=34)
            ent.insert(0, value)
            ent.pack(side="right")
            return ent

        ent_row_no = add_row("رقم الصف", row_key)
        ent_set_no = add_row("رقم التشغيل", cur_set)
        ent_date = add_row("التاريخ", str(ref_dt)[:10])

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=8)

        entries = {}
        for op_type, label in fields:
            existing = by_type.get(op_type)
            val = f"{existing['الوزن']:g}" if existing else ""
            entries[op_type] = add_row(label, val)

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=8)
        ent_note = add_row("البيان", cur_note)

        self.bind_arrow_navigation([ent_row_no, ent_set_no, ent_date]
                                   + [entries[t] for t, _ in fields] + [ent_note])

        def save_row():
            new_row_no = ent_row_no.get().strip()
            new_set_no = ent_set_no.get().strip()
            new_note = ent_note.get().strip()

            new_date = ent_date.get().strip()
            if len(new_date) < 10 or new_date[4] != "-":
                messagebox.showerror("خطأ", "الرجاء إدخال التاريخ بالصيغة YYYY-MM-DD.", parent=win)
                return

            values = {}
            for op_type, label in fields:
                raw = entries[op_type].get().strip()
                if raw == "":
                    values[op_type] = 0.0
                    continue
                try:
                    v = round(float(raw), 2)
                except ValueError:
                    messagebox.showerror("خطأ", f"القيمة في خانة ({label}) ليست رقماً صحيحاً.", parent=win)
                    return
                if v < 0:
                    messagebox.showerror("خطأ", f"لا يمكن إدخال قيمة سالبة في ({label}).", parent=win)
                    return
                values[op_type] = v

            if all(v <= 0 for v in values.values()):
                if not messagebox.askyesno(
                        "تأكيد", "كل الخانات صفر — سيتم حذف حركات هذا الصف بالكامل.\\n"
                        "هل تريد المتابعة؟", parent=win):
                    return

            # الوقت يبقى كما هو ما دام اليوم لم يتغيّر، فلا يتبدّل ترتيب الحركة
            old_time = str(ref_dt)[11:] or datetime.datetime.now().strftime("%H:%M:%S")
            new_dt = f"{new_date} {old_time}"

            blocked = False
            for op_type, _label in fields:
                value = values[op_type]
                existing = by_type.get(op_type)

                # العيار قد يكون صفراً بشكل مشروع، فلا يُحذف بسبب ذلك
                keep_zero = (op_type == "العيار بعد الفحص")

                if value > 0 or (keep_zero and existing and entries[op_type].get().strip() != ""):
                    if existing:
                        existing["الوزن"] = value
                        existing["البيان"] = new_note
                        existing["row_number"] = new_row_no
                        existing["set_number"] = new_set_no
                        existing["التاريخ"] = new_dt
                        if not self.save_invoice_to_db(existing["رقم الفاتورة"], existing):
                            blocked = True
                    else:
                        self.invoice_counter += 1
                        inv_data = {
                            "رقم الفاتورة": self.invoice_counter, "التاريخ": new_dt,
                            "الاسم": worker_name, "النوع": op_type, "الوزن": value,
                            "البيان": new_note, "settled_status": "ACTIVE", "trees_count": 0.0,
                            "قبل": 0.0, "بعد": 0.0, "set_number": new_set_no,
                            "row_number": new_row_no,
                        }
                        self.invoices[self.invoice_counter] = inv_data
                        if not self.save_invoice_to_db(self.invoice_counter, inv_data):
                            blocked = True
                elif existing:
                    if not self.delete_invoice_from_db(existing["رقم الفاتورة"]):
                        blocked = True

            # أي حركة أخرى في الصف (نوع غير معروض) تتبع الترقيم الجديد
            # وإلا انفصلت عن صفها وظهرت كصف مستقل
            handled = {t for t, _ in fields}
            for inv in row_invs:
                if inv.get("النوع") in handled or inv.get("رقم الفاتورة") not in self.invoices:
                    continue
                inv["row_number"] = new_row_no
                inv["set_number"] = new_set_no
                inv["التاريخ"] = new_dt
                if not self.save_invoice_to_db(inv["رقم الفاتورة"], inv):
                    blocked = True

            if blocked:
                return
            self.recalculate_all()
            win.destroy()
            messagebox.showinfo("تم", "تم تحديث كل خانات الصف بنجاح.")

        ctk.CTkButton(win, text="💾 حفظ التعديلات", font=("Cairo", 16, "bold"), fg_color="#2ecc71",
                      hover_color="#27ae60", height=44, width=220, command=save_row).pack(pady=12)

    def op_ledger_edit_selected(self):''')

# النقر المزدوج يعرض الكشف لا التعديل
rep('''        if col_name == "رقم التشغيل":
            self.rename_op_ledger_set_number()
        else:
            self.op_ledger_edit_selected()''',
    '''        if col_name == "رقم التشغيل":
            self.rename_op_ledger_set_number()
        elif self.current_op_cat in ("المصنعين", "المركبين"):
            # النقر المزدوج للعرض، والتعديل من زره المخصّص
            sel = self.op_ledger_tree.selection()
            if sel:
                key = self.op_ledger_group_map.get(sel[0])
                if key is not None:
                    self.open_row_operations_detail(self.combo_op_name.get(), key)
        else:
            self.op_ledger_edit_selected()''')


# ==========================================================================
#  ٣) شريط الإجمالي: ارتفاع ثابت لا ينكمش
# ==========================================================================
rep('''        total_holder = ttk.Frame(wrapper)
        total_holder.pack(side="bottom", fill="x")''',
    '''        # ارتفاع ثابت ومنع الانتشار: يضمن ظهور الشريط دائماً، فقد كان ينكمش
        # إلى صفر عندما يطلب جدول البيانات ارتفاعاً أكبر من المتاح
        total_holder = ttk.Frame(wrapper, height=40)
        total_holder.pack(side="bottom", fill="x")
        total_holder.pack_propagate(False)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة التاسعة عشرة على:", SRC)
