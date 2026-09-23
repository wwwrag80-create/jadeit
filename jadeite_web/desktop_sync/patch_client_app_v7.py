# -*- coding: utf-8 -*-
"""
الدفعة السابعة:
  ١) عمود (ذهب/صافي) في كشف المصنعين والمركبين = الفاقد اللحظي − مسموح/٨ − مسموح/٤
  ٢) تقليص عمود البيان ليتناسب الجدول
  ٣) شريط سعر الذهب العالمي أسفل الشاشة، يتحدّث كل ١٠ ثوانٍ

الاستخدام:  python3 patch_client_app_v7.py rageh-1-34-14-cloud.py
"""
import io
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(SRC, encoding="utf-8").read()


def rep(old, new, count=1):
    global src
    n = src.count(old)
    assert n == count, "MISMATCH (%d != %d):\n%s" % (n, count, old[:200])
    src = src.replace(old, new)


# ==========================================================================
#  ١) عمود (ذهب/صافي) بعد مسموح/٤
# ==========================================================================
rep('''            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "ليز", "سلك راجع", "عيار", "الفاقد اللحظي",
                    "مسموح/٨", "مسموح/٤", "البيان")''',
    '''            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "ليز", "سلك راجع", "عيار", "الفاقد اللحظي",
                    "مسموح/٨", "مسموح/٤", "ذهب/صافي", "البيان")''')

rep('''            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "مفنش 8", "مفنش 4", "بوليش", "ليز", "سلك راجع", "عيار",
                    "الفاقد اللحظي", "مسموح/٨", "مسموح/٤", "البيان")''',
    '''            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "مفنش 8", "مفنش 4", "بوليش", "ليز", "سلك راجع", "عيار",
                    "الفاقد اللحظي", "مسموح/٨", "مسموح/٤", "ذهب/صافي", "البيان")''')

# صفوف المركبين
rep('''                allow8 = round(data['قبض'] * ALLOWANCE_8, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", f"{allow8:.3f}", "-", note), tags=row_tags)''',
    '''                allow8 = round(data['قبض'] * ALLOWANCE_8, 2)
                # ذهب/صافي = الفاقد اللحظي بعد خصم المسموح (المركبين بلا مسموح/٤)
                net_gold = round(faqid - allow8, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["ذهب صافي"] = round(tot["ذهب صافي"] + net_gold, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", f"{allow8:.3f}", "-", f"{net_gold:.2f}", note), tags=row_tags)''')

# صفوف المصنعين
rep('''                allow8 = round(data['مفنش 8'] * ALLOWANCE_8, 2)
                allow4 = round(data['مفنش 4'] * ALLOWANCE_4, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["مسموح 4"] = round(tot["مسموح 4"] + allow4, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}", f"{data['مفنش 4']:.2f}", f"{data['بوليش']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", f"{allow8:.3f}", f"{allow4:.3f}", note), tags=row_tags)''',
    '''                allow8 = round(data['مفنش 8'] * ALLOWANCE_8, 2)
                allow4 = round(data['مفنش 4'] * ALLOWANCE_4, 2)
                # ذهب/صافي = الفاقد اللحظي بعد خصم المسموح ٨ و٤
                net_gold = round(faqid - allow8 - allow4, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["مسموح 4"] = round(tot["مسموح 4"] + allow4, 2)
                tot["ذهب صافي"] = round(tot["ذهب صافي"] + net_gold, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}", f"{data['مفنش 4']:.2f}", f"{data['بوليش']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", f"{allow8:.3f}", f"{allow4:.3f}", f"{net_gold:.2f}", note), tags=row_tags)''')

# مجاميع
rep('''        tot = {k: 0.0 for k in ("صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع",
                                "قبل", "بعد", "الخياس", "trees", "فاقد", "مسموح 8", "مسموح 4")}''',
    '''        tot = {k: 0.0 for k in ("صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع",
                                "قبل", "بعد", "الخياس", "trees", "فاقد", "مسموح 8", "مسموح 4",
                                "ذهب صافي")}''')

# سطور الإجمالي
rep('''f"{tot['سلك راجع']:.2f}", "-", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", "-", "-"), tags=("total_tag",))''',
    '''f"{tot['سلك راجع']:.2f}", "-", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", "-", f"{tot['ذهب صافي']:.2f}", "-"), tags=("total_tag",))''')

