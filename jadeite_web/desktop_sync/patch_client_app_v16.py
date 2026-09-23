# -*- coding: utf-8 -*-
"""
الدفعة الحادية عشرة — الجزء الرابع:
  ٣) صندوق خياس الطقوم: عمودا (الصافي) و(الخسارة) مع كشف تفصيلي عند الضغط
  ٤) مراحل التصنيع: توزيع تلقائي منظّم لعرض الأعمدة (يملأ الجدول بلا فراغ)
     + التنقل بالأسهم بين خانات العمليات + عودة التركيز لرقم الصف بعد الترحيل

الاستخدام:  python3 patch_client_app_v16.py rageh-1-34-14-cloud.py
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
#  ٣) صندوق خياس الطقوم: الصافي والخسارة
# ==========================================================================
rep('''    def get_stage_monthly_tree_totals(self, cat, month):''',
    '''    def get_sets_net_rows(self, month):
        """صافي كل طقم (رقم تشغيل) خلال شهر معيّن، من سطور الصافي المرحّلة
        في شاشة المبيعات/الصادر.

        الفصل المحاسبي المطلوب: الصافي الموجب يُعرض في عمود (الصافي)،
        والسالب يُعرض في عمود (الخسارة) — فلا يظهر رقم واحد في العمودين.
        يرجع: [(رقم التشغيل, الصافي, الخسارة)]
        """
        rows = {}
        for inv in self.invoices.values():
            if inv.get("النوع") != "خياس طقوم":
                continue
            if (inv.get("trees_count", 0.0) or 0.0) != KHAYAS_MARK_NET:
                continue
            if not str(inv.get("التاريخ", "")).startswith(month):
                continue
            key = inv.get("set_number", "") or "-"
            rows[key] = round(rows.get(key, 0.0) + inv.get("الوزن", 0.0), 2)

        out = []
        for set_no, net in sorted(rows.items()):
            if net < 0:
                out.append((set_no, 0.0, round(abs(net), 2)))
            else:
                out.append((set_no, net, 0.0))
        return out

    def get_sets_net_totals(self, month):
        """إجمالي الصافي وإجمالي الخسارة لشهر معيّن"""
        rows = self.get_sets_net_rows(month)
        return (round(sum(r[1] for r in rows), 2), round(sum(r[2] for r in rows), 2))

    def show_sets_net_detail(self, month, losses_only=False):
        """كشف تفصيلي: رقم التشغيل + الصافي (أو الخسارة) لكل طقم في الشهر"""
        rows = self.get_sets_net_rows(month)
        if losses_only:
            rows = [r for r in rows if r[2] > 0]
            title = f"كشف خسائر الطقوم — {month}"
            cols = ("رقم التشغيل", "الخسارة")
            data = [(r[0], f"{r[2]:.2f}") for r in rows]
            total = (f"الإجمالي", f"{sum(r[2] for r in rows):.2f}")
        else:
            rows = [r for r in rows if r[1] > 0]
            title = f"كشف صافي الطقوم — {month}"
            cols = ("رقم التشغيل", "الصافي")
            data = [(r[0], f"{r[1]:.2f}") for r in rows]
            total = (f"الإجمالي", f"{sum(r[1] for r in rows):.2f}")

        if not data:
            messagebox.showinfo("لا يوجد", f"لا توجد بيانات لعرضها في {title}.")
            return

        self.open_fullscreen_table_view(title, cols, data, totals_values=total)

    def get_stage_monthly_tree_totals(self, cat, month):''')

# أعمدة الصافي والخسارة في جدول خياس الطقوم الشهري
rep('''        show_trees = (cat == "الكاستنج")''',
    '''        show_trees = (cat == "الكاستنج")
        show_net = (cat == "خياس الطقوم")''')

rep('''        columns = ("الشهر والسنة", "مدين", "دائن", "الرصيد")
        if show_trees:
            columns = columns + ("عدد الأشجار", "خياس كل شجرة")''',
    '''        columns = ("الشهر والسنة", "مدين", "دائن", "الرصيد")
        if show_trees:
            columns = columns + ("عدد الأشجار", "خياس كل شجرة")
        if show_net:
            columns = columns + ("الصافي", "الخسارة")''')

rep('''            if show_trees:
                m_trees, m_per_tree = self.get_stage_monthly_tree_totals(cat, m)
                grand_trees += m_trees
                vals += [f"{m_trees:g}" if m_trees else "-", f"{m_per_tree:.2f}" if m_trees else "-"]''',
    '''            if show_trees:
                m_trees, m_per_tree = self.get_stage_monthly_tree_totals(cat, m)
                grand_trees += m_trees
                vals += [f"{m_trees:g}" if m_trees else "-", f"{m_per_tree:.2f}" if m_trees else "-"]
            if show_net:
                m_net, m_loss = self.get_sets_net_totals(m)
                grand_net += m_net
                grand_loss += m_loss
                vals += [f"{m_net:.2f}" if m_net else "-", f"{m_loss:.2f}" if m_loss else "-"]''')

rep('''        running = 0.0
        grand_trees = 0.0
        for m in sorted(months):''',
    '''        running = 0.0
        grand_trees = 0.0
        grand_net = grand_loss = 0.0
        for m in sorted(months):''')

rep('''            if show_trees:
                overall_per_tree = round(running / grand_trees, 2) if grand_trees else 0.0
                total_vals += [f"{grand_trees:g}" if grand_trees else "-",
                               f"{overall_per_tree:.2f}" if grand_trees else "-"]''',
    '''            if show_trees:
                overall_per_tree = round(running / grand_trees, 2) if grand_trees else 0.0
                total_vals += [f"{grand_trees:g}" if grand_trees else "-",
                               f"{overall_per_tree:.2f}" if grand_trees else "-"]
            if show_net:
                total_vals += [f"{grand_net:.2f}" if grand_net else "-",
                               f"{grand_loss:.2f}" if grand_loss else "-"]''')

# الضغط على عمود الصافي/الخسارة يفتح الكشف
rep('''        self.tree.bind("<Double-1>", self.open_stage_month_detail)

        months = set()''',
    '''        self.tree.bind("<Double-1>", self._on_stage_monthly_click)

        months = set()''')

rep('''    def view_stage_monthly_fullscreen(self, cat):''',
    '''    def _on_stage_monthly_click(self, event=None):
        """الضغط على عمود الصافي أو الخسارة يفتح كشفه التفصيلي،
        وأي عمود آخر يفتح تفاصيل حركات الشهر كالمعتاد."""
        if self.current_view_cat == "خياس الطقوم" and event is not None:
            try:
                cols = self.tree["columns"]
                idx = int(self.tree.identify_column(event.x).replace("#", "")) - 1
                col_name = cols[idx] if 0 <= idx < len(cols) else ""
            except (ValueError, IndexError):
                col_name = ""

            if col_name in ("الصافي", "الخسارة"):
                sel = self.tree.selection()
                if not sel:
                    return
                month = self.stage_month_rows_map.get(sel[0])
                if month:
                    self.show_sets_net_detail(month, losses_only=(col_name == "الخسارة"))
                return

        self.open_stage_month_detail(event)

    def view_stage_monthly_fullscreen(self, cat):''')


# ==========================================================================
#  ٤) توزيع تلقائي منظّم لعرض الأعمدة في كل جداول مراحل التصنيع
# ==========================================================================
rep('''    def create_standard_treeview(self, parent, columns, height=15):''',
    '''    def autofit_tree_columns(self, tree, min_width=70, priority_wide=None):
        """يوزّع عرض الأعمدة على كامل عرض الجدول تلقائياً.

        المشكلة التي يحلّها: الأعمدة كانت بعرض ثابت، فتتكدّس في نصف الجدول
        ويبقى النصف الآخر فارغاً على الشاشات العريضة. الآن تُوزَّع المساحة
        كاملة بلا تدخّل، مع إعطاء أعمدة النصوص (كالبيان والاسم) وزناً أكبر
        لأنها تحتاج مساحة أكثر من الأعمدة الرقمية.
        """
        if tree is None:
            return
        try:
            cols = list(tree["columns"])
            if not cols:
                return

            wide = set(priority_wide or ("البيان", "الاسم", "التاريخ", "رقم التشغيل"))
            weights = {c: (1.7 if c in wide else 1.0) for c in cols}
            total_weight = sum(weights.values())

            avail = tree.winfo_width()
            if avail <= 1:
                # الجدول لم يُرسم بعد: نعيد المحاولة بعد اكتمال التخطيط
                tree.after(120, lambda: self.autofit_tree_columns(tree, min_width, priority_wide))
                return

            avail -= 4   # هامش بسيط يمنع ظهور شريط تمرير أفقي بلا داعٍ
            for c in cols:
                w = int(avail * (weights[c] / total_weight))
                tree.column(c, width=max(min_width, w), minwidth=min_width, stretch=True)
        except Exception:
            pass   # التنسيق تحسين بصري: فشله يجب ألا يمنع عرض الجدول

    def create_standard_treeview(self, parent, columns, height=15):''')

# تطبيق التوزيع على جداول الأقسام وكشف المصنعين/المركبين
rep('''        if on_detail:
            tree.bind("<Double-1>", lambda e: on_detail())
        elif on_edit:
            tree.bind("<Double-1>", lambda e: on_edit())
        return tree, rows_map''',
    '''        if on_detail:
            tree.bind("<Double-1>", lambda e: on_detail())
        elif on_edit:
            tree.bind("<Double-1>", lambda e: on_edit())

        # توزيع تلقائي للأعمدة على كامل عرض الجدول، ويُعاد عند تغيير حجم النافذة
        self.autofit_tree_columns(tree)
        tree.bind("<Configure>", lambda e, t=tree: self.autofit_tree_columns(t), add="+")
        return tree, rows_map''')

rep('''        if hasattr(self, 'lbl_op_ledger_totals'):
            self.lbl_op_ledger_totals.configure(text=totals_txt)''',
    '''        if hasattr(self, 'lbl_op_ledger_totals'):
            self.lbl_op_ledger_totals.configure(text=totals_txt)

        # التوزيع التلقائي هنا أيضاً: كشف المصنعين/المركبين هو أعرض جداول النظام
        self.autofit_tree_columns(self.op_ledger_tree, min_width=62)
        self.op_ledger_tree.bind("<Configure>",
                                 lambda e: self.autofit_tree_columns(self.op_ledger_tree, min_width=62),
                                 add="+")''')


# ==========================================================================
#  ٤-ب) الكاستنج: عودة التركيز لرقم الصف بعد الترحيل + التنقل بالأسهم
# ==========================================================================
rep('''            self.cast_sarf.delete(0, 'end')
            self.cast_qabd.delete(0, 'end')
            self.cast_trees.delete(0, 'end')
            self.cast_note.delete(0, 'end')
            self.cast_row_num.delete(0, 'end')''',
    '''            self.cast_sarf.delete(0, 'end')
            self.cast_qabd.delete(0, 'end')
            self.cast_trees.delete(0, 'end')
            self.cast_note.delete(0, 'end')
            self.cast_row_num.delete(0, 'end')
            # التركيز يعود لرقم الصف مباشرة ليبدأ تسجيل العملية التالية بلا نقر
            self.cast_row_num.focus_set()''')

rep('''        cast_nav_fields = [self.cast_name, self.cast_row_num, self.cast_sarf, self.cast_qabd, self.cast_trees, self.cast_note]''',
    '''        cast_nav_fields = [self.cast_name, self.cast_row_num, self.cast_sarf, self.cast_qabd, self.cast_trees, self.cast_note]
        self.bind_arrow_navigation(cast_nav_fields)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الرابع من الدفعة الحادية عشرة على:", SRC)
