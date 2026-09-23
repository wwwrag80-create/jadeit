# -*- coding: utf-8 -*-
"""
الدفعة الثامنة:
  ١) شاشة صناديق الخياس: كل أرقام الجدول بلون أسود في جميع الأقسام
  ٢) شريط الأونصة والعيارات: خلفية رصاصية غامقة، أرقام سوداء بارزة وأكبر قليلاً

الاستخدام:  python3 patch_client_app_v8.py rageh-1-34-14-cloud.py
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
#  ١) صناديق الخياس: كل الأرقام سوداء
# ==========================================================================
rep('''        self.tree.tag_configure("green_tag", foreground="#2ecc71", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self.open_worker_ledger_window)''',
    '''        # لون واحد أسود لكل أرقام الجدول في جميع الأقسام.
        # الوسمان القديمان (الأخضر/الأحمر) يبقيان معرّفين بنفس اللون حتى تعمل
        # كل مواضع الإدراج القائمة دون تعديلها، فلا يتغيّر أي منطق حسابي.
        self.tree.tag_configure("green_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("red_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("total_tag", foreground="#000000", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self.open_worker_ledger_window)''')

# جدول العرض الشهري للصناديق (المضافة والثابتة)
rep('''        self.tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 14, "bold"))
        if cat == "خياس الطقوم":''',
    '''        self.tree.tag_configure("total_tag", foreground="#000000", font=("Cairo", 14, "bold"))
        if cat == "خياس الطقوم":''')


# ==========================================================================
#  ٢) شريط سعر الذهب: رصاصي غامق + أرقام سوداء بارزة
# ==========================================================================
rep('''        self.gold_bar = ctk.CTkFrame(self, height=34, corner_radius=0,
                                      fg_color=("#f3e6c0", "#1c1710"))
        self.gold_bar.pack(side="bottom", fill="x")

        self.lbl_gold_price = ctk.CTkLabel(
            self.gold_bar, text="🥇 جارٍ جلب سعر الذهب العالمي…",
            font=ctk.CTkFont(family="Cairo", size=13, weight="bold"), text_color="#d4af37")
        self.lbl_gold_price.pack(side="right", padx=14, pady=5)

        ctk.CTkButton(self.gold_bar, text="🔄", width=32, height=24,
                      font=("Cairo", 12), fg_color="#555555", hover_color="#333333",
                      command=lambda: self.gold_watcher and self.gold_watcher.refresh_now()
                      ).pack(side="left", padx=8)''',
    '''        # خلفية رصاصية غامقة موحّدة في الوضعين الفاتح والداكن،
        # والأرقام سوداء بارزة عليها لأقصى وضوح
        self.gold_bar = ctk.CTkFrame(self, height=44, corner_radius=0,
                                      fg_color=("#9aa0a6", "#8a9096"),
                                      border_width=2, border_color=("#6d7378", "#6d7378"))
        self.gold_bar.pack(side="bottom", fill="x")

        self.lbl_gold_price = ctk.CTkLabel(
            self.gold_bar, text="🥇 جارٍ جلب سعر الذهب العالمي…",
            font=ctk.CTkFont(family="Cairo", size=16, weight="bold"),
            text_color="#000000")
        self.lbl_gold_price.pack(side="right", padx=16, pady=7)

        ctk.CTkButton(self.gold_bar, text="🔄 تحديث", width=78, height=28,
                      font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                      fg_color="#5f6368", hover_color="#42464a", text_color="#ffffff",
                      command=lambda: self.gold_watcher and self.gold_watcher.refresh_now()
                      ).pack(side="left", padx=10)''')

rep('''                self.lbl_gold_price.configure(
                    text=self.gold_watcher.display_text(),
                    text_color="#d4af37" if snapshot.get("ounce") else "#e67e22")''',
    '''                # الأسود عند توفر السعر، وبنّي غامق عند تعذّر التحديث
                # (يبقى واضحاً على الخلفية الرصاصية في الحالتين)
                self.lbl_gold_price.configure(
                    text=self.gold_watcher.display_text(),
                    text_color="#000000" if snapshot.get("ounce") else "#5a2d0c")''')

rep('''            self.lbl_gold_price.configure(text="🥇 سعر الذهب غير متاح (وحدة الأسعار غير موجودة)")''',
    '''            self.lbl_gold_price.configure(text="🥇 سعر الذهب غير متاح (وحدة الأسعار غير موجودة)",
                                          text_color="#5a2d0c")''')

io.open(SRC, "w", encoding="utf-8").write(src)
print("تم تطبيق الدفعة الثامنة على:", SRC)