rep('''f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", f"{tot['مسموح 4']:.3f}", "-"), tags=("total_tag",))''',
    '''f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", f"{tot['مسموح 4']:.3f}", f"{tot['ذهب صافي']:.2f}", "-"), tags=("total_tag",))''')


# ==========================================================================
#  ٢) تقليص عمود البيان وضبط عرض الأعمدة
# ==========================================================================
rep('''        for c in cols:
            w = 200 if c == "البيان" else 120 if c == "التاريخ" else 90 if c in ("رقم التشغيل", "الصف") else 75
            self.op_ledger_tree.column(c, width=w, anchor="center")''',
    '''        for c in cols:
            # البيان مُقلَّص عمداً: الأرقام هي الأهم في هذا الكشف،
            # والنص الطويل كان يدفع الأعمدة الرقمية خارج الشاشة
            if c == "البيان":
                w = 110
            elif c == "التاريخ":
                w = 115
            elif c in ("رقم التشغيل", "الصف"):
                w = 85
            elif c in ("ذهب/صافي", "الفاقد اللحظي"):
                w = 88
            elif c in ("مسموح/٨", "مسموح/٤"):
                w = 72
            else:
                w = 70
            self.op_ledger_tree.column(c, width=w, anchor="center", stretch=False)''')


# ==========================================================================
#  ٣) شريط سعر الذهب العالمي
# ==========================================================================
rep('''try:
    from cloud_sync import CloudSync, install_sync_schema''',
    '''try:
    from gold_price import GoldPriceWatcher
    GOLD_PRICE_AVAILABLE = True
except Exception:
    GoldPriceWatcher = None
    GOLD_PRICE_AVAILABLE = False

try:
    from cloud_sync import CloudSync, install_sync_schema''')

# الشريط أسفل النافذة
rep('''        self.build_home_screen()
        self.show_home_screen()''',
    '''        self.build_gold_price_bar()
        self.build_home_screen()
        self.show_home_screen()''')

rep('''    def start_cloud_sync_engine(self):''',
    '''    def build_gold_price_bar(self):
        """شريط سعر الذهب العالمي أسفل الشاشة — يتحدّث تلقائياً كل ١٠ ثوانٍ"""
        self.gold_watcher = None

        self.gold_bar = ctk.CTkFrame(self, height=34, corner_radius=0,
                                      fg_color=("#f3e6c0", "#1c1710"))
        self.gold_bar.pack(side="bottom", fill="x")

        self.lbl_gold_price = ctk.CTkLabel(
            self.gold_bar, text="🥇 جارٍ جلب سعر الذهب العالمي…",
            font=ctk.CTkFont(family="Cairo", size=13, weight="bold"), text_color="#d4af37")
        self.lbl_gold_price.pack(side="right", padx=14, pady=5)

        ctk.CTkButton(self.gold_bar, text="🔄", width=32, height=24,
                      font=("Cairo", 12), fg_color="#555555", hover_color="#333333",
                      command=lambda: self.gold_watcher and self.gold_watcher.refresh_now()
                      ).pack(side="left", padx=8)

        if not GOLD_PRICE_AVAILABLE:
            self.lbl_gold_price.configure(text="🥇 سعر الذهب غير متاح (وحدة الأسعار غير موجودة)")
            return

        try:
            self.gold_watcher = GoldPriceWatcher(on_update=self._on_gold_price)
            self.gold_watcher.start()
        except Exception as e:
            log_cloud_error("تعذّر تشغيل مراقب سعر الذهب", e)

    def _on_gold_price(self, snapshot):
        """يُستدعى من الخيط الخلفي — يمرّ عبر after حتى لا يُسقط Tkinter"""
        def apply():
            try:
                self.lbl_gold_price.configure(
                    text=self.gold_watcher.display_text(),
                    text_color="#d4af37" if snapshot.get("ounce") else "#e67e22")
            except Exception:
                pass
        try:
            self.after(0, apply)
        except Exception:
            pass

    def start_cloud_sync_engine(self):''')

# إيقاف المراقب عند الإغلاق
rep('''    def on_app_closing(self):
        try:
            if getattr(self, 'cloud_sync', None):
                self.cloud_sync.stop()
        except Exception:
            pass''',
    '''    def on_app_closing(self):
        try:
            if getattr(self, 'cloud_sync', None):
                self.cloud_sync.stop()
        except Exception:
            pass
        try:
            if getattr(self, 'gold_watcher', None):
                self.gold_watcher.stop()
        except Exception:
            pass''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة السابعة على:", SRC)
