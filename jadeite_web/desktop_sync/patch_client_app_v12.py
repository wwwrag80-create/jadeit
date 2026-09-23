# -*- coding: utf-8 -*-
"""
الدفعة العاشرة — الجزء الثالث:
  ١) زر «👁️ عرض» بجانب «تعديل الحركة المحددة» في كل قسم بمراحل التصنيع:
     الكاستنج، التلميع، التلميع/البف، الأقسام المضافة، والمصنعين/المركبين
     (كل زر يفتح الجدول الحالي بملء الشاشة مع صف إجمالي ثابت)
  ٢) شريط تمرير عمودي في شاشة المبيعات/الصادر (الشاشة كاملة، لا الجداول فقط)

الاستخدام:  python3 patch_client_app_v12.py rageh-1-34-14-cloud.py
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
#  ١) دالة عامة تجمع بيانات أي Treeview الحالي وتفتحه بملء الشاشة
# ==========================================================================
rep('''    def open_fullscreen_table_view(self, title, columns, rows, totals_values=None,
                                   col_widths=None, row_tags=None):''',
    '''    def view_treeview_fullscreen(self, tree, title, name_tree=None):
        """يقرأ محتوى Treeview ظاهر حالياً في الشاشة (بيانات + إجمالي إن وُجد)
        ويعرضه بملء الشاشة بنفس الآلية العامة، بدل إعادة حساب البيانات من
        الصفر — فما تراه بالضبط هو ما يُعرض بملء الشاشة، بلا احتمال تعارض."""
        if tree is None:
            messagebox.showinfo("تنبيه", "لا يوجد جدول لعرضه حالياً.")
            return

        columns = list(tree["columns"])
        children = tree.get_children()
        if not children:
            messagebox.showinfo("تنبيه", "الجدول فارغ حالياً — لا يوجد ما يُعرض.")
            return

        # صف الإجمالي هو آخر صف موسوم total_tag إن وُجد، وباقي الصفوف بيانات
        rows, tags, totals_values = [], [], None
        for iid in children:
            vals = tree.item(iid, "values")
            item_tags = tree.item(iid, "tags") or ()
            if "total_tag" in item_tags:
                totals_values = tuple(vals)
            else:
                rows.append(tuple(vals))
                tags.append("red_tag" if "red_tag" in item_tags else None)

        # عمود الاسم (إن وُجد كجدول منفصل) يُدمَج كعمود أول في العرض الكامل
        if name_tree is not None:
            name_children = name_tree.get_children()
            merged_rows = []
            for i, r in enumerate(rows):
                nm = name_tree.item(name_children[i], "values")[0] if i < len(name_children) else ""
                merged_rows.append((nm,) + r)
            rows = merged_rows
            columns = ["الاسم"] + columns
            if totals_values is not None:
                totals_values = ("الإجمالي",) + totals_values[1:]

        self.open_fullscreen_table_view(title, tuple(columns), rows,
                                        totals_values=totals_values, row_tags=tags)

    def open_fullscreen_table_view(self, title, columns, rows, totals_values=None,
                                   col_widths=None, row_tags=None):''')


# ==========================================================================
#  ٢) زر «عرض» في كل قسم — يقرأ الجدول المعروض حالياً كما هو
# ==========================================================================
rep('''        self.build_negative_color_button(table_top, "الكاستنج", self.refresh_casting_table)

        btn_edit_cast = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_casting_row)''',
    '''        self.build_negative_color_button(table_top, "الكاستنج", self.refresh_casting_table)

        ctk.CTkButton(table_top, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda: self.view_treeview_fullscreen(
                          self.cast_tree, f"عرض كامل — {self.get_display_label('الكاستنج')}")
                      ).pack(side="left", padx=5)

        btn_edit_cast = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_casting_row)''')

rep('''        self.build_negative_color_button(table_top, "التلميع", self.refresh_polish_table)

        btn_edit_pol = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_polish_row)''',
    '''        self.build_negative_color_button(table_top, "التلميع", self.refresh_polish_table)

        ctk.CTkButton(table_top, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda: self.view_treeview_fullscreen(
                          self.polish_tree, f"عرض كامل — {self.get_display_label('التلميع')}")
                      ).pack(side="left", padx=5)

        btn_edit_pol = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_polish_row)''')

rep('''        self.build_negative_color_button(table_top, "التلميع/البف", self.refresh_polish_buff_table)

        btn_edit = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_polish_buff_row)''',
    '''        self.build_negative_color_button(table_top, "التلميع/البف", self.refresh_polish_buff_table)

        ctk.CTkButton(table_top, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda: self.view_treeview_fullscreen(
                          self.pbuff_tree, f"عرض كامل — {self.get_display_label('التلميع/البف')}")
                      ).pack(side="left", padx=5)

        btn_edit = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_polish_buff_row)''')

# الأقسام المضافة ديناميكياً
rep('''        self.build_negative_color_button(
            table_top, stage_name, lambda s=stage_name: self.refresh_generic_stage_table(s))

        btn_edit = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=lambda: self.edit_selected_generic_stage_row(stage_name))''',
    '''        self.build_negative_color_button(
            table_top, stage_name, lambda s=stage_name: self.refresh_generic_stage_table(s))

        ctk.CTkButton(table_top, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda s=stage_name: self.view_treeview_fullscreen(
                          self.dynamic_stage_widgets.get(s, {}).get("tree"), f"عرض كامل — {s}")
                      ).pack(side="left", padx=5)

        btn_edit = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=lambda: self.edit_selected_generic_stage_row(stage_name))''')

# المصنعين/المركبين: يمرّر جدول الاسم أيضاً ليُدمَج في العرض الكامل
rep('''        btn_edit_row = ctk.CTkButton(ledger_header, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.op_ledger_edit_selected)''',
    '''        ctk.CTkButton(ledger_header, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda: self.view_treeview_fullscreen(
                          self.op_ledger_tree, f"عرض كامل — {self.combo_op_name.get()}",
                          name_tree=self.op_ledger_name_tree)
                      ).pack(side="left", padx=5)

        btn_edit_row = ctk.CTkButton(ledger_header, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.op_ledger_edit_selected)''')


# ==========================================================================
#  ٣) شريط تمرير عمودي لكامل شاشة المبيعات/الصادر
# ==========================================================================
rep('''    def build_sales_tab(self):
        outer = self.tabview.tab("المبيعات")''',
    '''    def build_sales_tab(self):
        outer_raw = self.tabview.tab("المبيعات")

        # الشاشة تحوي عدداً كبيراً من الحقول والجداول، وبدون تمرير كانت
        # عناصرها السفلية تُقطع على الشاشات الأصغر بلا وسيلة للوصول إليها.
        sales_scroll_outer = ttk.Frame(outer_raw)
        sales_scroll_outer.pack(fill="both", expand=True)

        sales_canvas = tk.Canvas(sales_scroll_outer, highlightthickness=0,
                                 bg=self.cget("fg_color")[1] if isinstance(self.cget("fg_color"), (list, tuple)) else "#1a1a1a")
        sales_vsb = ttk.Scrollbar(sales_scroll_outer, orient="vertical", command=sales_canvas.yview)
        sales_canvas.configure(yscrollcommand=sales_vsb.set)
        sales_vsb.pack(side="right", fill="y")
        sales_canvas.pack(side="left", fill="both", expand=True)

        outer = ctk.CTkFrame(sales_canvas, fg_color="transparent")
        sales_canvas_window = sales_canvas.create_window((0, 0), window=outer, anchor="nw")

        def _on_sales_frame_configure(event=None):
            sales_canvas.configure(scrollregion=sales_canvas.bbox("all"))

        def _on_sales_canvas_configure(event):
            sales_canvas.itemconfig(sales_canvas_window, width=event.width)

        outer.bind("<Configure>", _on_sales_frame_configure)
        sales_canvas.bind("<Configure>", _on_sales_canvas_configure)

        def _sales_mousewheel(event):
            sales_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        sales_canvas.bind("<Enter>", lambda e: sales_canvas.bind_all("<MouseWheel>", _sales_mousewheel))
        sales_canvas.bind("<Leave>", lambda e: sales_canvas.unbind_all("<MouseWheel>"))''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الثالث من الدفعة العاشرة على:", SRC)
