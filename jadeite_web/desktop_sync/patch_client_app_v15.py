# -*- coding: utf-8 -*-
"""
الدفعة الحادية عشرة — الجزء الثالث (ترحيل واسترجاع خياس البوليش والصافي):
  • ترحيل خياس البوليش كحركة مستقلة في صندوق خياس الطقوم (بعلامة تمييز)
  • استرجاعه عند إعادة بناء سطور الفاتورة (تعديل فاتورة مرحّلة)
  • إضافته لنافذة تعديل الفاتورة المرحّلة وقالب الطباعة
  • حفظ الصافي في حقل مخصّص ليُقرأ من صندوق خياس الطقوم بلا إعادة حساب

الاستخدام:  python3 patch_client_app_v15.py rageh-1-34-14-cloud.py
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
#  ١) علامة تمييز نوع الخياس داخل حركات صندوق الطقوم
# ==========================================================================
rep('''RAJI_PURITY = 750.0''',
    '''# علامات تمييز حركات خياس الطقوم داخل حقل trees_count (المستخدم كعلامة داخلية
# في هذا النظام أصلاً): تفصل خياس التلميع النهائي عن خياس البوليش عن الصافي
# دون إضافة عمود جديد لقاعدة البيانات — فتبقى نسخ العملاء القديمة متوافقة.
KHAYAS_MARK_FINAL = 0.0    # خياس التلميع النهائي (القيمة التاريخية الافتراضية)
KHAYAS_MARK_POLISH = 7.0   # خياس البوليش
KHAYAS_MARK_NET = 9.0      # صافي الطقم (سطر معلوماتي لا يؤثر على الخزينة)

RAJI_PURITY = 750.0''')


# ==========================================================================
#  ٢) الترحيل: خياس البوليش + سطر الصافي المعلوماتي
# ==========================================================================
rep('''            khayas_v = row.get("خياس", 0.0)

            # إذا كان السطر يجمع ذهب وماس معاً''',
    '''            khayas_v = row.get("خياس", 0.0)
            khayas_polish_v = row.get("خياس البوليش", 0.0)
            net_v = sale_net_weight(row)

            # إذا كان السطر يجمع ذهب وماس معاً''')

rep('''            # خياس الطقم: لا يدخل ضمن أوزان الطقم المباعة، بل يُرحّل لصندوق (خياس الطقوم)
            if khayas_v > 0:
                self.invoice_counter += 1
                khayas_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    "النوع": "خياس طقوم", "الوزن": khayas_v, "البيان": "خياس طقم",
                    "settled_status": "ACTIVE", "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }''',
    '''            # خياس البوليش: نفس معاملة خياس التلميع النهائي محاسبياً (كلاهما فاقد
            # يُرحّل لصندوق خياس الطقوم)، ويُميَّز بعلامة ليُفصل في العرض والتعديل
            if khayas_polish_v > 0:
                self.invoice_counter += 1
                polish_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    "النوع": "خياس طقوم", "الوزن": khayas_polish_v, "البيان": "خياس بوليش",
                    "settled_status": "ACTIVE", "trees_count": KHAYAS_MARK_POLISH, "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }
                self.invoices[self.invoice_counter] = polish_data
                self.save_invoice_to_db(self.invoice_counter, polish_data)

            # سطر الصافي: معلوماتي بحت — يُسجَّل بحالة SETTLED_INOUT فيُستثنى من
            # كل حسابات الخزينة والفواقد، ووظيفته الوحيدة عرض الصافي في صندوق
            # خياس الطقوم بلا إعادة حسابه من عدة حركات متفرقة
            if abs(net_v) > 0.0001:
                self.invoice_counter += 1
                net_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    "النوع": "خياس طقوم", "الوزن": net_v, "البيان": "صافي الطقم",
                    "settled_status": "SETTLED_INOUT", "trees_count": KHAYAS_MARK_NET, "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }
                self.invoices[self.invoice_counter] = net_data
                self.save_invoice_to_db(self.invoice_counter, net_data)

            # خياس الطقم: لا يدخل ضمن أوزان الطقم المباعة، بل يُرحّل لصندوق (خياس الطقوم)
            if khayas_v > 0:
                self.invoice_counter += 1
                khayas_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    "النوع": "خياس طقوم", "الوزن": khayas_v, "البيان": "خياس طقم",
                    "settled_status": "ACTIVE", "trees_count": KHAYAS_MARK_FINAL, "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }''')


# ==========================================================================
#  ٣) إعادة بناء السطور عند تعديل فاتورة مرحّلة
# ==========================================================================
rep('''                                 "الماس": 0.0, "خياس": 0.0}''',
    '''                                 "الماس": 0.0, "خياس": 0.0, "خياس البوليش": 0.0}''')

rep('''            elif t == "خياس طقوم":
                r["خياس"] = round(r["خياس"] + w, 2)''',
    '''            elif t == "خياس طقوم":
                mark = inv.get("trees_count", 0.0) or 0.0
                if mark == KHAYAS_MARK_NET:
                    continue      # سطر الصافي معلوماتي ويُعاد حسابه، فلا يُعاد تحميله
                if mark == KHAYAS_MARK_POLISH:
                    r["خياس البوليش"] = round(r["خياس البوليش"] + w, 2)
                else:
                    r["خياس"] = round(r["خياس"] + w, 2)''')

# استبعاد سطر الصافي من تجميع الفواتير (لئلا يُحتسب مرتين في العرض)
rep('''            elif t == "خياس طقوم":
                g["خياس"] = round(g["خياس"] + w, 2)''',
    '''            elif t == "خياس طقوم":
                if (inv.get("trees_count", 0.0) or 0.0) == KHAYAS_MARK_NET:
                    continue      # سطر معلوماتي لا يُضاف لإجمالي الخياس
                g["خياس"] = round(g["خياس"] + w, 2)''')


# ==========================================================================
#  ٤) نافذة تعديل الفاتورة المرحّلة: خانة خياس البوليش
# ==========================================================================
rep('''        add_field("خياس", "خياس")
        add_field("الماس", "الماس")''',
    '''        add_field("خياس التلميع النهائي", "خياس")
        add_field("خياس البوليش", "خياس البوليش")
        add_field("الماس", "الماس")''')

rep('''            for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس", "خياس"):''',
    '''            for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس", "خياس", "خياس البوليش"):''')

rep('''            if (vals["ذهب"] <= 0 and vals["فصوص"] <= 0 and vals["أحجار بعد الخصم"] <= 0
                    and vals["الماس"] <= 0 and vals["خياس"] <= 0):''',
    '''            if (vals["ذهب"] <= 0 and vals["فصوص"] <= 0 and vals["أحجار بعد الخصم"] <= 0
                    and vals["الماس"] <= 0 and vals["خياس"] <= 0 and vals["خياس البوليش"] <= 0):''')

rep('''        cols = ("رقم الصف", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم", "الماس", "خياس")
        rows_tree = self.create_standard_treeview(table_frame, cols, height=9)''',
    '''        cols = ("رقم الصف", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم",
                "الماس", "خياس التلميع النهائي", "خياس البوليش", "الصافي")
        rows_tree = self.create_standard_treeview(table_frame, cols, height=9)''')

rep('''            tot = {k: 0.0 for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس", "خياس")}
            for r in edit_rows:
                for k in tot:
                    tot[k] = round(tot[k] + r.get(k, 0.0), 2)
                rows_tree.insert("", "end", values=(
                    r.get("row_number", "") or "-", r.get("set_number", "") or "-",
                    f"{r.get('ذهب', 0):.2f}" if r.get("ذهب") else "-",
                    f"{r.get('فصوص', 0):.2f}" if r.get("فصوص") else "-",
                    f"{r.get('أحجار', 0):.2f}" if r.get("أحجار") else "-",
                    f"{r.get('أحجار بعد الخصم', 0):.2f}" if r.get("أحجار بعد الخصم") else "-",
                    f"{r.get('الماس', 0):.2f}" if r.get("الماس") else "-",
                    f"{r.get('خياس', 0):.2f}" if r.get("خياس") else "-",
                ))
            if edit_rows:
                rows_tree.insert("", "end", values=(
                    "الإجمالي", "-", f"{tot['ذهب']:.2f}", f"{tot['فصوص']:.2f}", f"{tot['أحجار']:.2f}",
                    f"{tot['أحجار بعد الخصم']:.2f}", f"{tot['الماس']:.2f}", f"{tot['خياس']:.2f}"), tags=("total_tag",))''',
    '''            tot = {k: 0.0 for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس",
                                    "خياس", "خياس البوليش")}
            tot_net = 0.0
            for r in edit_rows:
                for k in tot:
                    tot[k] = round(tot[k] + r.get(k, 0.0), 2)
                net_r = sale_net_weight(r)
                tot_net = round(tot_net + net_r, 2)
                rows_tree.insert("", "end", values=(
                    r.get("row_number", "") or "-", r.get("set_number", "") or "-",
                    f"{r.get('ذهب', 0):.2f}" if r.get("ذهب") else "-",
                    f"{r.get('فصوص', 0):.2f}" if r.get("فصوص") else "-",
                    f"{r.get('أحجار', 0):.2f}" if r.get("أحجار") else "-",
                    f"{r.get('أحجار بعد الخصم', 0):.2f}" if r.get("أحجار بعد الخصم") else "-",
                    f"{r.get('الماس', 0):.2f}" if r.get("الماس") else "-",
                    f"{r.get('خياس', 0):.2f}" if r.get("خياس") else "-",
                    f"{r.get('خياس البوليش', 0):.2f}" if r.get("خياس البوليش") else "-",
                    f"{net_r:.2f}",
                ))
            if edit_rows:
                rows_tree.insert("", "end", values=(
                    "الإجمالي", "-", f"{tot['ذهب']:.2f}", f"{tot['فصوص']:.2f}", f"{tot['أحجار']:.2f}",
                    f"{tot['أحجار بعد الخصم']:.2f}", f"{tot['الماس']:.2f}", f"{tot['خياس']:.2f}",
                    f"{tot['خياس البوليش']:.2f}", f"{tot_net:.2f}"), tags=("total_tag",))''')


# ==========================================================================
#  ٥) قالب الطباعة: خياس البوليش والصافي
# ==========================================================================
rep('''            "diamond": 0.0, "khayas": 0.0, "row_number": "", "invoice_no": None, "voucher": ""''',
    '''            "diamond": 0.0, "khayas": 0.0, "khayas_polish": 0.0, "net": 0.0,
            "row_number": "", "invoice_no": None, "voucher": ""''')

rep('''            elif t == "خياس طقوم":
                data["khayas"] += inv["الوزن"]''',
    '''            elif t == "خياس طقوم":
                mark = inv.get("trees_count", 0.0) or 0.0
                if mark == KHAYAS_MARK_POLISH:
                    data["khayas_polish"] += inv["الوزن"]
                elif mark == KHAYAS_MARK_NET:
                    data["net"] += inv["الوزن"]
                else:
                    data["khayas"] += inv["الوزن"]''')

rep('''            5: {0: "الخياس", 1: f"{khayas_val:.2f}"},
        }
        y34, h34 = draw_mini_table(M, row3_top, col_w, "تفاصيل الأوزان", materials_cols, 6, row_h=8 * mm, fill_map=materials_fill)''',
    '''            5: {0: "خياس التلميع النهائي", 1: f"{khayas_val:.2f}"},
            6: {0: "خياس البوليش", 1: f"{data.get('khayas_polish', 0.0):.2f}"},
            7: {0: "الصافي", 1: f"{data.get('net', 0.0):.2f}"},
        }
        y34, h34 = draw_mini_table(M, row3_top, col_w, "تفاصيل الأوزان", materials_cols, 8, row_h=8 * mm, fill_map=materials_fill)''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الجزء الثالث من الدفعة الحادية عشرة على:", SRC)
