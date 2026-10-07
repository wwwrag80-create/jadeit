# -*- coding: utf-8 -*-
"""
قالب فاتورة المبيعات الإجمالية (الدفعة ٢٩) — أول صفحة في ملف الترحيل:
  • عمود «الخياس» بدل «خياس»: خياس بوليش 1 (خياس البوليش) + خياس بوليش 2 + خياس المركب لكل رقم تشغيل
  • آخر صف: إجمالي كل عمود
  • الترويسة: بيانات المصنع بالعربية يميناً وبالإنجليزية يساراً بلا تداخل، والشعار واضحاً في الوسط
    (كانت صورة ورقة الترويسة كاملة تُصغَّر في المنتصف فلا تُقرأ، والنصوص فوق بعضها)
  • رقم الفاتورة (اليدوي) في الجانب الأيسر
الرسم نفسه يُجرَّب فعلياً حيث تتوفّر reportlab (جهاز البناء)، وبقية الفحوص في كل مكان.
"""
import ast, base64, io, os, re, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.split("\n")
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def member(name):
    node = next(m for m in cls.body if (isinstance(m, ast.FunctionDef) and m.name == name)
                or (isinstance(m, ast.Assign) and getattr(m.targets[0], "id", "") == name))
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


marks = {n.targets[0].id: n.value.value for n in tree.body
         if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "").startswith("KHAYAS_MARK_")}
MEMBERS = ("SALES_SUMMARY_COLS", "LETTERHEAD_AR", "LETTERHEAD_EN", "LETTERHEAD_H", "SALES_SUMMARY_MIN_ROWS",
           "sale_khayas_total", "sales_summary_rows", "get_invoice_group_data", "pdf_logo", "draw_pdf_letterhead",
           "sales_summary_layout", "draw_sales_summary_pages")
