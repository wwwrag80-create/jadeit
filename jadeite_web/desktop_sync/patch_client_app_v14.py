# -*- coding: utf-8 -*-
"""
الدفعة الحادية عشرة — الجزء الثاني (شاشة المبيعات/الصادر):
  • خانة (خياس) → (خياس التلميع النهائي) + خانة جديدة (خياس البوليش)
  • عمود (الصافي) = الذهب − الفصوص − الأحجار بعد الخصم − خياس التلميع − خياس البوليش
  • عمودا الوزن القائم والوزن المقيد في الجدول
  • زر ترحيل الفاتورة أعلى الجدول
  • التنقل بين الخانات بالأسهم يمين/يسار

الاستخدام:  python3 patch_client_app_v14.py rageh-1-34-14-cloud.py
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
#  ١) دالة حساب الصافي — مصدر واحد يستخدمه الجدول والقالب والصناديق
# ==========================================================================
rep('''def raji_ayar(wire_back, karat):''',
    '''def sale_net_weight(row):
    """صافي الطقم = الذهب − الفصوص − الأحجار بعد الخصم − خياس التلميع − خياس البوليش.

    مصدر واحد للحساب يستخدمه: جدول السطور المعلّقة، قالب الطباعة، وصندوق
    خياس الطقوم — فلا يختلف الرقم بين شاشة وأخرى مهما تغيّرت المعادلة لاحقاً.
    """
    def val(key):
        try:
            return float(row.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return round(val("ذهب") - val("فصوص") - val("أحجار بعد الخصم")
                 - val("خياس") - val("خياس البوليش"), 2)


def raji_ayar(wire_back, karat):''')


# ==========================================================================
#  ٢) الخانتان: إعادة التسمية + خانة البوليش الجديدة
# ==========================================================================
rep('''        self.sale_khayas = add_field("خياس")
        self.sale_diamond = add_field("الماس")''',
    '''        self.sale_khayas = add_field("خياس التلميع النهائي")
        self.sale_khayas_polish = add_field("خياس البوليش")
        self.sale_diamond = add_field("الماس")''')

rep('''        nav_fields = [self.sale_name, self.sale_row_number, self.sale_set_number, self.sale_gold, self.sale_gems,
                      self.sale_stones, self.sale_stones_discount, self.sale_khayas, self.sale_diamond]
        for i, f in enumerate(nav_fields[:-1]):
            f.bind("<Return>", lambda e, nxt=nav_fields[i + 1]: nxt.focus_set() or "break")
        nav_fields[-1].bind("<Return>", lambda e: self.stage_sale_row() or "break")''',
    '''        nav_fields = [self.sale_name, self.sale_row_number, self.sale_set_number, self.sale_gold, self.sale_gems,
                      self.sale_stones, self.sale_stones_discount, self.sale_khayas, self.sale_khayas_polish,
                      self.sale_diamond]
        for i, f in enumerate(nav_fields[:-1]):
            f.bind("<Return>", lambda e, nxt=nav_fields[i + 1]: nxt.focus_set() or "break")
        nav_fields[-1].bind("<Return>", lambda e: self.stage_sale_row() or "break")

        # التنقل بالأسهم يمين/يسار بين الخانات.
        # الترتيب معكوس عمداً: الخانات مرصوفة من اليمين لليسار (side="right")،
        # فالسهم الأيسر ينتقل للخانة التالية بصرياً، والأيمن للسابقة.
        self.bind_arrow_navigation(nav_fields)''')

rep('''    def stage_sale_row(self):''',
    '''    def bind_arrow_navigation(self, fields):
        """تنقّل بالأسهم يمين/يسار بين خانات الإدخال المرصوفة من اليمين لليسار.

        لا يتدخّل عندما يكون المؤشر داخل النص: السهم الأيسر ينتقل للخانة
        التالية فقط إذا كان المؤشر في نهاية النص، والأيمن فقط إذا كان في
        بدايته — حتى يبقى تحريك المؤشر داخل الرقم ممكناً كالمعتاد.
        """
        widgets = [f for f in fields if f is not None]

        def go(idx, event):
            if 0 <= idx < len(widgets):
                widgets[idx].focus_set()
                return "break"
            return None

        for i, field in enumerate(widgets):
            def on_left(e, i=i):
                try:
                    if e.widget.index("insert") < len(e.widget.get()):
                        return None      # المؤشر داخل النص: دع السهم يحرّكه
                except Exception:
                    pass
                return go(i + 1, e)

            def on_right(e, i=i):
                try:
                    if e.widget.index("insert") > 0:
                        return None
                except Exception:
                    pass
                return go(i - 1, e)

            try:
                field.bind("<Left>", on_left)
                field.bind("<Right>", on_right)
            except Exception:
                pass

    def stage_sale_row(self):''')


# ==========================================================================
#  ٣) قراءة الخانة الجديدة عند إضافة السطر
# ==========================================================================
rep('''        khayas_v = safe_val(self.sale_khayas)''',
    '''        khayas_v = safe_val(self.sale_khayas)
        khayas_polish_v = safe_val(self.sale_khayas_polish)''')

rep('''        if gold_v <= 0 and gems_v <= 0 and stones_v <= 0 and diamond_v <= 0 and khayas_v <= 0:
            messagebox.showwarning("تنبيه", "الرجاء إدخال قيمة واحدة على الأقل (ذهب/فصوص/أحجار/ماس/خياس).")
            return
        if khayas_v < 0:
            messagebox.showwarning("تنبيه", "لا يمكن إدخال خياس بالسالب.")
            return''',
    '''        if (gold_v <= 0 and gems_v <= 0 and stones_v <= 0 and diamond_v <= 0
                and khayas_v <= 0 and khayas_polish_v <= 0):
            messagebox.showwarning("تنبيه", "الرجاء إدخال قيمة واحدة على الأقل (ذهب/فصوص/أحجار/ماس/خياس).")
            return
        if khayas_v < 0 or khayas_polish_v < 0:
            messagebox.showwarning("تنبيه", "لا يمكن إدخال خياس بالسالب.")
            return''')

rep('''            "أحجار بعد الخصم": stones_discount_v, "الماس": diamond_v, "خياس": khayas_v
        })''',
    '''            "أحجار بعد الخصم": stones_discount_v, "الماس": diamond_v, "خياس": khayas_v,
            "خياس البوليش": khayas_polish_v
        })''')

rep('''        self.sale_row_number.delete(0, 'end')
        self.sale_khayas.delete(0, 'end')
        self.sale_set_number.delete(0, 'end')''',
    '''        self.sale_row_number.delete(0, 'end')
        self.sale_khayas.delete(0, 'end')
        self.sale_khayas_polish.delete(0, 'end')
        self.sale_set_number.delete(0, 'end')''')


# ==========================================================================
#  ٤) الجدول: أعمدة الصافي والوزن القائم والمقيد + زر الترحيل أعلاه
# ==========================================================================
rep('''        cols = ("رقم الصف", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم", "الماس", "خياس")
        self.pending_sales_tree = self.create_standard_treeview(self.pending_sales_table_frame, cols, height=6)
        self.pending_sales_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        for c in cols:
            self.pending_sales_tree.column(c, width=130, anchor="center")

        tot_gold = tot_gems = tot_stones = tot_diamond = tot_khayas = tot_disc = 0.0
        for row in self.pending_sale_rows:
            tot_gold += row.get("ذهب", 0.0); tot_gems += row.get("فصوص", 0.0)
            tot_stones += row.get("أحجار", 0.0); tot_diamond += row.get("الماس", 0.0)
            tot_khayas += row.get("خياس", 0.0)
            try:
                tot_disc += float(row.get("أحجار بعد الخصم", 0.0) or 0.0)
            except (TypeError, ValueError):
                pass
            self.pending_sales_tree.insert("", "end", values=(
                row.get("row_number", "") or "-",
                row.get("set_number", "") or "-",
                f"{row['ذهب']:.2f}" if row.get("ذهب") else "-",
                f"{row['فصوص']:.2f}" if row.get("فصوص") else "-",
                f"{row['أحجار']:.2f}" if row.get("أحجار") else "-",
                f"{float(row.get('أحجار بعد الخصم', 0) or 0):.2f}" if row.get("أحجار بعد الخصم") else "-",
                f"{row['الماس']:.2f}" if row.get("الماس") else "-",
                f"{row['خياس']:.2f}" if row.get("خياس") else "-",
            ))

        if self.pending_sale_rows:
            self.pending_sales_tree.insert("", "end", values=(
                "إجمالي الفاتورة", "-", f"{tot_gold:.2f}", f"{tot_gems:.2f}", f"{tot_stones:.2f}",
                f"{tot_disc:.2f}", f"{tot_diamond:.2f}", f"{tot_khayas:.2f}"), tags=("total_tag",))''',
    '''        cols = ("رقم الصف", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم",
                "الماس", "خياس التلميع النهائي", "خياس البوليش", "الصافي",
                "الوزن القائم", "الوزن المقيد")
        self.pending_sales_tree = self.create_standard_treeview(self.pending_sales_table_frame, cols, height=6)
        self.pending_sales_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 13, "bold"))
        for c in cols:
            w = 140 if c in ("الأحجار بعد الخصم", "خياس التلميع النهائي") else 110
            self.pending_sales_tree.column(c, width=w, anchor="center", stretch=False)

        tot = dict.fromkeys(["ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس",
                             "خياس", "خياس البوليش", "الصافي", "القائم", "المقيد"], 0.0)

        def num(row, key):
            try:
                return float(row.get(key, 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        for row in self.pending_sale_rows:
            net = sale_net_weight(row)
            # الوزن القائم يحسب الأحجار الخام، والمقيد يحسبها بعد الخصم
            standing = round(num(row, "ذهب") + num(row, "فصوص") + num(row, "أحجار") + num(row, "الماس"), 2)
            bound = round(num(row, "ذهب") + num(row, "فصوص") + num(row, "أحجار بعد الخصم") + num(row, "الماس"), 2)

            for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس", "خياس", "خياس البوليش"):
                tot[k] = round(tot[k] + num(row, k), 2)
            tot["الصافي"] = round(tot["الصافي"] + net, 2)
            tot["القائم"] = round(tot["القائم"] + standing, 2)
            tot["المقيد"] = round(tot["المقيد"] + bound, 2)

            self.pending_sales_tree.insert("", "end", values=(
                row.get("row_number", "") or "-",
                row.get("set_number", "") or "-",
                f"{num(row, 'ذهب'):.2f}" if num(row, "ذهب") else "-",
                f"{num(row, 'فصوص'):.2f}" if num(row, "فصوص") else "-",
                f"{num(row, 'أحجار'):.2f}" if num(row, "أحجار") else "-",
                f"{num(row, 'أحجار بعد الخصم'):.2f}" if num(row, "أحجار بعد الخصم") else "-",
                f"{num(row, 'الماس'):.2f}" if num(row, "الماس") else "-",
                f"{num(row, 'خياس'):.2f}" if num(row, "خياس") else "-",
                f"{num(row, 'خياس البوليش'):.2f}" if num(row, "خياس البوليش") else "-",
                f"{net:.2f}",
                f"{standing:.2f}" if standing else "-",
                f"{bound:.2f}" if bound else "-",
            ))

        if self.pending_sale_rows:
            self.pending_sales_tree.insert("", "end", values=(
                "إجمالي الفاتورة", "-", f"{tot['ذهب']:.2f}", f"{tot['فصوص']:.2f}", f"{tot['أحجار']:.2f}",
                f"{tot['أحجار بعد الخصم']:.2f}", f"{tot['الماس']:.2f}", f"{tot['خياس']:.2f}",
                f"{tot['خياس البوليش']:.2f}", f"{tot['الصافي']:.2f}",
                f"{tot['القائم']:.2f}", f"{tot['المقيد']:.2f}"), tags=("total_tag",))''')

# زر الترحيل أعلى الجدول
rep('''        btn_edit_pending = ctk.CTkButton(pending_top, text="تعديل السطر المعلّق ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=170, height=32, command=self.edit_pending_sale_row)''',
    '''        ctk.CTkButton(pending_top, text="✅ ترحيل الفاتورة", font=("Cairo", 14, "bold"),
                      fg_color="#1e8449", hover_color="#145a32", width=160, height=32,
                      command=self.commit_sale_invoice).pack(side="left", padx=5)

        btn_edit_pending = ctk.CTkButton(pending_top, text="تعديل السطر المعلّق ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=170, height=32, command=self.edit_pending_sale_row)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الثاني من الدفعة الحادية عشرة على:", SRC)
