# -*- coding: utf-8 -*-
"""
الدفعة السادسة عشرة — الجزء الثاني:
  شاشة رئيسية مستقلة: (ربح/خسارة الطقم)

  أعمدة الجدول:
    التاريخ | عدد الأطقم | خياس التلميع النهائي | خياس البوليش | خياس المركب
    | إجمالي الخياس | المسترجع | الربح | خسارة

  المسترجع: لكل نوع خياس نسبة استرجاع يحدّدها المستخدم (الضغط على رأس عمود
  المسترجع يفتح نافذة ضبط النسب الثلاث). المسترجع = مجموع (خياس × نسبته).
  الربح = إجمالي الخياس − المسترجع.

  الأطقم الخاسرة تخرج من عمود الربح وتظهر في عمود (خسارة) بقيمتها المطلقة.
  الشاشة كلها **عرض فقط** ولا تؤثر على الخزينة إطلاقاً.

الاستخدام:  python3 patch_client_app_v25.py rageh-1-34-14-cloud.py
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
#  ١) نسب الاسترجاع + حساب صفوف الأطقم
# ==========================================================================
rep('''    PROFIT_SECTION = "ربح/خسارة الطقم"''',
    '''    PROFIT_SECTION = "ربح/خسارة الطقم"

    # مفاتيح أنواع الخياس الثلاثة ونِسَب استرجاعها الافتراضية
    RECOVERY_KEYS = (("تلميع", "خياس التلميع النهائي"),
                     ("بوليش", "خياس البوليش"),
                     ("مركب", "خياس المركب"))
    RECOVERY_DEFAULT = 0.0   # الافتراضي صفر: لا استرجاع حتى يحدّده المستخدم بنفسه

    def get_recovery_pct(self, key):
        """نسبة استرجاع نوع خياس معيّن (٪) — محفوظة وتبقى بعد إغلاق البرنامج"""
        try:
            return float(self.get_setting(f"recovery_pct_{key}", "") or self.RECOVERY_DEFAULT)
        except (TypeError, ValueError):
            return self.RECOVERY_DEFAULT

    def set_recovery_pct(self, key, value):
        try:
            pct = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return
        self.set_setting(f"recovery_pct_{key}", str(pct))

    def open_recovery_settings(self):
        """نافذة ضبط نسب الاسترجاع الثلاث (تُفتح بالضغط على رأس عمود المسترجع)"""
        win = ctk.CTkToplevel(self)
        win.title("نسب استرجاع الخياس")
        win.geometry("430x360")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="⚙️ نسب استرجاع الخياس", font=("Cairo", 18, "bold"),
                     text_color="#d4af37").pack(pady=(16, 4))
        ctk.CTkLabel(win, text="لكل نوع خياس نسبة تُسترجع منه — والباقي هو الربح",
                     font=("Cairo", 11), text_color="#8b8f95").pack(pady=(0, 12))

        entries = {}
        for key, label in self.RECOVERY_KEYS:
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=28, pady=6)
            ctk.CTkLabel(row, text=label, font=("Cairo", 13, "bold"),
                         width=170, anchor="e").pack(side="right")
            ent = ctk.CTkEntry(row, justify="center", font=("Cairo", 14), width=90, height=34)
            ent.insert(0, f"{self.get_recovery_pct(key):g}")
            ent.pack(side="right", padx=8)
            ctk.CTkLabel(row, text="%", font=("Cairo", 13, "bold")).pack(side="right")
            entries[key] = ent

        def save_and_close():
            for key, _ in self.RECOVERY_KEYS:
                self.set_recovery_pct(key, entries[key].get().strip() or 0)
            win.destroy()
            self.refresh_sets_profit_tab()

        ctk.CTkButton(win, text="💾 حفظ وتطبيق", font=("Cairo", 15, "bold"), fg_color="#1e8449",
                      hover_color="#145a32", width=190, height=42, command=save_and_close).pack(pady=(18, 6))
        ctk.CTkButton(win, text="إلغاء", font=("Cairo", 13), fg_color="#555555",
                      hover_color="#333333", width=120, height=34, command=win.destroy).pack()

    def get_sets_profit_rows(self, month):
        """تفصيل كل طقم في شهر: خياساته الثلاثة، إجماليها، مسترجعها، وربحه/خسارته.

        الربح = إجمالي الخياس − المسترجع. الطقم ذو الربح السالب يُعدّ خسارة
        ويخرج كلياً من عمود الربح، فلا يُقاصّ ربح طقم خسارة طقم آخر.
        """
        breakdown = self.get_set_khayas_breakdown(month)
        pct = {k: self.get_recovery_pct(k) / 100.0 for k, _ in self.RECOVERY_KEYS}

        rows = []
        for set_no in sorted(breakdown):
            k = breakdown[set_no]
            total = round(k["تلميع"] + k["بوليش"] + k["مركب"], 2)
            recovered = round(k["تلميع"] * pct["تلميع"]
                              + k["بوليش"] * pct["بوليش"]
                              + k["مركب"] * pct["مركب"], 2)
            net = round(total - recovered, 2)
            rows.append({
                "رقم التشغيل": set_no,
                "تلميع": k["تلميع"], "بوليش": k["بوليش"], "مركب": k["مركب"],
                "إجمالي": total, "المسترجع": recovered,
                "الربح": net if net >= 0 else 0.0,
                "خسارة": round(abs(net), 2) if net < 0 else 0.0,
            })
        return rows

    def get_sets_profit_totals(self, month):
        rows = self.get_sets_profit_rows(month)
        agg = {k: 0.0 for k in ("تلميع", "بوليش", "مركب", "إجمالي", "المسترجع", "الربح", "خسارة")}
        for r in rows:
            for k in agg:
                agg[k] = round(agg[k] + r[k], 2)
        agg["عدد"] = len(rows)
        return agg''')


# ==========================================================================
#  ٢) الشاشة المستقلة
# ==========================================================================
rep('''    def get_all_stage_categories(self):''',
    '''    def build_sets_profit_tab(self):
        """شاشة (ربح/خسارة الطقم) المستقلة — عرض فقط، بلا أي أثر على الخزينة"""
        tab = self.tabview.tab("ربح/خسارة الطقم")

        head = ctk.CTkFrame(tab, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(head, text="📈 ربح/خسارة الطقم", font=("Cairo", 20, "bold"),
                     text_color="#d4af37").pack(side="right", padx=8)
        ctk.CTkLabel(head, text="(عرض فقط — لا يؤثر على الخزينة)",
                     font=("Cairo", 11), text_color="#8b8f95").pack(side="right", padx=6)

        ctk.CTkButton(head, text="⚙️ نسب الاسترجاع", font=("Cairo", 13, "bold"),
                      fg_color="#b8860b", hover_color="#daa520", width=150, height=34,
                      command=self.open_recovery_settings).pack(side="left", padx=5)
        ctk.CTkButton(head, text="👁️ عرض كامل", font=("Cairo", 13, "bold"),
                      fg_color="#1f77b4", hover_color="#144d75", width=130, height=34,
                      command=lambda: self.view_treeview_fullscreen(
                          getattr(self, "sets_profit_tree", None), "ربح/خسارة الطقم")).pack(side="left", padx=5)
        ctk.CTkButton(head, text="🔄 تحديث", font=("Cairo", 13, "bold"),
                      fg_color="#555555", hover_color="#333333", width=110, height=34,
                      command=self.refresh_sets_profit_tab).pack(side="left", padx=5)

        self.lbl_sets_profit_hint = ctk.CTkLabel(
            tab, text="اضغط على رأس عمود (المسترجع) لضبط النسب  •  اضغط على أي صف لعرض تفاصيل أطقمه",
            font=("Cairo", 11), text_color="#8b8f95")
        self.lbl_sets_profit_hint.pack(pady=(0, 6))

        self.sets_profit_table_frame = ttk.Frame(tab)
        self.sets_profit_table_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.sets_profit_tree = None

        self.lbl_sets_profit_summary = ctk.CTkLabel(
            tab, text="", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"),
            text_color="#2ecc71")
        self.lbl_sets_profit_summary.pack(pady=(0, 10))

        self.refresh_sets_profit_tab()

    SETS_PROFIT_COLS = ("التاريخ", "عدد الأطقم", "خياس التلميع النهائي", "خياس البوليش",
                        "خياس المركب", "إجمالي الخياس", "المسترجع", "الربح", "خسارة")

    def refresh_sets_profit_tab(self):
        if not getattr(self, "sets_profit_table_frame", None):
            return
        for w in self.sets_profit_table_frame.winfo_children():
            w.destroy()

        cols = self.SETS_PROFIT_COLS
        self.sets_profit_tree = self.create_standard_treeview(self.sets_profit_table_frame, cols, height=16)
        self.sets_profit_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        self.sets_profit_tree.bind("<Double-1>", self._on_sets_profit_row_click)

        # الضغط على رأس عمود المسترجع يفتح ضبط النسب
        def on_head(event):
            if self.sets_profit_tree.identify_region(event.x, event.y) != "heading":
                return
            try:
                idx = int(self.sets_profit_tree.identify_column(event.x).replace("#", "")) - 1
                if 0 <= idx < len(cols) and cols[idx] == "المسترجع":
                    self.open_recovery_settings()
            except (ValueError, IndexError):
                pass

        self.sets_profit_tree.bind("<Button-1>", on_head, add="+")

        months = sorted({str(inv.get("التاريخ", ""))[:7] for inv in self.invoices.values()
                         if inv.get("النوع") == "خياس طقوم" and inv.get("التاريخ")})

        self.sets_profit_month_map = {}
        grand = {k: 0.0 for k in ("تلميع", "بوليش", "مركب", "إجمالي", "المسترجع", "الربح", "خسارة")}
        grand_count = 0

        for m in months:
            t = self.get_sets_profit_totals(m)
            if t["عدد"] == 0:
                continue
            grand_count += t["عدد"]
            for k in grand:
                grand[k] = round(grand[k] + t[k], 2)

            row_id = self.sets_profit_tree.insert("", "end", values=(
                m, str(t["عدد"]),
                f"{t['تلميع']:.2f}" if t["تلميع"] else "-",
                f"{t['بوليش']:.2f}" if t["بوليش"] else "-",
                f"{t['مركب']:.2f}" if t["مركب"] else "-",
                f"{t['إجمالي']:.2f}" if t["إجمالي"] else "-",
                f"{t['المسترجع']:.2f}" if t["المسترجع"] else "-",
                f"{t['الربح']:.2f}" if t["الربح"] else "-",
                f"{t['خسارة']:.2f}" if t["خسارة"] else "-",
            ))
            self.sets_profit_month_map[row_id] = m

        if grand_count:
            self.sets_profit_tree.insert("", "end", values=(
                "الإجمالي", str(grand_count),
                f"{grand['تلميع']:.2f}", f"{grand['بوليش']:.2f}", f"{grand['مركب']:.2f}",
                f"{grand['إجمالي']:.2f}", f"{grand['المسترجع']:.2f}",
                f"{grand['الربح']:.2f}", f"{grand['خسارة']:.2f}"), tags=("total_tag",))

        self.apply_column_labels(self.sets_profit_tree, "sets_profit")
        self.fit_columns_to_content(self.sets_profit_tree, "sets_profit", min_width=54, max_width=170)
        self.enable_column_rename(self.sets_profit_tree, "sets_profit",
                                  on_renamed=self.refresh_sets_profit_tab)

        pcts = "  |  ".join(f"{label}: {self.get_recovery_pct(k):g}%"
                            for k, label in self.RECOVERY_KEYS)
        self.lbl_sets_profit_summary.configure(
            text=(f"الأطقم: {grand_count}  |  إجمالي الخياس: {en(grand['إجمالي'])}  |  "
                  f"المسترجع: {en(grand['المسترجع'])}  |  الربح: {en(grand['الربح'])}  |  "
                  f"خسارة: {en(grand['خسارة'])} جم\\n{pcts}"))

    def _on_sets_profit_row_click(self, event=None):
        """يفتح كشف أطقم الشهر المحدد بنفس أعمدة الجدول"""
        sel = self.sets_profit_tree.selection() if self.sets_profit_tree else []
        if not sel:
            return
        month = getattr(self, "sets_profit_month_map", {}).get(sel[0])
        if not month:
            return
        self.show_sets_profit_detail(month)

    def show_sets_profit_detail(self, month, losses_only=False):
        """كشف تفصيلي لكل طقم بنفس أعمدة الجدول الرئيسي"""
        rows = self.get_sets_profit_rows(month)
        if losses_only:
            rows = [r for r in rows if r["خسارة"] > 0]
            title = f"أطقم الخسارة — {month}"
        else:
            title = f"تفاصيل أطقم — {month}"

        if not rows:
            messagebox.showinfo("لا يوجد", f"لا توجد أطقم لعرضها في {title}.")
            return

        cols = ("رقم التشغيل", "خياس التلميع النهائي", "خياس البوليش", "خياس المركب",
                "إجمالي الخياس", "المسترجع", "الربح", "خسارة")
        data, agg = [], {k: 0.0 for k in ("تلميع", "بوليش", "مركب", "إجمالي", "المسترجع", "الربح", "خسارة")}
        for r in rows:
            for k in agg:
                agg[k] = round(agg[k] + r[k], 2)
            data.append((
                r["رقم التشغيل"],
                f"{r['تلميع']:.2f}" if r["تلميع"] else "-",
                f"{r['بوليش']:.2f}" if r["بوليش"] else "-",
                f"{r['مركب']:.2f}" if r["مركب"] else "-",
                f"{r['إجمالي']:.2f}" if r["إجمالي"] else "-",
                f"{r['المسترجع']:.2f}" if r["المسترجع"] else "-",
                f"{r['الربح']:.2f}" if r["الربح"] else "-",
                f"{r['خسارة']:.2f}" if r["خسارة"] else "-",
            ))

        totals = ("الإجمالي", f"{agg['تلميع']:.2f}", f"{agg['بوليش']:.2f}", f"{agg['مركب']:.2f}",
                  f"{agg['إجمالي']:.2f}", f"{agg['المسترجع']:.2f}",
                  f"{agg['الربح']:.2f}", f"{agg['خسارة']:.2f}")
        self.open_fullscreen_table_view(title, cols, data, totals_values=totals)

    def get_all_stage_categories(self):''')


# ==========================================================================
#  ٣) تسجيل الشاشة في القائمة الرئيسية + إزالتها من صناديق الخياس
# ==========================================================================
rep('''        self.tabview.add("شاشة الخسائر")''',
    '''        self.tabview.add("شاشة الخسائر")
        self.tabview.add("ربح/خسارة الطقم")''')

rep('''        self.build_chart_of_accounts_tab()''',
    '''        self.build_chart_of_accounts_tab()
        self.build_sets_profit_tab()''')

rep('''                "القيود اليومية", "شاشة الخسائر"]''',
    '''                "القيود اليومية", "شاشة الخسائر", "ربح/خسارة الطقم"]''')

# إزالتها من أزرار صناديق الخياس
rep('''            ("ربح/خسارة الطقم", "📈 ربح/خسارة الطقم"),
''', '''''')

rep('''        if self.current_view_cat == self.PROFIT_SECTION:
            self.render_sets_profit_inquiry()
            return

''', '''''')

# تحديثها مع كل إعادة حساب
rep('''        if hasattr(self, 'sales_ops_table_frame'):
            self.refresh_sales_ops_table()''',
    '''        if hasattr(self, 'sales_ops_table_frame'):
            self.refresh_sales_ops_table()
        if getattr(self, 'sets_profit_table_frame', None):
            self.refresh_sets_profit_tab()''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الثاني من الدفعة السادسة عشرة على:", SRC)