ns = dict(marks, REPORTLAB_AVAILABLE=False)
exec("class App:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)
App = ns["App"]

# ═══ ١) «الخياس» لرقم التشغيل = بوليش 1 + بوليش 2 + المركب ═══
D, NAME = "2026-10-06 10:30:00", "عميل الفاتورة"


def mv(set_no, t, w, mark=0.0, status="ACTIVE", before=0.0, manual="F-2041"):
    return {"set_number": set_no, "التاريخ": D, "الاسم": NAME, "النوع": t, "الوزن": w, "trees_count": mark,
            "settled_status": status, "قبل": before, "رقم الفاتورة اليدوي": manual, "رقم الفاتورة": 0,
            "البيان": "", "row_number": "1"}


app = App()
app.invoices = dict(enumerate([
    mv("88001", "مبيعات ذهب", 30.5), mv("88001", "مبيعات فصوص وأحجار", 1.25),
    mv("88001", "مبيعات فصوص وأحجار", 1.40, mark=3.0, before=2.0), mv("88001", "مبيعات الماس", 0.4),
    mv("88001", "خياس طقوم", 0.30, marks["KHAYAS_MARK_FINAL"]),                       # خياس بوليش 2
    mv("88001", "خياس طقوم", 0.12, marks["KHAYAS_MARK_POLISH"], "MEMO"),              # خياس البوليش (بوليش 1)
    mv("88001", "خياس طقوم", 0.05, marks["KHAYAS_MARK_ASSEMBLER"], "MEMO"),           # خياس المركب
    mv("88001", "خياس طقوم", 9.99, marks["KHAYAS_MARK_NET"], "MEMO"),                 # صافي الطقم: ليس خياساً
    mv("88002", "مبيعات ذهب", 31.5), mv("88002", "خياس طقوم", 0.31, marks["KHAYAS_MARK_FINAL"]),
    mv("88002", "خياس طقوم", 0.04, marks["KHAYAS_MARK_ASSEMBLER"], "MEMO"),
], start=1))
d1 = app.get_invoice_group_data("88001", D, NAME)
d2 = app.get_invoice_group_data("88002", D, NAME)
assert (d1["khayas"], d1["khayas_polish"], d1["khayas_assembler"], d1["net"]) == (0.30, 0.12, 0.05, 9.99)
assert App.sale_khayas_total(d1) == 0.47 and App.sale_khayas_total(d2) == 0.35
assert d1["manual_no"] == "F-2041"
print("✔ «الخياس» لرقم التشغيل 88001 = بوليش 1 (0.12) + بوليش 2 (0.30) + المركب (0.05) = 0.47 — والصافي ليس منه")

cols = App.SALES_SUMMARY_COLS
assert cols == ("#", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم", "الماس", "الخياس",
                "الوزن القائم", "الوزن المقيد"), cols
assert "خياس" not in cols
rows, totals = app.sales_summary_rows([d1, d2])
assert rows[0] == {"set_number": "88001", "الذهب": 30.5, "الفصوص": 1.25, "الأحجار": 2.0, "الأحجار بعد الخصم": 1.4,
                   "الماس": 0.4, "الخياس": 0.47, "الوزن القائم": 34.15, "الوزن المقيد": 33.55}, rows[0]
assert rows[1]["الخياس"] == 0.35 and rows[1]["الوزن القائم"] == 31.5
for k in cols[2:]:
    assert totals[k] == round(sum(r[k] for r in rows), 2), k
assert totals["الخياس"] == 0.82 and totals["الذهب"] == 62.0
print("✔ عمود «خياس» استُبدل بـ«الخياس» في موضعه، وصف الإجمالي = مجموع كل عمود (الخياس 0.82، الذهب 62.00)")

# ═══ ٢) الترتيب بعد الترحيل: الفاتورة أولاً ═══
gen = member("generate_invoice_pdf")
assert (gen.index("self.draw_sales_summary_pages(") < gen.index("self.draw_sale_tickets(c, tickets)")
        < gen.index("self.draw_set_voucher_page(c, data)"))
print("✔ ملف الترحيل: فاتورة المبيعات أول صفحة، ثم تذاكر أرقام التشغيل، ثم سنداتها")

# ═══ ٣) الترويسة ورقم الفاتورة في القالب ═══
page = member("draw_sales_summary_pages")
head = member("draw_pdf_letterhead")
assert "self.draw_pdf_letterhead(" in page and "APP_LOGO_B64" not in page and "45 * mm" not in page
assert '"رقم الفاتورة"' in page and 'd.get("manual_no")' in page and "box(M, band_top, side_w" in page
assert "LETTERHEAD_AR" in head and "LETTERHEAD_EN" in head and "self.pdf_logo()" in head
assert App.LETTERHEAD_AR[0] == "مصنع جاديت للتصنيع" and App.LETTERHEAD_EN[0] == "Jadeite Factory"
assert 'resource_path("jadeite_logo.png")' in member("pdf_logo")
assert App.SALES_SUMMARY_MIN_ROWS == 26 and "max(len(page_rows), fill_rows) if is_last" in page
assert '"بضاعة صادرة" if page_no == 1 else "بضاعة صادرة (تابع)"' in page and "فاتورة مبيعات" not in page.split('"""')[2], \
    "عنوان القالب «بضاعة صادرة» (الدفعة ٣٣)"
assert not re.search(r'"توقيع [^"]*"', page) and "sig_y" not in page, "لا توقيعات في آخر الورقة (الدفعة ٣١)"
print("✔ الترويسة: بيانات المصنع (عربي يميناً، إنجليزي يساراً) والشعار وحده في الوسط — لا صورة الترويسة مصغّرة؛ "
      "ورقم الفاتورة اليدوي في مربع يساراً")

# ═══ ٤) الرسم الفعلي (حيث تتوفّر reportlab) ═══
try:
    import reportlab  # noqa: F401
    HAVE_RL = True
except ImportError:
    HAVE_RL = False

if HAVE_RL:
    from PIL import Image
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as pdf_canvas
    g = {"os": os, "sys": sys, "re": re, "io": io, "base64": base64, "Image": Image, "ImageReader": ImageReader,
         "A4": A4, "mm": mm, "pdfmetrics": pdfmetrics, "TTFont": TTFont, "REPORTLAB_AVAILABLE": True}
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        g.update(arabic_reshaper=arabic_reshaper, get_display=get_display, ARABIC_SHAPING_AVAILABLE=True)
    except ImportError:
        g["ARABIC_SHAPING_AVAILABLE"] = False
    for name in ("resource_path", "_ARABIC_FONT_NAME", "_ARABIC_FONT_BOLD_NAME", "_ARABIC_FONT_PATH_USED",
                 "_register_arabic_font", "_PDF_SYMBOL_RANGES", "_PDF_SYMBOL_SWAP", "_PDF_GLYPHS", "_pdf_font_has",
                 "pdf_text", "ar", "fit_font_size", "vcenter_baseline", "APP_LOGO_B64"):
        exec(module_src(name), g)
    g["__file__"] = os.path.abspath(TARGET)
    g["_register_arabic_font"]()
    g.update(marks)
    exec("class App:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), g)
    ar = g["ar"]

    class Rec(pdf_canvas.Canvas):
        """يسجّل كل نص يُرسم وموضعه، وكل صورة"""
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.items, self.images, self.rects, self.page, self.size = [], [], [], 1, 0

        def _rec(self, x, y, s, align):
            self.items.append((self.page, round(x, 1), round(y, 1), s, align))
            self.sizes.setdefault((self.page, s), self.size)

        sizes = {}

        def drawString(self, x, y, s, *a, **k):
            self._rec(x, y, s, "left"); return super().drawString(x, y, s, *a, **k)

        def drawRightString(self, x, y, s, *a, **k):
            self._rec(x, y, s, "right"); return super().drawRightString(x, y, s, *a, **k)

        def drawCentredString(self, x, y, s, *a, **k):
            self._rec(x, y, s, "center"); return super().drawCentredString(x, y, s, *a, **k)

        def setFont(self, name, size, *a, **k):
            self.size = size; return super().setFont(name, size, *a, **k)

        def rect(self, x, y, w, h, *a, **k):
            self.rects.append((self.page, round(h, 2))); return super().rect(x, y, w, h, *a, **k)

        def drawImage(self, img, x, y, width=None, height=None, **k):
            self.images.append((self.page, x, y, width, height)); return super().drawImage(img, x, y, width, height, **k)

        def showPage(self):
            self.page += 1; return super().showPage()

    PW, PH = A4
    rapp = g["App"]()
    many = [dict(d1, set_number=f"8800{i}") for i in range(1, 31)]
    out = io.BytesIO()
    c = Rec(out, pagesize=A4)
    rapp.draw_sales_summary_pages(c, many, NAME, D)
    c.save()
    pages = c.page - 1
    texts = {(p, s) for p, _x, _y, s, _a in c.items}
    assert pages == 2, pages
    for p in (1, 2):
        assert (p, ar("F-2041")) in texts and (p, ar("الخياس")) in texts, p
        no = next((x, y) for pg, x, y, s, a in c.items if pg == p and s == ar("F-2041"))
        assert no[0] < PW / 2, "رقم الفاتورة في الجانب الأيسر"
        assert (p, ar(f"صفحة {p} من 2")) in texts
    assert (1, ar("بضاعة صادرة")) in texts and (2, ar("بضاعة صادرة (تابع)")) in texts
    assert not any(ar("فاتورة مبيعات") in s for _p, s in texts), "العنوان القديم لا يظهر في القالب"
    assert (2, ar("الإجمالي")) in texts and (1, ar("الإجمالي")) not in texts
    assert (2, "14.10") in texts or (2, ar("14.10")) in texts                    # 30 × 0.47
    assert not any("توقيع" in s or ar("توقيع") in s for _p, s in texts), "لا توقيعات"
    # الترويسة: كل سطر في مكانه — لا سطرين على ارتفاع واحد (أو متقاربين) في الجهة نفسها
    for side_lines, align in ((rapp.LETTERHEAD_AR, "right"), (rapp.LETTERHEAD_EN, "left")):
        ys = sorted(y for pg, x, y, s, a in c.items if pg == 1 and a == align and s in {ar(t) for t in side_lines})
        assert len(ys) == 4 and all(b - a >= 4 * mm for a, b in zip(ys, ys[1:])), ys
    logo = [im for im in c.images if im[0] == 1]
    assert logo and abs(logo[0][4] - 27 * mm) < 0.1 and abs(logo[0][1] + logo[0][3] / 2 - PW / 2) < 0.5
    assert PH - (logo[0][2] + logo[0][4]) <= 8 * mm, "الترويسة مرفوعة لأعلى الورقة"
    print("✔ الرسم الفعلي: 30 طقماً في صفحتين (الأولى «بضاعة صادرة» والثانية «تابع»)، رقم الفاتورة يساراً في كل صفحة، "
          "صف الإجمالي (الخياس 14.10) في الأخيرة وحدها، بلا توقيعات، سطور الترويسة متباعدة، والشعار ٢٧ مم في الوسط")

    # ═══ ورقة A4 واحدة: ٢٦ صفاً بالضبط بخانات كبيرة وخط واضح، والجدول يمتد حتى أسفل الورقة ═══
    L = rapp.sales_summary_layout()
    assert rapp.SALES_SUMMARY_MIN_ROWS == 26 and L["cap_last"] == 26, L["cap_last"]
    table_bottom = L["table_top"] - L["head_h"] - L["cap_last"] * L["row_h"] - L["total_h"]
    assert 8 * mm <= table_bottom <= 10 * mm and L["row_h"] >= 7.7 * mm, (table_bottom / mm, L["row_h"] / mm)
    full = Rec(io.BytesIO(), pagesize=A4)
    rapp.draw_sales_summary_pages(full, [dict(d1, set_number=f"7700{i}") for i in range(1, L["cap_last"] + 1)], NAME, D)
    full_texts = {(p, s) for p, _x, _y, s, _a in full.items}
    assert full.page - 1 == 1 and (1, ar("الإجمالي")) in full_texts
    assert full.sizes[(1, "30.50")] >= 12 and full.sizes[(1, ar("الإجمالي"))] >= 12, full.sizes[(1, "30.50")]
    one = Rec(io.BytesIO(), pagesize=A4)
    rapp.draw_sales_summary_pages(one, [d1, d2], NAME, D)
    assert one.page - 1 == 1 and (1, ar("الإجمالي")) in {(p, s) for p, _x, _y, s, _a in one.items}
    body_rows = sum(1 for pg, h in one.rects if pg == 1 and abs(h - round(L["row_h"], 2)) < 0.01)
    assert body_rows == L["cap_last"] == 26, body_rows
    over = Rec(io.BytesIO(), pagesize=A4)
    rapp.draw_sales_summary_pages(over, [dict(d1, set_number=f"6600{i}") for i in range(1, 28)], NAME, D)
    assert over.page - 1 == 2, "الطقم السابع والعشرون ينتقل لصفحة «تابع»"
    print(f"✔ ورقة A4 واحدة: {L['cap_last']} صفاً بالضبط مع الإجمالي (والسابع والعشرون في صفحة «تابع»)، صف {L['row_h'] / mm:g} مم بخط "
          f"{full.sizes[(1, '30.50')]:g} واضح؛ وفاتورة بطقمين يُكمَّل جدولها حتى أسفل الورقة "
          f"(ينتهي على {table_bottom / mm:.1f} مم من حافتها) — بلا توقيعات")
else:
    print("… الرسم الفعلي يُجرَّب حيث تتوفّر reportlab (جهاز البناء) — هنا فحوص المنطق والمصدر وحدها")

print("\n✅ قالب فاتورة المبيعات: «الخياس» الجامع، إجمالي كل عمود، ترويسة مرتبة، ورقم الفاتورة يساراً — وأول صفحة بعد الترحيل")
