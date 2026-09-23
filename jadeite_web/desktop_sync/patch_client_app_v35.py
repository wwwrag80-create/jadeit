# -*- coding: utf-8 -*-
"""
الدفعة الخامسة والعشرون — نظام تصميم مركزي:

  بدل إعادة كتابة الشاشات الأربع عشرة واحدةً واحدةً (وهو ما يكسر نظاماً
  محاسبياً مستقراً)، بُني **نظام تصميم واحد** تمرّ عبره كل الجداول والخطوط
  والمسافات — فيتغيّر مظهر النظام كله دفعةً واحدة وبلا مساس بأي منطق محاسبي.

  ما يشمله:
    • مقاييس تتكيّف مع دقة شاشة المستخدم (خطوط، ارتفاع الصفوف، المسافات)
    • تنسيق موحّد لكل الجداول: رؤوس بارزة، صفوف متناوبة، تحديد واضح
    • ألوان متناسقة في المظهرين الفاتح والداكن
    • حدّ أدنى لحجم النافذة يمنع تشوّه الشاشات

الاستخدام:  python3 patch_client_app_v35.py rageh-1-34-14-cloud.py
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
#  ١) نظام التصميم
# ==========================================================================
rep('''    def create_standard_treeview(self, parent, columns, height=15):''',
    '''    # ══════════════════════════════════════════════════════════════════
    #  نظام التصميم المركزي
    #
    #  كل الجداول في النظام تُنشأ من create_standard_treeview، وكل الخطوط
    #  تُقاس من هنا — فتغيير هذه القيم يغيّر مظهر الشاشات الأربع عشرة معاً
    #  بلا لمس أي منطق محاسبي.
    # ══════════════════════════════════════════════════════════════════
    DESIGN = {
        "light": {
            "bg":          "#ffffff",
            "row_alt":     "#f4f7fb",
            "text":        "#1b2a3a",
            "head_bg":     "#1f4e79",
            "head_text":   "#ffffff",
            "sel_bg":      "#cfe4fb",
            "sel_text":    "#0d2a45",
            "grid":        "#d8e0ea",
        },
        "dark": {
            "bg":          "#1b2027",
            "row_alt":     "#222933",
            "text":        "#e8eef5",
            "head_bg":     "#16344f",
            "head_text":   "#ffffff",
            "sel_bg":      "#2c4a68",
            "sel_text":    "#ffffff",
            "grid":        "#2c343f",
        },
    }

    def design_metrics(self):
        """مقاييس تتناسب مع دقة شاشة المستخدم.

        الجداول والخطوط تكبر على الشاشات الكبيرة وتصغر على الصغيرة، فيبقى
        النظام مقروءاً ومتناسقاً على كل المقاسات بلا تدخّل من المستخدم.
        """
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        except Exception:
            sw, sh = 1366, 768

        if sw >= 2400:
            base, row_h, head = 15, 40, 15
        elif sw >= 1900:
            base, row_h, head = 14, 36, 14
        elif sw >= 1600:
            base, row_h, head = 13, 33, 13
        elif sw >= 1400:
            base, row_h, head = 12, 31, 12
        else:
            base, row_h, head = 11, 28, 11

        # الشاشات القصيرة تحتاج صفوفاً أقصر وإلا ظهر عدد قليل منها
        if sh <= 800:
            row_h = max(24, row_h - 4)

        return {"font": base, "row_h": row_h, "head": head,
                "pad_x": max(6, base - 4), "pad_y": max(3, base // 3)}

    def apply_design_system(self):
        """يطبّق التنسيق الموحّد على كل جداول النظام دفعةً واحدة"""
        try:
            m = self.design_metrics()
            mode = "dark" if ctk.get_appearance_mode() == "Dark" else "light"
            c = self.DESIGN[mode]
            self._design = dict(c, **m)

            style = ttk.Style()
            try:
                style.theme_use("clam")   # أكثر سمة تقبل التخصيص الكامل
            except Exception:
                pass

            style.configure(
                "Treeview",
                background=c["bg"], fieldbackground=c["bg"], foreground=c["text"],
                rowheight=m["row_h"], borderwidth=0, relief="flat",
                font=("Cairo", m["font"]))

            style.configure(
                "Treeview.Heading",
                background=c["head_bg"], foreground=c["head_text"],
                relief="flat", borderwidth=0, padding=(4, m["pad_y"] + 2),
                font=("Cairo", m["head"], "bold"))

            style.map("Treeview.Heading",
                      background=[("active", c["head_bg"])],
                      foreground=[("active", c["head_text"])])

            style.map("Treeview",
                      background=[("selected", c["sel_bg"])],
                      foreground=[("selected", c["sel_text"])])

            # شريط التمرير بنفس لغة الألوان
            style.configure("Vertical.TScrollbar", background=c["grid"],
                            troughcolor=c["bg"], borderwidth=0, arrowsize=14)
            style.configure("Horizontal.TScrollbar", background=c["grid"],
                            troughcolor=c["bg"], borderwidth=0, arrowsize=14)

            # شريط الإجمالي يتبع النظام أيضاً
            self._totals_style_ready = False
            self.ensure_totals_bar_style()
        except Exception as e:
            log_cloud_error("تعذّر تطبيق نظام التصميم", e)

    def style_tree_rows(self, tree):
        """صفوف متناوبة اللون: تسهّل تتبّع السطر الواحد عبر جدول عريض"""
        try:
            c = getattr(self, "_design", self.DESIGN["light"])
            tree.tag_configure("odd_row", background=c["bg"])
            tree.tag_configure("even_row", background=c["row_alt"])
            for i, iid in enumerate(tree.get_children()):
                tags = list(tree.item(iid, "tags") or ())
                # لا نلمس الصفوف ذات الوسوم الخاصة (الإجمالي، السالب…)
                if any(t in tags for t in ("total_tag", "red_tag", "orange_name")):
                    continue
                tags = [t for t in tags if t not in ("odd_row", "even_row")]
                tags.append("even_row" if i % 2 else "odd_row")
                tree.item(iid, tags=tuple(tags))
        except Exception:
            pass

    def create_standard_treeview(self, parent, columns, height=15):''')


# ==========================================================================
#  ٢) كل جدول يتبع النظام تلقائياً
# ==========================================================================
rep('''    def create_standard_treeview(self, parent, columns, height=15):
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=col)
        
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree''',
    '''    def create_standard_treeview(self, parent, columns, height=15):
        # كل جداول النظام تمرّ من هنا، فالتنسيق الموحّد يصلها جميعاً
        if not getattr(self, "_design", None):
            self.apply_design_system()

        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=self.wrap_header(col))
            tree.column(col, anchor="center")

        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        # الصفوف المتناوبة تُلوَّن بعد امتلاء الجدول
        tree.bind("<<TreeviewOpen>>", lambda e, t=tree: self.style_tree_rows(t), add="+")
        return tree''')


# ==========================================================================
#  ٣) التطبيق عند التشغيل وعند تبديل المظهر
# ==========================================================================
rep('''        self.create_layout()
        self.update_period_selector()''',
    '''        self.apply_design_system()
        try:
            # حدّ أدنى يمنع تشوّه الجداول لو صغّر المستخدم النافذة
            self.minsize(1100, 620)
        except Exception:
            pass

        self.create_layout()
        self.update_period_selector()''')

rep('''    def toggle_theme(self):''',
    '''    def toggle_theme(self):
        # التنسيق الموحّد يُعاد تطبيقه بعد التبديل ليتبع المظهر الجديد
        self.after(60, self.apply_design_system)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق نظام التصميم المركزي على:", SRC)
