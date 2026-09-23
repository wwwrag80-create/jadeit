# -*- coding: utf-8 -*-
"""
الدفعة الثانية عشرة — الجزء الثاني:
  ١) خانة (خياس المركب) في المبيعات — تُملأ تلقائياً من مراحل التصنيع/المركبين
     بمطابقة رقم التشغيل وأخذ قيمة الفاقد اللحظي له
  ٢) معادلة الصافي تخصم خياس المركب أيضاً
  ٣) قسم جديد في صناديق الخياس: (ربح/خسارة الطقم) + حذف عمودي الصافي والخسارة
     من قسم خياس التلميع النهائي

الاستخدام:  python3 patch_client_app_v18.py rageh-1-34-14-cloud.py
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
#  ١) معادلة الصافي + علامة خياس المركب
# ==========================================================================
rep('''KHAYAS_MARK_NET = 9.0      # صافي الطقم (سطر معلوماتي لا يؤثر على الخزينة)''',
    '''KHAYAS_MARK_NET = 9.0      # صافي الطقم (سطر معلوماتي لا يؤثر على الخزينة)
KHAYAS_MARK_ASSEMBLER = 5.0  # خياس المركب (مأخوذ من مراحل التصنيع، معلوماتي هنا)''')

rep('''    return round(val("ذهب") - val("فصوص") - val("أحجار بعد الخصم")
                 - val("خياس") - val("خياس البوليش"), 2)''',
    '''    return round(val("ذهب") - val("فصوص") - val("أحجار بعد الخصم")
                 - val("خياس") - val("خياس البوليش") - val("خياس المركب"), 2)''')

rep('''    """صافي الطقم = الذهب − الفصوص − الأحجار بعد الخصم − خياس التلميع − خياس البوليش.''',
    '''    """صافي الطقم = الذهب − الفصوص − الأحجار بعد الخصم
                     − خياس التلميع النهائي − خياس البوليش − خياس المركب.''')


# ==========================================================================
#  ٢) خانة خياس المركب + جلبها تلقائياً برقم التشغيل
# ==========================================================================
rep('''        self.sale_khayas_polish = add_field("خياس البوليش")
        self.sale_diamond = add_field("الماس")''',
    '''        self.sale_khayas_polish = add_field("خياس البوليش")
        self.sale_khayas_assembler = add_field("خياس المركب")
        self.sale_diamond = add_field("الماس")

        # خياس المركب يُجلب تلقائياً من مراحل التصنيع بمجرد كتابة رقم التشغيل
        self.sale_set_number.bind("<KeyRelease>", self.autofill_assembler_khayas, add="+")
        self.sale_set_number.bind("<FocusOut>", self.autofill_assembler_khayas, add="+")''')

rep('''                      self.sale_stones, self.sale_stones_discount, self.sale_khayas, self.sale_khayas_polish,
                      self.sale_diamond]''',
    '''                      self.sale_stones, self.sale_stones_discount, self.sale_khayas, self.sale_khayas_polish,
                      self.sale_khayas_assembler, self.sale_diamond]''')

rep('''    def bind_arrow_navigation(self, fields):''',
    '''    def get_assembler_khayas_for_set(self, set_number, month=None):
        """الفاقد اللحظي للمركبين لرقم تشغيل معيّن.

        يبحث في كل عمال قسم (المركبين) عن الحركات المسجّلة بهذا رقم التشغيل،
        ويحسب فاقدها اللحظي بنفس معادلة كشف مراحل التصنيع بالضبط:
            صرف − قبض + ليز − (الراجع/عيار)
        فيبقى الرقم مطابقاً لما يراه المستخدم هناك حرفياً.
        """
        set_number = (set_number or "").strip()
        if not set_number:
            return 0.0

        month = month or self.current_display_month
        assemblers = set(self.categories.get("المركبين", []))
        if not assemblers:
            return 0.0

        # نجمّع حركات كل عامل على حدة، لأن الفاقد يُحسب لكل عامل ثم يُجمع
        per_worker = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE":
                continue
            if inv.get("الاسم") not in assemblers:
                continue
            if (inv.get("set_number", "") or "").strip() != set_number:
                continue
            if month and not str(inv.get("التاريخ", "")).startswith(month):
                continue

            d = per_worker.setdefault(inv["الاسم"], {
                "صرف": 0.0, "قبض": 0.0, "ليز": 0.0, "سلك راجع": 0.0, "عيار": 0.0})
            t = inv.get("النوع")
            w = inv.get("الوزن", 0.0)
            if t == "صرف ذهب":
                d["صرف"] += w
            elif t == "قبض ذهب":
                d["قبض"] += w
            elif t == "الليز":
                d["ليز"] += w
            elif t == "السلك الراجع":
                d["سلك راجع"] += w
            elif t == "العيار بعد الفحص":
                d["عيار"] = max(d["عيار"], w)

        total = 0.0
        for d in per_worker.values():
            total += d["صرف"] - d["قبض"] + d["ليز"] - raji_ayar(d["سلك راجع"], d["عيار"])
        return round(total, 2)

    def autofill_assembler_khayas(self, event=None):
        """يملأ خانة (خياس المركب) تلقائياً حسب رقم التشغيل المكتوب"""
        if not hasattr(self, "sale_khayas_assembler"):
            return
        try:
            value = self.get_assembler_khayas_for_set(self.sale_set_number.get())
            self.sale_khayas_assembler.delete(0, 'end')
            if abs(value) > 0.0001:
                self.sale_khayas_assembler.insert(0, f"{value:g}")
            if hasattr(self, "_recompute_sale_totals"):
                self._recompute_sale_totals()
        except Exception:
            pass   # الجلب التلقائي مساعدة: فشله يجب ألا يمنع الإدخال اليدوي

    def bind_arrow_navigation(self, fields):''')

# قراءة الخانة عند إضافة السطر
rep('''        khayas_polish_v = safe_val(self.sale_khayas_polish)''',
    '''        khayas_polish_v = safe_val(self.sale_khayas_polish)
        khayas_assembler_v = safe_val(self.sale_khayas_assembler)''')

rep('''        if (gold_v <= 0 and gems_v <= 0 and stones_v <= 0 and diamond_v <= 0
                and khayas_v <= 0 and khayas_polish_v <= 0):''',
    '''        if (gold_v <= 0 and gems_v <= 0 and stones_v <= 0 and diamond_v <= 0
                and khayas_v <= 0 and khayas_polish_v <= 0 and khayas_assembler_v == 0):''')

rep('''            "خياس البوليش": khayas_polish_v
        })''',
    '''            "خياس البوليش": khayas_polish_v, "خياس المركب": khayas_assembler_v
        })''')

rep('''        self.sale_khayas.delete(0, 'end')
        self.sale_khayas_polish.delete(0, 'end')''',
    '''        self.sale_khayas.delete(0, 'end')
        self.sale_khayas_polish.delete(0, 'end')
        self.sale_khayas_assembler.delete(0, 'end')''')

# الترحيل: تسجيل خياس المركب كسطر معلوماتي (مصدره مراحل التصنيع، فلا يُحمَّل مرتين)
rep('''            khayas_polish_v = row.get("خياس البوليش", 0.0)
            net_v = sale_net_weight(row)''',
    '''            khayas_polish_v = row.get("خياس البوليش", 0.0)
            khayas_assembler_v = row.get("خياس المركب", 0.0)
            net_v = sale_net_weight(row)''')

rep('''            # سطر الصافي: معلوماتي بحت''',
    '''            # خياس المركب: مصدره حركات المركبين في مراحل التصنيع وهو محمّل هناك
            # أصلاً على صندوق المركبين. يُسجَّل هنا معلوماتياً فقط (SETTLED_INOUT)
            # لحفظه مع الفاتورة وحساب الصافي — تحميله ثانيةً يعني احتساب الفاقد مرتين.
            if abs(khayas_assembler_v) > 0.0001:
                self.invoice_counter += 1
                asm_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    "النوع": "خياس طقوم", "الوزن": khayas_assembler_v, "البيان": "خياس المركب",
                    "settled_status": "SETTLED_INOUT", "trees_count": KHAYAS_MARK_ASSEMBLER,
                    "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }
                self.invoices[self.invoice_counter] = asm_data
                self.save_invoice_to_db(self.invoice_counter, asm_data)

            # سطر الصافي: معلوماتي بحت''')

# إعادة البناء عند تعديل فاتورة مرحّلة
rep('''                                 "الماس": 0.0, "خياس": 0.0, "خياس البوليش": 0.0}''',
    '''                                 "الماس": 0.0, "خياس": 0.0, "خياس البوليش": 0.0,
                                 "خياس المركب": 0.0}''')

rep('''                if mark == KHAYAS_MARK_POLISH:
                    r["خياس البوليش"] = round(r["خياس البوليش"] + w, 2)
                else:
                    r["خياس"] = round(r["خياس"] + w, 2)''',
    '''                if mark == KHAYAS_MARK_POLISH:
                    r["خياس البوليش"] = round(r["خياس البوليش"] + w, 2)
                elif mark == KHAYAS_MARK_ASSEMBLER:
                    r["خياس المركب"] = round(r["خياس المركب"] + w, 2)
                else:
                    r["خياس"] = round(r["خياس"] + w, 2)''')

# استبعاد السطور المعلوماتية من إجمالي خياس الفاتورة
rep('''            elif t == "خياس طقوم":
                if (inv.get("trees_count", 0.0) or 0.0) == KHAYAS_MARK_NET:
                    continue      # سطر معلوماتي لا يُضاف لإجمالي الخياس
                g["خياس"] = round(g["خياس"] + w, 2)''',
    '''            elif t == "خياس طقوم":
                if (inv.get("trees_count", 0.0) or 0.0) in (KHAYAS_MARK_NET, KHAYAS_MARK_ASSEMBLER,
                                                            KHAYAS_MARK_POLISH):
                    continue      # سطور معلوماتية لا تُضاف لإجمالي خياس الصندوق
                g["خياس"] = round(g["خياس"] + w, 2)''')

# نافذة تعديل الفاتورة المرحّلة
rep('''        add_field("خياس البوليش", "خياس البوليش")
        add_field("الماس", "الماس")''',
    '''        add_field("خياس البوليش", "خياس البوليش")
        add_field("خياس المركب", "خياس المركب")
        add_field("الماس", "الماس")''')

rep('''            for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس", "خياس", "خياس البوليش"):''',
    '''            for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس", "خياس",
                      "خياس البوليش", "خياس المركب"):''', count=2)

# القالب
rep('''            "diamond": 0.0, "khayas": 0.0, "khayas_polish": 0.0, "net": 0.0,''',
    '''            "diamond": 0.0, "khayas": 0.0, "khayas_polish": 0.0, "khayas_assembler": 0.0, "net": 0.0,''')

rep('''                if mark == KHAYAS_MARK_POLISH:
                    data["khayas_polish"] += inv["الوزن"]
                elif mark == KHAYAS_MARK_NET:
                    data["net"] += inv["الوزن"]
                else:
                    data["khayas"] += inv["الوزن"]''',
    '''                if mark == KHAYAS_MARK_POLISH:
                    data["khayas_polish"] += inv["الوزن"]
                elif mark == KHAYAS_MARK_ASSEMBLER:
                    data["khayas_assembler"] += inv["الوزن"]
                elif mark == KHAYAS_MARK_NET:
                    data["net"] += inv["الوزن"]
                else:
                    data["khayas"] += inv["الوزن"]''')

rep('''            6: {0: "خياس البوليش", 1: f"{data.get('khayas_polish', 0.0):.2f}"},
            7: {0: "الصافي", 1: f"{data.get('net', 0.0):.2f}"},
        }
        y34, h34 = draw_mini_table(M, row3_top, col_w, "تفاصيل الأوزان", materials_cols, 8, row_h=8 * mm, fill_map=materials_fill)''',
    '''            6: {0: "خياس البوليش", 1: f"{data.get('khayas_polish', 0.0):.2f}"},
            7: {0: "خياس المركب", 1: f"{data.get('khayas_assembler', 0.0):.2f}"},
            8: {0: "الصافي", 1: f"{data.get('net', 0.0):.2f}"},
        }
        y34, h34 = draw_mini_table(M, row3_top, col_w, "تفاصيل الأوزان", materials_cols, 9, row_h=7 * mm, fill_map=materials_fill)''')

# جدول السطور المعلّقة
rep('''        cols = ("رقم الصف", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم",
                "الماس", "خياس التلميع النهائي", "خياس البوليش", "الصافي",
                "الوزن القائم", "الوزن المقيد")''',
    '''        cols = ("رقم الصف", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم",
                "الماس", "خياس التلميع النهائي", "خياس البوليش", "خياس المركب", "الصافي",
                "الوزن القائم", "الوزن المقيد")''')

rep('''        tot = dict.fromkeys(["ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس",
                             "خياس", "خياس البوليش", "الصافي", "القائم", "المقيد"], 0.0)''',
    '''        tot = dict.fromkeys(["ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس",
                             "خياس", "خياس البوليش", "خياس المركب",
                             "الصافي", "القائم", "المقيد"], 0.0)''')

rep('''                f"{num(row, 'خياس البوليش'):.2f}" if num(row, "خياس البوليش") else "-",
                f"{net:.2f}",''',
    '''                f"{num(row, 'خياس البوليش'):.2f}" if num(row, "خياس البوليش") else "-",
                f"{num(row, 'خياس المركب'):.2f}" if num(row, "خياس المركب") else "-",
                f"{net:.2f}",''')

rep('''                f"{tot['خياس البوليش']:.2f}", f"{tot['الصافي']:.2f}",
                f"{tot['القائم']:.2f}", f"{tot['المقيد']:.2f}"), tags=("total_tag",))''',
    '''                f"{tot['خياس البوليش']:.2f}", f"{tot['خياس المركب']:.2f}", f"{tot['الصافي']:.2f}",
                f"{tot['القائم']:.2f}", f"{tot['المقيد']:.2f}"), tags=("total_tag",))''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الثاني من الدفعة الثانية عشرة على:", SRC)
