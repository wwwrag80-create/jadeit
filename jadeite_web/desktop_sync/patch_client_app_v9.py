# -*- coding: utf-8 -*-
"""
الدفعة التاسعة:
  ١) صف الإجمالي برتقالي في كل جداول صناديق الخياس (وباقي الصفوف أسود)
  ٢) حذف خانة وعمود (الاسم) من أقسام مراحل التصنيع — عدا المصنعين والمركبين
  ٣) الضغط المزدوج على صف يعرض تفاصيل العملية بدل نافذة التعديل
  ٤) صندوق (الصب) الجديد + إمكانية حذف أي صندوق خياس بكل ما يخصه
  ٥) الأرقام بالصيغة الإنجليزية في أشرطة الذهب والخزينة والرصيد الحالي

الاستخدام:  python3 patch_client_app_v9.py rageh-1-34-14-cloud.py
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


ORANGE = "#e67e22"

# ==========================================================================
#  ١) صف الإجمالي برتقالي في كل جداول صناديق الخياس
# ==========================================================================
rep('''        self.tree.tag_configure("green_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("red_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("total_tag", foreground="#000000", font=("Cairo", 14, "bold"))''',
    '''        self.tree.tag_configure("green_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("red_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        # صف الإجمالي برتقالي ليتميّز بوضوح عن باقي الصفوف السوداء
        self.tree.tag_configure("total_tag", foreground="%s", font=("Cairo", 14, "bold"))''' % ORANGE)

rep('''        self.tree.tag_configure("total_tag", foreground="#000000", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self.open_stage_month_detail)''',
    '''        self.tree.tag_configure("total_tag", foreground="%s", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self.open_stage_month_detail)''' % ORANGE)

rep('''        tree.tag_configure("total_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        for c in cols:
            w = 170 if c == "الاسم" else 140 if c == "التاريخ" else 110''',
    '''        tree.tag_configure("total_tag", foreground="%s", font=("Cairo", 13, "bold"))
        for c in cols:
            w = 170 if c == "الاسم" else 140 if c == "التاريخ" else 110''' % ORANGE)

rep('''        sub_tree.tag_configure("total_tag", foreground="#000000", font=("Cairo", 13, "bold"))''',
    '''        sub_tree.tag_configure("total_tag", foreground="%s", font=("Cairo", 13, "bold"))''' % ORANGE)


# ==========================================================================
#  ٢+٣) أقسام مراحل التصنيع: بلا عمود اسم + نافذة تفاصيل بدل التعديل
# ==========================================================================
rep('''    def render_stage_ops_table(self, table_frame, madin_type, qabd_type, height=11,
                               with_trees=False, on_edit=None, totals_label=None,
                               section=None):''',
    '''    def render_stage_ops_table(self, table_frame, madin_type, qabd_type, height=11,
                               with_trees=False, on_edit=None, totals_label=None,
                               section=None, show_name=False, on_detail=None):''')

rep('''        if with_trees:
            cols = ("الصف", "الاسم", "مدين", "دائن", "الخياس", "عدد الأشجار", "خياس كل شجرة", "البيان")
        else:
            cols = ("الصف", "الاسم", "مدين", "دائن", "الخياس", "البيان")''',
    '''        # عمود الاسم يظهر فقط حيث يكون له معنى (المصنعين/المركبين).
        # في باقي الأقسام الاسم هو اسم القسم نفسه فلا فائدة من تكراره في كل صف.
        name_col = ("الاسم",) if show_name else ()
        if with_trees:
            cols = ("الصف",) + name_col + ("مدين", "دائن", "الخياس", "عدد الأشجار", "خياس كل شجرة", "البيان")
        else:
            cols = ("الصف",) + name_col + ("مدين", "دائن", "الخياس", "البيان")''')

rep('''            vals = [row_label, name,
                    f"{g['مدين']:.2f}" if g["مدين"] else "-",''',
    '''            vals = [row_label] + ([name] if show_name else []) + [
                    f"{g['مدين']:.2f}" if g["مدين"] else "-",''')

rep('''            tvals = ["إجمالي الشهر", "-", f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{tot_khayas:.2f}"]''',
    '''            tvals = ["إجمالي الشهر"] + (["-"] if show_name else []) + [
                     f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{tot_khayas:.2f}"]''')

# الضغط المزدوج: تفاصيل بدل تعديل
rep('''        if on_edit:
            tree.bind("<Double-1>", lambda e: on_edit())
        return tree, rows_map''',
    '''        # الضغط المزدوج يعرض تفاصيل العملية. التعديل يبقى متاحاً من زره المخصّص،
        # حتى لا يفتح المستخدم نافذة تعديل بالخطأ وهو يريد الاطّلاع فقط.
        if on_detail:
            tree.bind("<Double-1>", lambda e: on_detail())
        elif on_edit:
            tree.bind("<Double-1>", lambda e: on_edit())
        return tree, rows_map''')

# نافذة التفاصيل
rep('''    def open_stage_op_edit_dialog(self''',
    '''    def show_stage_row_details(self, ids, title):
        """نافذة عرض تفاصيل حركات الصف: التاريخ والوقت والنوع والوزن والبيان.

        للاطّلاع فقط — لا تعديل هنا، فالتعديل له زره المخصّص أعلى الجدول.
        """
        invs = [self.invoices[i] for i in ids if i in self.invoices]
        if not invs:
            messagebox.showwarning("تنبيه", "لم يعد لهذا الصف حركات مسجّلة.")
            return
        invs.sort(key=lambda x: (x.get("التاريخ", ""), x.get("رقم الفاتورة", 0)))

        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("760x480")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ref = invs[0]
        ctk.CTkLabel(win, text=f"📋 تفاصيل الصف ({ref.get('row_number') or 'بدون ترقيم'})",
                     font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=(14, 2))
        ctk.CTkLabel(win, text=f"{ref.get('الاسم', '')}   |   عدد الحركات: {len(invs)}",
                     font=("Cairo", 12), text_color="#8b8f95").pack(pady=(0, 10))

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=16, pady=6)

        cols = ("رقم الحركة", "التاريخ", "الوقت", "النوع", "الوزن", "عدد الأشجار", "البيان")
        tree = self.create_standard_treeview(frame, cols, height=11)
        tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 13, "bold"))
        for c in cols:
            tree.column(c, width=180 if c == "البيان" else 130 if c == "النوع" else 100, anchor="center")

        total_w = 0.0
        for inv in invs:
            dt = str(inv.get("التاريخ", ""))
            total_w = round(total_w + inv.get("الوزن", 0.0), 2)
            tree.insert("", "end", values=(
                inv.get("رقم الفاتورة", "-"),
                dt[:10] or "-",
                dt[11:19] or "-",
                inv.get("النوع", "-"),
                f"{inv.get('الوزن', 0.0):.2f}",
                f"{inv.get('trees_count', 0) or 0:g}" if inv.get("trees_count") else "-",
                inv.get("البيان", "") or "-",
            ))

        tree.insert("", "end", values=("الإجمالي", "-", "-", "-", f"{total_w:.2f}", "-", "-"),
                    tags=("total_tag",))

        ctk.CTkButton(win, text="إغلاق", font=("Cairo", 14, "bold"), width=140, height=38,
                      command=win.destroy).pack(pady=12)

    def open_stage_op_edit_dialog(self''')

# تمرير المعاملات لكل جدول
rep('''            self.cast_table_frame, "صرف كاستنج", "قبض كاستنج", height=11, with_trees=True,
            section="الكاستنج",''',
    '''            self.cast_table_frame, "صرف كاستنج", "قبض كاستنج", height=11, with_trees=True,
            section="الكاستنج", show_name=False,
            on_detail=lambda: self.show_selected_stage_details(
                self.cast_tree, self.cast_table_rows_map, "تفاصيل حركة الكاستنج"),''')

rep('''            self.polish_table_frame, "صرف تلميع", "قبض تلميع", height=11, section="التلميع",''',
    '''            self.polish_table_frame, "صرف تلميع", "قبض تلميع", height=11, section="التلميع",
            show_name=False,
            on_detail=lambda: self.show_selected_stage_details(
                self.polish_tree, self.polish_table_rows_map, "تفاصيل حركة التلميع"),''')

rep('''            self.pbuff_table_frame, "صرف تلميع بف", "قبض تلميع بف", height=11, section="التلميع/البف",''',
    '''            self.pbuff_table_frame, "صرف تلميع بف", "قبض تلميع بف", height=11, section="التلميع/البف",
            show_name=False,
            on_detail=lambda: self.show_selected_stage_details(
                self.pbuff_tree, self.pbuff_table_rows_map, "تفاصيل حركة التلميع/البف"),''')

rep('''            w["table_frame"], madin_type, qabd_type, height=10, section=stage_name,''',
    '''            w["table_frame"], madin_type, qabd_type, height=10, section=stage_name, show_name=False,
            on_detail=lambda s=stage_name: self.show_selected_stage_details(
                self.dynamic_stage_widgets[s]["tree"],
                self.dynamic_stage_widgets[s]["table_rows_map"], f"تفاصيل حركة {s}"),''')

rep('''    def show_stage_row_details(self, ids, title):''',
    '''    def show_selected_stage_details(self, tree, rows_map, title):
        """يفتح تفاصيل الصف المحدد في أي جدول من جداول الأقسام"""
        if not tree:
            return
        sel = tree.selection()
        if not sel:
            return
        ids = (rows_map or {}).get(sel[0])
        if ids:
            self.show_stage_row_details(ids, title)

    def show_stage_row_details(self, ids, title):''')


# ==========================================================================
#  ٢-ب) حذف خانة الاسم من نموذج إدخال الأقسام
# ==========================================================================
rep('''        w["name"] = ctk.CTkComboBox(top, values=self.get_stage_name_values(stage_name, stage_name), font=("Cairo", 15), width=200, height=38, justify="right")
        w["name"].pack(side="right", padx=8)
        w["name"].set("")
        self.bind_name_autocomplete(w["name"], lambda: self.get_stage_name_values(stage_name, stage_name))''',
    '''        # لا خانة اسم في هذه الأقسام: الاسم هو اسم القسم نفسه دائماً،
        # ويُملأ تلقائياً عند الترحيل بلا تدخّل من المستخدم
        w["name"] = None''')

rep('''        nav_fields = [w["name"], w["row_num"], w["sarf"], w["qabd"], w["note"]]''',
    '''        nav_fields = [w["row_num"], w["sarf"], w["qabd"], w["note"]]''')

rep('''        name = w["name"].get().strip() or stage_name''',
    '''        name = stage_name''')

rep('''            w["name"].configure(values=self.get_stage_name_values(stage_name, stage_name))
            w["name"].set("")''',
    '''''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة التاسعة على:", SRC)
