# -*- coding: utf-8 -*-
"""
الدفعة الثامنة عشرة:
  ١) خياس المركب: يبحث في المصنعين **والمركبين** معاً بمعادلة مسموح/٨ الصحيحة
     لكل قسم، وفي كل الفترات — فيلتقط بيانات العميل القديمة والجديدة معاً
  ٢) تعديل الحركة: إضافة (رقم الصف) و(رقم التشغيل) و(التاريخ) للنافذة
  ٣) شريط الإجمالي داخل الشاشة: خلفية رصاصية غامقة وأرقام بيضاء
  ٤) شريط الإجمالي في العرض الكامل: بارز وواضح خارج الجدول

الاستخدام:  python3 patch_client_app_v28.py rageh-1-34-14-cloud.py
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
#  ١) خياس المركب من مسموح/٨ في المصنعين والمركبين معاً
# ==========================================================================
old_fn_start = src.index("    def get_assembler_khayas_for_set(self, set_number, month=None):")
old_fn_end = src.index("\n    def autofill_assembler_khayas", old_fn_start)

new_fn = '''    def get_assembler_khayas_for_set(self, set_number, month=None):
        """قيمة عمود (مسموح/٨) لرقم تشغيل معيّن، من شاشة مراحل التصنيع.

        يبحث في قسمَي (المركبين) و(المصنعين) معاً، لأن رقم التشغيل الواحد قد
        يكون مسجّلاً في أيّهما حسب طبيعة العمل وحسب ما اعتاده العميل في نسخته
        القديمة — فالبحث في قسم واحد كان يُرجع صفراً لأرقام مسجّلة في الآخر.

        معادلة (مسموح/٨) تختلف بين القسمين، فتُحسب لكل قسم بمعادلته الصحيحة
        تماماً كما تظهر في كشف مراحل التصنيع:
            • المركبين: القبض × ٨ بالألف
            • المصنعين: المفنش ٨ بالالف × ٨ بالألف

        البحث يشمل **كل الفترات** لا الشهر المعروض فقط: رقم التشغيل فريد عبر
        الزمن، والتصنيع/التركيب يسبق البيع غالباً بشهر أو أكثر.
        (تمرير month صراحةً يقيّد البحث بذلك الشهر عند الحاجة)
        """
        set_number = (set_number or "").strip()
        if not set_number:
            return 0.0

        # (اسم القسم، نوع الحركة التي يُحسب عليها المسموح)
        sections = (("المركبين", "قبض ذهب"),
                    ("المصنعين", "المفنش ٨ بالالف"))

        members = {}
        for cat, base_type in sections:
            for name in self.categories.get(cat, []):
                members[name] = base_type

        if not members:
            return 0.0

        totals = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"):
                continue
            name = inv.get("الاسم")
            base_type = members.get(name)
            if base_type is None:
                continue
            if (inv.get("set_number", "") or "").strip() != set_number:
                continue
            if month and not str(inv.get("التاريخ", "")).startswith(month):
                continue
            if inv.get("النوع") != base_type:
                continue
            totals[name] = totals.get(name, 0.0) + inv.get("الوزن", 0.0)

        return round(sum(v * ALLOWANCE_8 for v in totals.values()), 2)
'''

src = src[:old_fn_start] + new_fn + src[old_fn_end:]


# ==========================================================================
#  ٢) نافذة تعديل الحركة: رقم الصف ورقم التشغيل والتاريخ
# ==========================================================================
rep('''        ctk.CTkLabel(win, text="البيان:", font=("Cairo", 15, "bold")).pack(pady=(8, 0))
        ent_note = ctk.CTkEntry(win, justify="right", width=380)
        ent_note.insert(0, common_note)
        ent_note.pack(pady=5)''',
    '''        # حقول تعريف الحركة: قابلة للتعديل لتصحيح أي خطأ في الترقيم أو التاريخ
        ref_set = (base_inv.get("set_number", "") or "") if base_inv else ""

        ctk.CTkLabel(frm, text="رقم الصف:", font=("Cairo", 15, "bold")).grid(row=3, column=1, padx=10, pady=8)
        ent_row_no = ctk.CTkEntry(frm, justify="center", width=130)
        ent_row_no.insert(0, ref_row)
        ent_row_no.grid(row=3, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="رقم التشغيل:", font=("Cairo", 15, "bold")).grid(row=4, column=1, padx=10, pady=8)
        ent_set_no = ctk.CTkEntry(frm, justify="center", width=130)
        ent_set_no.insert(0, ref_set)
        ent_set_no.grid(row=4, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="التاريخ:", font=("Cairo", 15, "bold")).grid(row=5, column=1, padx=10, pady=8)
        ent_date = ctk.CTkEntry(frm, justify="center", width=130)
        ent_date.insert(0, str(ref_dt)[:10])
        ent_date.grid(row=5, column=0, padx=10, pady=8)

        ctk.CTkLabel(win, text="البيان:", font=("Cairo", 15, "bold")).pack(pady=(8, 0))
        ent_note = ctk.CTkEntry(win, justify="right", width=380)
        ent_note.insert(0, common_note)
        ent_note.pack(pady=5)''')

rep('''            new_note = ent_note.get().strip()
            any_blocked = False''',
    '''            new_note = ent_note.get().strip()
            new_row_no = ent_row_no.get().strip()
            new_set_no = ent_set_no.get().strip()

            new_date = ent_date.get().strip()
            if len(new_date) < 10 or new_date[4] != "-":
                messagebox.showerror("خطأ", "الرجاء إدخال التاريخ بالصيغة YYYY-MM-DD.", parent=win)
                return
            # نُبقي وقت الحركة كما هو ما دام اليوم لم يتغيّر، فلا يتبدّل ترتيبها
            # المحاسبي بلا داعٍ داخل اليوم نفسه
            old_time = str(ref_dt)[11:] or datetime.datetime.now().strftime("%H:%M:%S")
            new_dt = f"{new_date} {old_time}"

            any_blocked = False''')

rep('''                if value > 0:
                    if existing:
                        existing["الوزن"] = value
                        existing["البيان"] = new_note
                        existing["trees_count"] = new_trees
                        if not self.save_invoice_to_db(existing["رقم الفاتورة"], existing):
                            any_blocked = True''',
    '''                if value > 0:
                    if existing:
                        existing["الوزن"] = value
                        existing["البيان"] = new_note
                        existing["trees_count"] = new_trees
                        existing["row_number"] = new_row_no
                        existing["set_number"] = new_set_no
                        existing["التاريخ"] = new_dt
                        if not self.save_invoice_to_db(existing["رقم الفاتورة"], existing):
                            any_blocked = True''')

rep('''                        inv_data = {"رقم الفاتورة": self.invoice_counter, "التاريخ": ref_dt, "الاسم": ref_name,
                                    "النوع": op_type, "الوزن": value, "البيان": new_note, "settled_status": "ACTIVE",
                                    "trees_count": new_trees, "قبل": 0.0, "بعد": 0.0, "set_number": "",
                                    "row_number": ref_row}''',
    '''                        inv_data = {"رقم الفاتورة": self.invoice_counter, "التاريخ": new_dt, "الاسم": ref_name,
                                    "النوع": op_type, "الوزن": value, "البيان": new_note, "settled_status": "ACTIVE",
                                    "trees_count": new_trees, "قبل": 0.0, "بعد": 0.0,
                                    "set_number": new_set_no, "row_number": new_row_no}''')

rep('''            upsert(sarf_inv, new_sarf, madin_type)
            upsert(qabd_inv, new_qabd, qabd_type)''',
    '''            upsert(sarf_inv, new_sarf, madin_type)
            upsert(qabd_inv, new_qabd, qabd_type)

            # أي حركة أخرى في نفس الصف (غير الصرف والقبض) تتبع الترقيم الجديد
            # أيضاً، وإلا انفصلت عن صفها وظهرت كصف مستقل بعد التعديل
            for extra in invs:
                if extra is sarf_inv or extra is qabd_inv:
                    continue
                extra["row_number"] = new_row_no
                extra["set_number"] = new_set_no
                extra["التاريخ"] = new_dt
                if not self.save_invoice_to_db(extra["رقم الفاتورة"], extra):
                    any_blocked = True''')

rep('''        win.geometry("520x460" if with_trees else "520x390")''',
    '''        win.geometry("540x610" if with_trees else "540x545")''')


# ==========================================================================
#  ٣) شريط الإجمالي داخل الشاشة: رصاصي غامق وأرقام بيضاء
# ==========================================================================
rep('''        total_tree = ttk.Treeview(total_holder, columns=columns, show="", height=1)
        for col in columns:
            total_tree.column(col, width=(col_widths or {}).get(col, 110), anchor="center", stretch=False)
        total_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        total_tree.pack(side="left", fill="x", expand=True)''',
    '''        total_tree = ttk.Treeview(total_holder, columns=columns, show="", height=1,
                                  style="Totals.Treeview")
        for col in columns:
            total_tree.column(col, width=(col_widths or {}).get(col, 110), anchor="center", stretch=False)
        # شريط رصاصي غامق بأرقام بيضاء ليتميّز بوضوح عن صفوف الجدول
        self.ensure_totals_bar_style()
        total_tree.tag_configure("total_tag", foreground="#ffffff", font=("Cairo", 14, "bold"))
        total_tree.pack(side="left", fill="x", expand=True)''')

rep('''    def sync_total_tree_columns(self, data_tree, total_tree):''',
    '''    def ensure_totals_bar_style(self):
        """نمط شريط الإجمالي: خلفية رصاصية غامقة ثابتة في الوضعين الفاتح والداكن"""
        if getattr(self, "_totals_style_ready", False):
            return
        try:
            style = ttk.Style()
            style.configure("Totals.Treeview",
                            background="#4a4f55", fieldbackground="#4a4f55",
                            foreground="#ffffff", rowheight=34, borderwidth=0)
            # الصف يبقى رصاصياً حتى عند التحديد، فلا يتغيّر شكل الشريط بالنقر
            style.map("Totals.Treeview",
                      background=[("selected", "#4a4f55")],
                      foreground=[("selected", "#ffffff")])
            self._totals_style_ready = True
        except Exception:
            pass

    def sync_total_tree_columns(self, data_tree, total_tree):''')


# ==========================================================================
#  ٤) شريط الإجمالي في العرض الكامل: بارز وواضح
# ==========================================================================
rep('''        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 6))

        data_tree, total_tree = self.create_sticky_total_tree(body, columns, height=24, col_widths=col_widths)''',
    '''        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 2))

        data_tree, total_tree = self.create_sticky_total_tree(body, columns, height=24, col_widths=col_widths)''')

rep('''        data_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))

        # ضبط عرض الأعمدة حسب المحتوى، ثم مطابقة الشريط الثابت معها''',
    '''        data_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))

        # عنوان صغير فوق الشريط يوضّح أنه إجمالي ثابت لا صف من الجدول
        ctk.CTkLabel(win, text="▼ الإجمالي (ثابت)", font=("Cairo", 11, "bold"),
                     text_color="#8b8f95").pack(pady=(0, 0))

        # ضبط عرض الأعمدة حسب المحتوى، ثم مطابقة الشريط الثابت معها''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة الثامنة عشرة على:", SRC)
