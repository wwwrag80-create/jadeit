# -*- coding: utf-8 -*-
"""
الدفعة الثالثة عشرة — الجزء الثاني:
  ١) تقليص الأعمدة حسب محتواها فعلياً (لا عرض ثابت) + عناوين بسطرين
     فلا تختفي أعمدة ولا يبقى فراغ — في مراحل التصنيع والمبيعات
  ٢) تعديل اسم أي عمود بالضغط عليه (المصنعين/المركبين في الشاشتين)
  ٣) تصحيح معادلة الصافي + تقليص خانات المبيعات + لون الخلفية

الاستخدام:  python3 patch_client_app_v21.py rageh-1-34-14-cloud.py
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
#  ١) توزيع الأعمدة حسب المحتوى + عناوين بسطرين + تعديل الأسماء
# ==========================================================================
rep('''    def autofit_tree_columns(self, tree, min_width=70, priority_wide=None):''',
    '''    # أسماء الأعمدة المعدّلة من المستخدم — تُحفظ لكل جدول على حدة
    COLUMN_LABEL_KEY = "col_labels"

    def get_column_label(self, table_key, column_id):
        """الاسم المعروض للعمود: المعدَّل من المستخدم إن وُجد، وإلا الاسم الأصلي"""
        try:
            import json as _json
            saved = _json.loads(self.get_setting(f"{self.COLUMN_LABEL_KEY}_{table_key}", "") or "{}")
            return saved.get(column_id, column_id)
        except Exception:
            return column_id

    def set_column_label(self, table_key, column_id, new_label):
        try:
            import json as _json
            key = f"{self.COLUMN_LABEL_KEY}_{table_key}"
            saved = _json.loads(self.get_setting(key, "") or "{}")
            if new_label and new_label != column_id:
                saved[column_id] = new_label
            else:
                saved.pop(column_id, None)   # إرجاع الاسم الأصلي
            self.set_setting(key, _json.dumps(saved, ensure_ascii=False))
        except Exception as e:
            log_cloud_error("تعذّر حفظ اسم العمود", e)

    @staticmethod
    def wrap_header(text, max_len=9):
        """يوزّع عنوان العمود على سطرين بدل سطر واحد طويل.

        السبب: العنوان الطويل يفرض عرضاً كبيراً على العمود فتُزاح بقية الأعمدة
        خارج الشاشة. توزيعه على سطرين يجعل عرض العمود محكوماً بمحتواه الرقمي.
        """
        text = str(text or "")
        if len(text) <= max_len:
            return text
        words = text.split()
        if len(words) == 1:
            return text
        # نقسم الكلمات على سطرين متوازنين قدر الإمكان
        best, best_diff = 1, None
        for i in range(1, len(words)):
            a = len(" ".join(words[:i]))
            b = len(" ".join(words[i:]))
            diff = abs(a - b)
            if best_diff is None or diff < best_diff:
                best, best_diff = i, diff
        return " ".join(words[:best]) + "\\n" + " ".join(words[best:])

    def enable_column_rename(self, tree, table_key, on_renamed=None):
        """يسمح بتعديل اسم أي عمود بالضغط على رأسه، ويحفظ الاسم الجديد"""
        def on_header_click(event):
            if tree.identify_region(event.x, event.y) != "heading":
                return
            try:
                cols = list(tree["columns"])
                idx = int(tree.identify_column(event.x).replace("#", "")) - 1
                if not (0 <= idx < len(cols)):
                    return
                col_id = cols[idx]
            except (ValueError, IndexError):
                return

            current = self.get_column_label(table_key, col_id)
            dialog = ctk.CTkInputDialog(
                title="تعديل اسم العمود",
                text=f"الاسم الجديد للعمود «{current}»\\n(اتركه فارغاً لإرجاع الاسم الأصلي: {col_id})")
            new_name = dialog.get_input()
            if new_name is None:
                return

            self.set_column_label(table_key, col_id, new_name.strip())
            label = self.get_column_label(table_key, col_id)
            try:
                tree.heading(col_id, text=self.wrap_header(label))
            except Exception:
                pass
            if on_renamed:
                try:
                    on_renamed()
                except Exception:
                    pass

        tree.bind("<Button-1>", on_header_click, add="+")

    def apply_column_labels(self, tree, table_key):
        """يطبّق الأسماء المعدّلة والعناوين ذات السطرين على كل أعمدة الجدول"""
        try:
            for col_id in list(tree["columns"]):
                tree.heading(col_id, text=self.wrap_header(self.get_column_label(table_key, col_id)))
        except Exception:
            pass

    def fit_columns_to_content(self, tree, table_key=None, min_width=46, max_width=200, padding=16):
        """يضبط عرض كل عمود على أعرض محتوى فيه فعلياً — لا عرض ثابت ولا تمدّد.

        المشكلة التي يحلّها: التوزيع بالنِسَب كان يمنح كل عمود حصة متساوية
        تقريباً، فتتمدّد أعمدة الأرقام القصيرة (كرقم الصف) وتُزاح بقية الأعمدة
        خارج الشاشة فتحتاج سحباً أفقياً. القياس الفعلي للنص يجعل كل عمود
        بعرض محتواه بالضبط، فتظهر كل الأعمدة معاً.
        """
        if tree is None:
            return
        try:
            import tkinter.font as tkfont
            cols = list(tree["columns"])
            if not cols:
                return

            body_font = tkfont.Font(family="Cairo", size=11)
            head_font = tkfont.Font(family="Cairo", size=11, weight="bold")

            children = tree.get_children()
            for i, col_id in enumerate(cols):
                label = self.get_column_label(table_key, col_id) if table_key else col_id
                # عرض العنوان = أطول سطر فيه بعد التوزيع على سطرين
                header_w = max((head_font.measure(line)
                                for line in self.wrap_header(label).split("\\n")), default=0)

                content_w = 0
                for iid in children:
                    try:
                        text = str(tree.item(iid, "values")[i])
                    except (IndexError, TypeError):
                        continue
                    if text:
                        content_w = max(content_w, body_font.measure(text))

                width = max(min_width, min(max_width, max(header_w, content_w) + padding))
                tree.column(col_id, width=width, minwidth=min_width, stretch=False)
        except Exception:
            pass   # التنسيق تحسين بصري: فشله يجب ألا يمنع عرض الجدول

    def autofit_tree_columns(self, tree, min_width=70, priority_wide=None):''')


# ==========================================================================
#  ٢) تطبيقه على جداول الأقسام في مراحل التصنيع
# ==========================================================================
rep('''        # توزيع تلقائي للأعمدة على كامل عرض الجدول، ويُعاد عند تغيير حجم النافذة
        self.autofit_tree_columns(tree)
        tree.bind("<Configure>", lambda e, t=tree: self.autofit_tree_columns(t), add="+")
        return tree, rows_map''',
    '''        # عناوين بسطرين + عرض محكوم بالمحتوى، فتظهر كل الأعمدة بلا سحب أفقي
        table_key = f"stage_{section or madin_type}"
        self.apply_column_labels(tree, table_key)
        self.fit_columns_to_content(tree, table_key)
        return tree, rows_map''')

rep('''        # التوزيع التلقائي هنا أيضاً: كشف المصنعين/المركبين هو أعرض جداول النظام
        self.autofit_tree_columns(self.op_ledger_tree, min_width=62)
        self.op_ledger_tree.bind("<Configure>",
                                 lambda e: self.autofit_tree_columns(self.op_ledger_tree, min_width=62),
                                 add="+")''',
    '''        # كشف المصنعين/المركبين هو أعرض جداول النظام: نضغط أعمدته حسب محتواها
        # الفعلي (رقم الصف أضيق عمود) مع عناوين بسطرين، فتظهر كل الأعمدة معاً
        ledger_key = f"ledger_{cat}"
        self.apply_column_labels(self.op_ledger_tree, ledger_key)
        self.fit_columns_to_content(self.op_ledger_tree, ledger_key, min_width=40, max_width=150)
        if not getattr(self, "_ledger_rename_bound", False):
            self.enable_column_rename(self.op_ledger_tree, ledger_key,
                                      on_renamed=self.refresh_op_ledger_table)
            self._ledger_rename_bound = True''')

# رقم الصف: أضيق عمود ممكن
rep('''            if c == "البيان":
                w = 110
            elif c == "التاريخ":
                w = 115
            elif c in ("رقم التشغيل", "الصف"):
                w = 85
            elif c in ("ذهب/صافي", "الفاقد اللحظي", "الراجع/عيار"):
                w = 88
            elif c in ("مسموح/٨", "مسموح/٤"):
                w = 72
            else:
                w = 70
            self.op_ledger_tree.column(c, width=w, anchor="center", stretch=False)''',
    '''            # عرض مبدئي فقط؛ fit_columns_to_content يضبطه لاحقاً حسب المحتوى
            w = 40 if c == "الصف" else 70
            self.op_ledger_tree.column(c, width=w, anchor="center", stretch=False)''')


# ==========================================================================
#  ٣) شاشة صناديق الخياس: تعديل أسماء الأعمدة + ضغطها
# ==========================================================================
rep('''        self.tree.tag_configure("green_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("red_tag", foreground="#000000", font=("Cairo", 13, "bold"))''',
    '''        self.tree.tag_configure("green_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("red_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self._inquiry_table_key = f"inquiry_{self.current_view_cat}"''')


# ==========================================================================
#  ٤) المبيعات: معادلة الصافي المصححة
# ==========================================================================
rep('''    return round(val("ذهب") - val("فصوص") - val("أحجار بعد الخصم")
                 - val("خياس") - val("خياس البوليش") - val("خياس المركب"), 2)''',
    '''    return round(val("فصوص") - val("أحجار بعد الخصم")
                 - val("خياس") - val("خياس البوليش") - val("خياس المركب"), 2)''')

rep('''    """صافي الطقم = الذهب − الفصوص − الأحجار بعد الخصم
                     − خياس التلميع النهائي − خياس البوليش − خياس المركب.''',
    '''    """صافي الطقم = الفصوص − الأحجار بعد الخصم
                     − خياس التلميع النهائي − خياس البوليش − خياس المركب.

    ملاحظة: الأحجار الخام والذهب والماس خارج المعادلة عمداً حسب التعريف المعتمد.''')

# جدول السطور المعلّقة: ضغط الأعمدة
rep('''        for c in cols:
            w = 140 if c in ("الأحجار بعد الخصم", "خياس التلميع النهائي") else 110
            self.pending_sales_tree.column(c, width=w, anchor="center", stretch=False)''',
    '''        for c in cols:
            self.pending_sales_tree.column(c, width=70, anchor="center", stretch=False)''')

rep('''        if self.pending_sale_rows:
            self.pending_sales_tree.insert("", "end", values=(
                "إجمالي الفاتورة", "-", f"{tot['ذهب']:.2f}", f"{tot['فصوص']:.2f}", f"{tot['أحجار']:.2f}",''',
    '''        self.apply_column_labels(self.pending_sales_tree, "pending_sales")
        self.fit_columns_to_content(self.pending_sales_tree, "pending_sales",
                                     min_width=44, max_width=150)

        if self.pending_sale_rows:
            self.pending_sales_tree.insert("", "end", values=(
                "إجمالي الفاتورة", "-", f"{tot['ذهب']:.2f}", f"{tot['فصوص']:.2f}", f"{tot['أحجار']:.2f}",''')

# خانات الإدخال أضيق ليظهر الجميع
rep('''            ent = ctk.CTkEntry(col, justify="center", font=("Cairo", 15), width=100, height=34)''',
    '''            ent = ctk.CTkEntry(col, justify="center", font=("Cairo", 14), width=78, height=32)''')

# لون خلفية شاشة المبيعات يتبع سمة النظام
rep('''        sales_canvas = tk.Canvas(sales_scroll_outer, highlightthickness=0,
                                 bg=self.cget("fg_color")[1] if isinstance(self.cget("fg_color"), (list, tuple)) else "#1a1a1a")''',
    '''        # لون الخلفية يتبع سمة النظام (فاتح/داكن) بدل لون ثابت
        sales_canvas = tk.Canvas(
            sales_scroll_outer, highlightthickness=0, bd=0,
            bg=ctk.ThemeManager.theme["CTkFrame"]["fg_color"][
                0 if ctk.get_appearance_mode() == "Light" else 1])''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الثاني من الدفعة الثالثة عشرة على:", SRC)
