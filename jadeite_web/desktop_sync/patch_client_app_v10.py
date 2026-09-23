# -*- coding: utf-8 -*-
"""
الدفعة العاشرة — الجزء الأول (شاشة صناديق الخياس):
  ١) عارض جدول ملء الشاشة مع صف إجمالي ثابت أثناء التمرير (لكل الأقسام)
  ٢) زر «👁️ عرض» في جدول القسم الشهري + تطبيق الثبات على تفاصيل الشهر
  ٣) الكاستنج: عمودا (عدد الأشجار) و(خياس كل شجرة) في الجدول الشهري
  ٤) كشف حركة العامل (من صناديق الخياس): تعديل «رقم التشغيل» مباشرة من الجدول

الاستخدام:  python3 patch_client_app_v10.py rageh-1-34-14-cloud.py
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
#  ١) العارض العام: جدول ملء الشاشة بصف إجمالي ثابت
# ==========================================================================
rep('''    def create_standard_treeview(self, parent, columns, height=15):''',
    '''    def create_sticky_total_tree(self, parent, columns, height=18, col_widths=None):
        """جدول بصف إجمالي ثابت أسفله لا يتحرّك مع التمرير.

        Treeview لا يدعم "تجميد صف" أصلياً، فالحل القياسي هو استخدام شجرتين:
        الأولى قابلة للتمرير لصفوف البيانات، والثانية أسفلها مباشرة (خارج
        منطقة التمرير) لصف الإجمالي فقط، بنفس الأعمدة والعرض بالضبط حتى
        تصطف الأرقام رأسياً مع الجدول العلوي.

        يرجع: (شجرة البيانات القابلة للتمرير، شجرة الإجمالي الثابتة)
        """
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="both", expand=True)

        body_frame = ttk.Frame(wrapper)
        body_frame.pack(side="top", fill="both", expand=True)

        data_tree = ttk.Treeview(body_frame, columns=columns, show="headings", height=height)
        for col in columns:
            data_tree.heading(col, text=col)
            data_tree.column(col, width=(col_widths or {}).get(col, 110), anchor="center")

        vsb = ttk.Scrollbar(body_frame, orient="vertical", command=data_tree.yview)
        data_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        data_tree.pack(side="left", fill="both", expand=True)

        # فاصل بصري خفيف يوضّح أن الصف التالي مثبّت وليس جزءاً من التمرير
        ttk.Separator(wrapper, orient="horizontal").pack(side="top", fill="x")

        # شجرة الإجمالي: صف واحد فقط، بلا شريط تمرير، وبعرض أعمدة مطابق تماماً
        # (عرض شريط التمرير الرأسي 17px تقريباً يُعوَّض بهامش مساوٍ من اليمين
        # حتى تصطف أعمدة الشجرتين رأسياً رغم غياب الشريط في الشجرة السفلى)
        total_holder = ttk.Frame(wrapper)
        total_holder.pack(side="top", fill="x")
        spacer = ttk.Frame(total_holder, width=17)
        spacer.pack(side="right", fill="y")

        total_tree = ttk.Treeview(total_holder, columns=columns, show="headings", height=1)
        for col in columns:
            total_tree.heading(col, text="")
            total_tree.column(col, width=(col_widths or {}).get(col, 110), anchor="center")
        total_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        total_tree.pack(side="left", fill="x", expand=True)

        return data_tree, total_tree

    def open_fullscreen_table_view(self, title, columns, rows, totals_values=None,
                                   col_widths=None, row_tags=None):
        """يفتح نافذة ملء الشاشة لعرض جدول كامل، مع صف الإجمالي ثابتاً أسفلها
        أثناء تمرير صفوف البيانات — يُستخدم لكل جداول الأقسام في مراحل التصنيع
        وصناديق الخياس دون تكرار الكود في كل شاشة.

        rows: قائمة صفوف، كل صف Tuple بنفس عدد الأعمدة
        totals_values: صف الإجمالي (Tuple)، أو None لإخفائه
        row_tags: قائمة موازية لـ rows فيها وسم اللون لكل صف (أو None لكل صف)
        """
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.transient(self)
        win.grab_set()
        win.focus_force()
        try:
            win.state("zoomed")   # ملء الشاشة على ويندوز
        except Exception:
            win.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}")

        ctk.CTkLabel(win, text=title, font=("Cairo", 20, "bold"),
                     text_color="#d4af37").pack(pady=(16, 4))
        ctk.CTkLabel(win, text=f"عدد الصفوف: {len(rows)}", font=("Cairo", 12),
                     text_color="#8b8f95").pack(pady=(0, 10))

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 6))

        data_tree, total_tree = self.create_sticky_total_tree(body, columns, height=24, col_widths=col_widths)

        for i, row in enumerate(rows):
            tag = (row_tags[i],) if row_tags and row_tags[i] else ()
            data_tree.insert("", "end", values=row, tags=tag)

        if totals_values is not None:
            total_tree.insert("", "end", values=totals_values, tags=("total_tag",))

        ctk.CTkButton(win, text="إغلاق", font=("Cairo", 14, "bold"), width=140, height=40,
                      command=win.destroy).pack(pady=14)

    def create_standard_treeview(self, parent, columns, height=15):''')


# ==========================================================================
#  ٢) زر «عرض» في جدول القسم الشهري بصناديق الخياس + الكاستنج: عمودا الأشجار
# ==========================================================================
rep('''    def render_stage_monthly_inquiry(self):
        """جدول عرض أرصدة صناديق الكاستنج/التلميع/التلميع-البف: شهر وسنة + مدين + دائن + رصيد تراكمي"""
        cat = self.current_view_cat
        madin_type, qabd_type, mustarja_name = self.get_stage_config(cat)
        in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]

        tree_container = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        tree_container.pack(side="top", fill="both", expand=True)

        columns = ("الشهر والسنة", "مدين", "دائن", "الرصيد")
        self.tree = self.create_standard_treeview(tree_container, columns, height=18)
        for col in columns:
            self.tree.column(col, width=170, anchor="center")
        if cat == "خياس الطقوم":
            # هذا الصندوق يُغذّى من خانة الخياس بشاشة المبيعات، فتوضيح المسميات أدق للمستخدم
            self.tree.heading("مدين", text="الخياس")
            self.tree.heading("دائن", text="المسترجع/القبض")
            self.tree.heading("الرصيد", text="الرصيد التراكمي")

        self.tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self.open_stage_month_detail)

        months = set()
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            t = inv.get("النوع")
            dt = inv.get("التاريخ", "")
            if not dt: continue
            if t == madin_type or (qabd_type and t == qabd_type) or (t in in_types and inv.get("الاسم") == mustarja_name):
                months.add(dt[:7])

        self.stage_month_rows_map = {}
        running = 0.0
        for m in sorted(months):
            tot_madin, tot_daen = self.get_stage_totals_for_month(cat, m)
            running += (tot_daen - tot_madin)
            row_id = self.tree.insert("", "end", values=(m, f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{running:.2f}"))
            self.stage_month_rows_map[row_id] = m

        if months:
            self.tree.insert("", "end", values=("الرصيد التراكمي الحالي", "-", "-", f"{running:.2f}"), tags=("total_tag",))

        cur_madin, cur_daen = self.get_stage_totals_for_month(cat, self.current_display_month)
        if hasattr(self, 'lbl_dash_alert'):
            self.lbl_dash_alert.configure(text=f"الذهب عند {self.get_display_label(cat)}: {round(cur_madin - cur_daen, 2):.2f} جم")
        self.last_computed_actual_khayas = 0.0  # الإقفال الجماعي غير مطبق على هذا القسم
        self.lbl_section_summary.configure(text=f"({cat}) لشهر ({self.current_display_month}): مدين {cur_madin:.2f} | دائن {cur_daen:.2f} | الرصيد التراكمي {running:.2f} جم")''',
    '''    def get_stage_monthly_tree_totals(self, cat, month):
        """عدد الأشجار الكلي وخياس كل شجرة لصندوق الكاستنج خلال شهر معيّن.

        نُعيد استخدام نفس منطق تجميع الصفوف المستخدم في مراحل التصنيع
        (collect_stage_ops_rows) حتى يبقى الرقمان متطابقين بين الشاشتين دائماً،
        بدل حساب منفصل قد ينحرف عنه.
        """
        madin_type, qabd_type, _ = self.get_stage_config(cat)
        saved_month = self.current_display_month
        self.current_display_month = month
        try:
            rows = self.collect_stage_ops_rows(madin_type, qabd_type)
        finally:
            self.current_display_month = saved_month

        total_trees = sum(g.get("أشجار", 0.0) for _, _, g in rows)
        total_khayas = sum(round(g["مدين"] - g["دائن"], 2) for _, _, g in rows)
        per_tree = round(total_khayas / total_trees, 2) if total_trees > 0 else 0.0
        return round(total_trees, 2), per_tree

    def render_stage_monthly_inquiry(self):
        """جدول عرض أرصدة صناديق الكاستنج/التلميع/التلميع-البف: شهر وسنة + مدين + دائن + رصيد تراكمي"""
        cat = self.current_view_cat
        madin_type, qabd_type, mustarja_name = self.get_stage_config(cat)
        in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
        show_trees = (cat == "الكاستنج")

        header_row = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        header_row.pack(side="top", fill="x", padx=4, pady=(0, 4))
        ctk.CTkButton(header_row, text="👁️ عرض الجدول كاملاً", font=("Cairo", 13, "bold"),
                      fg_color="#1f77b4", hover_color="#144d75", width=170, height=32,
                      command=lambda: self.view_stage_monthly_fullscreen(cat)
                      ).pack(side="left", padx=4)

        tree_container = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        tree_container.pack(side="top", fill="both", expand=True)

        columns = ("الشهر والسنة", "مدين", "دائن", "الرصيد")
        if show_trees:
            columns = columns + ("عدد الأشجار", "خياس كل شجرة")
        self.tree = self.create_standard_treeview(tree_container, columns, height=18)
        for col in columns:
            self.tree.column(col, width=170 if col in ("الشهر والسنة", "مدين", "دائن", "الرصيد") else 130,
                             anchor="center")
        if cat == "خياس الطقوم":
            # هذا الصندوق يُغذّى من خانة الخياس بشاشة المبيعات، فتوضيح المسميات أدق للمستخدم
            self.tree.heading("مدين", text="الخياس")
            self.tree.heading("دائن", text="المسترجع/القبض")
            self.tree.heading("الرصيد", text="الرصيد التراكمي")

        self.tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self.open_stage_month_detail)

        months = set()
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            t = inv.get("النوع")
            dt = inv.get("التاريخ", "")
            if not dt: continue
            if t == madin_type or (qabd_type and t == qabd_type) or (t in in_types and inv.get("الاسم") == mustarja_name):
                months.add(dt[:7])

        self.stage_month_rows_map = {}
        self._stage_monthly_rows_cache = []
        running = 0.0
        grand_trees = 0.0
        for m in sorted(months):
            tot_madin, tot_daen = self.get_stage_totals_for_month(cat, m)
            running += (tot_daen - tot_madin)
            vals = [m, f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{running:.2f}"]
            if show_trees:
                m_trees, m_per_tree = self.get_stage_monthly_tree_totals(cat, m)
                grand_trees += m_trees
                vals += [f"{m_trees:g}" if m_trees else "-", f"{m_per_tree:.2f}" if m_trees else "-"]
            row_id = self.tree.insert("", "end", values=tuple(vals))
            self.stage_month_rows_map[row_id] = m
            self._stage_monthly_rows_cache.append(tuple(vals))

        if months:
            total_vals = ["الرصيد التراكمي الحالي", "-", "-", f"{running:.2f}"]
            if show_trees:
                overall_per_tree = round(running / grand_trees, 2) if grand_trees else 0.0
                total_vals += [f"{grand_trees:g}" if grand_trees else "-",
                               f"{overall_per_tree:.2f}" if grand_trees else "-"]
            self.tree.insert("", "end", values=tuple(total_vals), tags=("total_tag",))
            self._stage_monthly_totals_cache = tuple(total_vals)
        else:
            self._stage_monthly_totals_cache = None
        self._stage_monthly_columns_cache = columns

        cur_madin, cur_daen = self.get_stage_totals_for_month(cat, self.current_display_month)
        if hasattr(self, 'lbl_dash_alert'):
            self.lbl_dash_alert.configure(text=f"الذهب عند {self.get_display_label(cat)}: {round(cur_madin - cur_daen, 2):.2f} جم")
        self.last_computed_actual_khayas = 0.0  # الإقفال الجماعي غير مطبق على هذا القسم
        self.lbl_section_summary.configure(text=f"({cat}) لشهر ({self.current_display_month}): مدين {cur_madin:.2f} | دائن {cur_daen:.2f} | الرصيد التراكمي {running:.2f} جم")

    def view_stage_monthly_fullscreen(self, cat):
        """يعرض جدول القسم الشهري كاملاً بشاشة ملء الشاشة وصف إجمالي ثابت"""
        rows = getattr(self, "_stage_monthly_rows_cache", [])
        cols = getattr(self, "_stage_monthly_columns_cache", ("الشهر والسنة", "مدين", "دائن", "الرصيد"))
        totals = getattr(self, "_stage_monthly_totals_cache", None)
        self.open_fullscreen_table_view(
            f"عرض كامل — {self.get_display_label(cat)}", cols, rows, totals_values=totals)''')


# ==========================================================================
#  ٣) تفاصيل الشهر: صف الإجمالي ثابت (نفس نافذة الحركات الحالية)
# ==========================================================================
rep('''        win = ctk.CTkToplevel(self)
        win.title(f"تفاصيل {self.get_display_label(cat)} - {month}")
        win.geometry("650x480")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"تفاصيل حركة ({self.get_display_label(cat)}) لشهر ({month})", font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=15)

        cols = ("التاريخ", "رقم التشغيل", "الاسم", "مدين", "دائن", "الرصيد")
        tree = self.create_standard_treeview(win, cols, height=14)
        tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 13, "bold"))
        for c in cols:
            w = 170 if c == "الاسم" else 140 if c == "التاريخ" else 110
            tree.column(c, width=w, anchor="center")
        if cat == "خياس الطقوم":
            tree.heading("مدين", text="الخياس")
            tree.heading("دائن", text="المسترجع/القبض")

        tot_madin = tot_daen = 0.0
        for dt, name, madin_v, daen_v, _, set_no in recs:
            running += (daen_v - madin_v)
            tot_madin = round(tot_madin + madin_v, 2)
            tot_daen = round(tot_daen + daen_v, 2)
            tree.insert("", "end", values=(
                dt, set_no, name,
                f"{madin_v:.2f}" if madin_v else "-",
                f"{daen_v:.2f}" if daen_v else "-",
                f"{running:.2f}"
            ))

        if recs:
            tree.insert("", "end", values=("إجمالي الشهر", "-", "-", f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{running:.2f}"), tags=("total_tag",))
        else:
            ctk.CTkLabel(win, text="لا توجد عمليات مسجّلة لهذا الشهر", font=("Cairo", 15, "bold"), text_color="#e74c3c").pack(pady=10)''',
    '''        win = ctk.CTkToplevel(self)
        win.title(f"تفاصيل {self.get_display_label(cat)} - {month}")
        win.geometry("700x520")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"تفاصيل حركة ({self.get_display_label(cat)}) لشهر ({month})", font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=15)

        cols = ("التاريخ", "رقم التشغيل", "الاسم", "مدين", "دائن", "الرصيد")
        col_widths = {"الاسم": 170, "التاريخ": 140}
        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 6))
        tree, total_tree = self.create_sticky_total_tree(body, cols, height=13, col_widths=col_widths)
        if cat == "خياس الطقوم":
            tree.heading("مدين", text="الخياس")
            tree.heading("دائن", text="المسترجع/القبض")

        tot_madin = tot_daen = 0.0
        for dt, name, madin_v, daen_v, _, set_no in recs:
            running += (daen_v - madin_v)
            tot_madin = round(tot_madin + madin_v, 2)
            tot_daen = round(tot_daen + daen_v, 2)
            tree.insert("", "end", values=(
                dt, set_no, name,
                f"{madin_v:.2f}" if madin_v else "-",
                f"{daen_v:.2f}" if daen_v else "-",
                f"{running:.2f}"
            ))

        if recs:
            total_tree.insert("", "end", values=("إجمالي الشهر", "-", "-", f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{running:.2f}"), tags=("total_tag",))
        else:
            ctk.CTkLabel(win, text="لا توجد عمليات مسجّلة لهذا الشهر", font=("Cairo", 15, "bold"), text_color="#e74c3c").pack(pady=10)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الأول من الدفعة العاشرة على:", SRC)
