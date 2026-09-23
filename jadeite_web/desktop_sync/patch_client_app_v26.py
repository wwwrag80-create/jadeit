# -*- coding: utf-8 -*-
"""
الدفعة السابعة عشرة — الجزء الأول:
  ١) شاشة المبيعات: إزالة الشريط الأسود عند التمرير (خلفية موحّدة كاملة)
  ٢) مراحل التصنيع: صف الإجمالي ثابت داخل الجدول لا يتحرك مع التمرير
     (في الشاشة وفي العرض الكامل معاً)
  ٣) خياس المركب: يُستخرج من عمود (مسموح/٨) بدل عمود الفاقد

الاستخدام:  python3 patch_client_app_v26.py rageh-1-34-14-cloud.py
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
#  ١) خلفية شاشة المبيعات: لا شريط أسود عند التمرير
# ==========================================================================
rep('''        sales_scroll_outer = ttk.Frame(outer_raw)
        sales_scroll_outer.pack(fill="both", expand=True)''',
    '''        # الحاوية بلون النظام لا ttk.Frame الافتراضي (كان يكشف خلفية سوداء
        # في الفراغ أعلى المحتوى أو أسفله أثناء التمرير)
        sales_scroll_outer = ctk.CTkFrame(outer_raw, fg_color=("#d9d9d9", "#1c1c1c"),
                                           corner_radius=0)
        sales_scroll_outer.pack(fill="both", expand=True)
        try:
            outer_raw.configure(fg_color=("#d9d9d9", "#1c1c1c"))
        except Exception:
            pass''')

rep('''        def _on_sales_canvas_configure(event):
            sales_canvas.itemconfig(sales_canvas_window, width=event.width)''',
    '''        def _on_sales_canvas_configure(event):
            # المحتوى يُمدّد ليملأ عرض وارتفاع اللوحة معاً: بدون تمديد الارتفاع
            # يبقى فراغ أسفل المحتوى تظهر فيه خلفية اللوحة كشريط داكن
            sales_canvas.itemconfig(sales_canvas_window, width=event.width)
            content_h = outer.winfo_reqheight()
            if content_h < event.height:
                sales_canvas.itemconfig(sales_canvas_window, height=event.height)
            else:
                sales_canvas.itemconfig(sales_canvas_window, height="")''')


# ==========================================================================
#  ٢) صف إجمالي ثابت في جداول مراحل التصنيع
# ==========================================================================
rep('''        rows_map = {}
        tot_madin = tot_daen = tot_trees = 0.0''',
    '''        # الإجمالي في شجرة ثابتة أسفل الجدول: يبقى أمام المستخدم أثناء التمرير
        # بدل الاضطرار للنزول لآخر الصفوف لرؤيته
        rows_map = {}
        tot_madin = tot_daen = tot_trees = 0.0''')

rep('''        tree = self.create_standard_treeview(table_frame, cols, height=height)
        tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))''',
    '''        tree, total_tree = self.create_sticky_total_tree(table_frame, cols, height=height)
        tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 13, "bold"))
        tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))''')

rep('''            tree.insert("", "end", values=tuple(tvals), tags=("total_tag",))''',
    '''            total_tree.insert("", "end", values=tuple(tvals), tags=("total_tag",))
            # نحفظ الإجمالي على الجدول ليستخدمه العرض الكامل (الشجرة الثابتة
            # منفصلة، فلا يجده العرض الكامل بقراءة صفوف الجدول وحدها)
            tree._totals_values = tuple(tvals)
            tree._total_tree = total_tree''')

# العرض الكامل يستخدم الإجمالي المحفوظ
rep('''        rows, tags, totals_values = [], [], None
        for iid in children:
            vals = tree.item(iid, "values")
            item_tags = tree.item(iid, "tags") or ()
            if "total_tag" in item_tags:
                totals_values = tuple(vals)
            else:
                rows.append(tuple(vals))
                tags.append("red_tag" if "red_tag" in item_tags else None)''',
    '''        rows, tags, totals_values = [], [], None
        for iid in children:
            vals = tree.item(iid, "values")
            item_tags = tree.item(iid, "tags") or ()
            if "total_tag" in item_tags:
                totals_values = tuple(vals)
            else:
                rows.append(tuple(vals))
                tags.append("red_tag" if "red_tag" in item_tags else None)

        # الجداول ذات الإجمالي الثابت تحفظه على الجدول نفسه
        if totals_values is None:
            totals_values = getattr(tree, "_totals_values", None)''')

# الإجمالي في العرض الكامل ثابت أيضاً (العارض يستخدم create_sticky_total_tree أصلاً)
rep('''        data_tree, total_tree = self.create_sticky_total_tree(body, columns, height=24, col_widths=col_widths)

        for i, row in enumerate(rows):''',
    '''        data_tree, total_tree = self.create_sticky_total_tree(body, columns, height=24, col_widths=col_widths)
        data_tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))

        for i, row in enumerate(rows):''')


# ==========================================================================
#  ٣) كشف المصنعين/المركبين: صف إجمالي ثابت
# ==========================================================================
rep('''        self.op_ledger_tree = self.create_standard_treeview(self.op_ledger_table_frame, cols, height=11)''',
    '''        self.op_ledger_tree, self.op_ledger_total_tree = self.create_sticky_total_tree(
            self.op_ledger_table_frame, cols, height=11)''')

rep('''                self.op_ledger_tree.insert("", "end", values=total_prefix + ("الإجمالي",''',
    '''                self.op_ledger_total_tree.insert("", "end", values=total_prefix + ("الإجمالي",''', count=5)

rep('''        # كشف المصنعين/المركبين هو أعرض جداول النظام: نضغط أعمدته حسب محتواها''',
    '''        # الإجمالي محفوظ على الجدول ليستخدمه العرض الكامل
        try:
            children = self.op_ledger_total_tree.get_children()
            if children:
                self.op_ledger_tree._totals_values = self.op_ledger_total_tree.item(
                    children[0], "values")
        except Exception:
            pass

        # كشف المصنعين/المركبين هو أعرض جداول النظام: نضغط أعمدته حسب محتواها''')


# ==========================================================================
#  ٤) خياس المركب من عمود (مسموح/٨)
# ==========================================================================
rep('''        يبحث في كل عمال قسم (المركبين) عن الحركات المسجّلة بهذا رقم التشغيل،
        ويحسب فاقدها اللحظي بنفس معادلة كشف مراحل التصنيع بالضبط:
            صرف − قبض + ليز − (الراجع/عيار)
        فيبقى الرقم مطابقاً لما يراه المستخدم هناك حرفياً.''',
    '''        يبحث في كل عمال قسم (المركبين) عن الحركات المسجّلة بهذا رقم التشغيل،
        ويحسب قيمة عمود (مسموح/٨) بنفس معادلة كشف مراحل التصنيع بالضبط:
            مسموح/٨ = القبض × ٨ بالألف
        فيبقى الرقم مطابقاً لما يراه المستخدم في ذلك العمود حرفياً.''')

rep('''        total = 0.0
        for d in per_worker.values():
            total += d["صرف"] - d["قبض"] + d["ليز"] - raji_ayar(d["سلك راجع"], d["عيار"])
        return round(total, 2)''',
    '''        # المصدر المعتمد الآن هو عمود (مسموح/٨) لا عمود الفاقد
        total = 0.0
        for d in per_worker.values():
            total += d["قبض"] * ALLOWANCE_8
        return round(total, 2)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة السابعة عشرة على:", SRC)
