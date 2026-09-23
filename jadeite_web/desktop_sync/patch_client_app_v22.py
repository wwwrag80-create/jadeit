# -*- coding: utf-8 -*-
"""
الدفعة الرابعة عشرة:
  ١) الأعمدة تملأ عرض الجدول كاملاً مع بقاء كل الأعمدة ظاهرة ومرتبة
  ٢) المصنعين/المركبين: عمود الاسم يندمج داخل الجدول كأول عمود (لا جدول منفصل)
     وأسفله: خياس ٨/٤ ورصيد العامل بدل الإجماليات العامة
  ٣) المبيعات: الذهب وخياس التلميع النهائي فقط يؤثران على الخزينة
  ٤) إخفاء خانتَي الوزن القائم/المقيد (الأعمدة تبقى) وإظهار نسبة الخصم
  ٥) الكاستنج: التركيز يعود لرقم الصف بعد الترحيل
  ٦) صناديق الخياس: زر عرض الجدول كاملاً في المصنعين والمركبين

الاستخدام:  python3 patch_client_app_v22.py rageh-1-34-14-cloud.py
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
#  ١) الأعمدة تملأ عرض الجدول كاملاً
# ==========================================================================
rep('''                width = max(min_width, min(max_width, max(header_w, content_w) + padding))
                tree.column(col_id, width=width, minwidth=min_width, stretch=False)
        except Exception:
            pass   # التنسيق تحسين بصري: فشله يجب ألا يمنع عرض الجدول''',
    '''                width = max(min_width, min(max_width, max(header_w, content_w) + padding))
                widths.append(width)

            # توزيع المساحة الفائضة على الأعمدة بالتناسب مع عرضها المطلوب،
            # فيمتلئ الجدول كاملاً بلا فراغ على اليسار وبلا انكماش الأعمدة.
            # لو ضاق الجدول عن المجموع، نُبقي العرض المحسوب ويظهر شريط أفقي
            # بدل قصّ الأعمدة — فلا يختفي عمود أبداً.
            avail = tree.winfo_width()
            if avail <= 1:
                tree.after(120, lambda: self.fit_columns_to_content(
                    tree, table_key, min_width, max_width, padding))
            else:
                total = sum(widths)
                extra = avail - total - 4          # هامش يمنع شريطاً أفقياً زائداً
                if extra > 0 and total > 0:
                    for i in range(len(widths)):
                        widths[i] += int(extra * (widths[i] / total))

            for col_id, width in zip(cols, widths):
                tree.column(col_id, width=width, minwidth=min_width, stretch=False)

            # يُعاد الضبط عند تغيير حجم النافذة ليبقى الجدول ممتلئاً دائماً
            if not getattr(tree, "_fit_bound", False):
                tree.bind("<Configure>",
                          lambda e, t=tree, k=table_key: self.fit_columns_to_content(
                              t, k, min_width, max_width, padding), add="+")
                tree._fit_bound = True
        except Exception:
            pass   # التنسيق تحسين بصري: فشله يجب ألا يمنع عرض الجدول''')

rep('''            children = tree.get_children()
            for i, col_id in enumerate(cols):''',
    '''            children = tree.get_children()
            widths = []
            for i, col_id in enumerate(cols):''')


# ==========================================================================
#  ٢) دمج عمود الاسم داخل جدول المصنعين/المركبين
# ==========================================================================
rep('''        cols = self.build_op_ledger_columns(worker_name, cat)
        show_name_pane = cat in ("المصنعين", "المركبين") and worker_name not in ("الكاستينج", "التلميع النهائي")
        self.op_ledger_name_tree = None

        if show_name_pane:
            self.op_ledger_tree, self.op_ledger_name_tree = self.create_two_pane_ledger_tree(
                self.op_ledger_table_frame, cols, height=11)
        else:
            self.op_ledger_tree = self.create_standard_treeview(self.op_ledger_table_frame, cols, height=11)''',
    '''        cols = self.build_op_ledger_columns(worker_name, cat)
        # عمود الاسم صار جزءاً من الجدول نفسه (أول عمود) بدل جدول منفصل بجانبه،
        # فيبقى الجدول كتلة واحدة مرتبة ويتمرّر معها الاسم تلقائياً
        show_name_col = cat in ("المصنعين", "المركبين") and worker_name not in ("الكاستينج", "التلميع النهائي")
        self.op_ledger_name_tree = None
        if show_name_col:
            cols = ("الاسم",) + tuple(cols)

        self.op_ledger_tree = self.create_standard_treeview(self.op_ledger_table_frame, cols, height=11)''')

rep('''        self.op_ledger_tree.bind("<Double-1>", self._on_op_ledger_double_click)
        if self.op_ledger_name_tree:
            self.op_ledger_name_tree.bind(
                "<Double-1>", lambda e: self.reassign_op_ledger_row(worker_name, cat))''',
    '''        self.op_ledger_tree.bind("<Double-1>", self._on_op_ledger_double_click)''')

# إدراج الاسم كأول قيمة في كل صف
rep('''            if row_id is not None:
                self.op_ledger_group_map[row_id] = gkey
                if self.op_ledger_name_tree is not None:
                    self.op_ledger_name_tree.insert("", "end", values=(worker_name,), tags=("orange_name",))''',
    '''            if row_id is not None:
                self.op_ledger_group_map[row_id] = gkey''')

rep('''        # صف إجمالي فارغ يقابل صف الإجمالي في الجدول الرئيسي، حتى يبقى الجدولان
        # متطابقَي عدد الصفوف تماماً (شرط أساسي لتزامن التمرير بينهما)
        if self.op_ledger_name_tree is not None and ordered:
            self.op_ledger_name_tree.insert("", "end", values=("الإجمالي",), tags=("orange_name",))

''', '''''')


# ==========================================================================
#  ٣) الإجماليات أسفل الجدول: خياس ٨/٤ ورصيد العامل
# ==========================================================================
rep('''                totals_txt = f"الإجماليات — مدين (صرف): {tot['صرف']:.2f}  |  دائن (قبض/كسر+٨+٤+بوليش): {round(tot['قبض'] + tot['مفنش 8'] + tot['مفنش 4'] + tot['بوليش'], 2):.2f}  |  الخياس (الفاقد): {tot['فاقد']:.2f} جم"''',
    '''                totals_txt = (f"خياس ٨/٤: {en(round(tot['مسموح 8'] + tot['مسموح 4'], 2))}"
                              f"   |   رصيد العامل: {en(tot['ذهب صافي'])} جم")''')

rep('''                totals_txt = f"الإجماليات — مدين (صرف): {tot['صرف']:.2f}  |  دائن (قبض): {tot['قبض']:.2f}  |  الخياس (الفاقد): {tot['فاقد']:.2f} جم"''',
    '''                totals_txt = (f"خياس ٨/٤: {en(round(tot['مسموح 8'] + tot['مسموح 4'], 2))}"
                              f"   |   رصيد العامل: {en(tot['ذهب صافي'])} جم")''')


# ==========================================================================
#  ٤) المبيعات: البيان الصحيح لخياس التلميع النهائي في كشف الخزينة
# ==========================================================================
rep('''                    "النوع": "خياس طقوم", "الوزن": khayas_v, "البيان": "خياس طقم",''',
    '''                    # البيان يطابق اسم الصندوق ليظهر واضحاً في كشف حساب الخزينة
                    "النوع": "خياس طقوم", "الوزن": khayas_v, "البيان": "خياس التلميع النهائي",''')


# ==========================================================================
#  ٥) إخفاء خانتَي الوزن القائم/المقيد (الأعمدة تبقى في الجدول)
# ==========================================================================
rep('''        self.sale_weight_standing = add_field("الوزن القائم")
        self.sale_weight_bound = add_field("الوزن المقيد")''',
    '''        # الوزنان يُحسبان تلقائياً ويظهران في الجدول، فلا داعي لخانتَي إدخال لهما.
        # نُبقيهما ككائنين مخفيّين لأن كوداً آخر يقرأ منهما ويكتب فيهما.
        hidden_holder = ctk.CTkFrame(fields_row, fg_color="transparent")
        self.sale_weight_standing = ctk.CTkEntry(hidden_holder, width=1)
        self.sale_weight_bound = ctk.CTkEntry(hidden_holder, width=1)''')


# ==========================================================================
#  ٦) الكاستنج: التركيز يعود لرقم الصف بعد الترحيل
# ==========================================================================
rep('''            self.lbl_op_status.configure(text=f"✅ تم ترحيل حركة الكاستنج لـ ({name})")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))
            self.cast_sarf.focus_set()
            self.refresh_casting_table()''',
    '''            self.lbl_op_status.configure(text=f"✅ تم ترحيل حركة الكاستنج لـ ({name})")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))
            self.refresh_casting_table()
            # التركيز يعود لرقم الصف لتسجيل العملية التالية مباشرة بلا نقر.
            # يُؤجَّل بعد إعادة رسم الجدول لأن إعادة الرسم تسحب التركيز.
            self.after(60, lambda: self.cast_row_num.focus_set())''')


# ==========================================================================
#  ٧) زر عرض الجدول كاملاً في المصنعين والمركبين بصناديق الخياس
# ==========================================================================
rep('''        ctk.CTkButton(btn_row, text="🗑️ حذف صندوق خياس", font=("Cairo", 13, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=170, height=38, command=self.delete_khayas_box_dialog).pack(side="left", padx=5)''',
    '''        ctk.CTkButton(btn_row, text="🗑️ حذف صندوق خياس", font=("Cairo", 13, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=170, height=38, command=self.delete_khayas_box_dialog).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="👁️ عرض الجدول كاملاً", font=("Cairo", 13, "bold"), fg_color="#1f77b4", hover_color="#144d75", width=180, height=38,
                      command=lambda: self.view_treeview_fullscreen(
                          getattr(self, "tree", None),
                          f"عرض كامل — {self.get_display_label(self.current_view_cat)}")).pack(side="left", padx=5)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة الرابعة عشرة على:", SRC)
