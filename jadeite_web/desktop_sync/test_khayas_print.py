# -*- coding: utf-8 -*-
"""1.93: زر «🖨️ طباعة القسم» في «صناديق الخياس» — القسم المختار PDF واضح ومرتب:
ترويسة المصنع، شريط عنوان (القسم، الفترة، تاريخ الطباعة)، بطاقة الملخّص، جدول بعناوين تتكرر في كل صفحة وصفوف
متناوبة الظل والسالب بالأحمر وصف الإجمالي بارز، «صفحة س من ص»، والتوقيعات آخرها؛ والأعمدة الكثيرة على صفحة عرضية.
السند يُفتح للمعاينة (_open_file → نافذة Edge المستقلة على ويندوز)."""
import ast, base64, io, os, re, sys, tempfile, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.splitlines()
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


# ═══ ١) الزر في شاشة صناديق الخياس، والبيانات من الجدول المعروض ═══
build = member("build_inquiries_tab")
assert 'text="🖨️ طباعة القسم"' in build and "command=self.print_khayas_section" in build
pr = member("print_khayas_section")
assert "self.draw_khayas_section_pdf(path, data)" in pr and "self._open_file(path)" in pr
assert "لا بيانات في قسم" in pr
pages = {}
exec("class P:\n" + textwrap.indent(member("khayas_print_pages"), "    "), pages)
kp = pages["P"].khayas_print_pages
assert kp(0, 20, 25) == [(0, 0)] and kp(20, 20, 25) == [(0, 20)]
assert kp(50, 20, 25) == [(0, 20), (20, 45), (45, 50)]
print("✔ زر «🖨️ طباعة القسم» بجوار «عرض»، يطبع القسم المعروض ويفتحه للمعاينة؛ والصفوف موزّعة على الصفحات")


class FakeTree:
    def __init__(self, cols, heads, rows):
        self.cols, self.heads, self.rows = cols, heads, rows

    def __getitem__(self, k):
        return self.cols

    def heading(self, c):
        return {"text": self.heads[self.cols.index(c)]}

    def get_children(self, _p=""):
        return [str(i) for i in range(len(self.rows))]

    def set(self, iid, c):
        return self.rows[int(iid)][0][self.cols.index(c)]

    def item(self, iid, opt):
        return self.rows[int(iid)][1]


class Label:
    def __init__(self, t):
        self.t = t

    def cget(self, _k):
        return self.t


# ═══ ٢) الرسم الفعلي ═══
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
    import tkinter as tk
    g = {"os": os, "sys": sys, "re": re, "io": io, "base64": base64, "Image": Image, "ImageReader": ImageReader,
         "A4": A4, "mm": mm, "pdfmetrics": pdfmetrics, "TTFont": TTFont, "REPORTLAB_AVAILABLE": True,
         "pdf_canvas": pdf_canvas, "datetime": __import__("datetime"), "tk": tk}
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
    g.update({"BRAND_KEY": "brand_identity", "BRAND_LOGO_KEY": "brand_logo_png", "json": __import__("json"),
              "sqlite3": __import__("sqlite3"), "log_cloud_error": lambda *a: None})     # هوية المصنع (1.98)
    MEMBERS = ("LETTERHEAD_AR", "LETTERHEAD_EN", "BRAND_FIELDS", "BRAND_DEFAULT", "_brand_setting", "brand_identity", "letterhead_ar", "letterhead_en", "default_brand_logo", "brand_logo_image", "pdf_logo", "draw_pdf_letterhead", "draw_standard_letterhead",
               "KHAYAS_PRINT_LANDSCAPE_COLS", "khayas_print_pages", "draw_khayas_section_pdf",
               "khayas_section_print_data", "table_headers", "SORT_ARROWS")
    exec("class App:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), g)
    App = g["App"]

    class Rec(pdf_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.items, self.page = [], 1

        def _rec(self, x, y, s):
            self.items.append((self.page, x, y, s))

        def drawString(self, x, y, s, *a, **k):
            self._rec(x, y, s); return super().drawString(x, y, s, *a, **k)

        def drawRightString(self, x, y, s, *a, **k):
            self._rec(x, y, s); return super().drawRightString(x, y, s, *a, **k)

        def drawCentredString(self, x, y, s, *a, **k):
            self._rec(x, y, s); return super().drawCentredString(x, y, s, *a, **k)

        def showPage(self):
            self.page += 1; return super().showPage()

    made = []

    def canvas_factory(*a, **k):
        cv = Rec(*a, **k)
        made.append(cv)
        return cv
    g["pdf_canvas"] = type("M", (), {"Canvas": staticmethod(canvas_factory)})
    ar = g["ar"]
    app = App()
    app.current_view_cat, app.current_display_month = "المصنعين", "2026-10"
    app.get_display_label = lambda cat: cat
    cols = ("الاسم", "الصرف", "القبض", "الليز", "البوليش", "مفنش 8", "مفنش 4", "ذهب/باقي", "مسموح 8", "مسموح 4",
            "ذهب/صافي", "السلك الراجع", "عيار الفحص", "المرجع 750", "الإنتاج", "الخياس")
    heads = ["الاسم", "الصرف", "قبض/كسر"] + list(cols[3:])
    rows = [((f"صانع {i + 1}",) + tuple(f"{(i + 1) * 1.25 + j:.2f}" for j in range(14)) + (f"{-0.35 if i == 2 else 0.4:.2f}",),
             ("green_tag",)) for i in range(48)]
    rows.append((("الإجمالي العام",) + tuple(f"{100 + j:.2f}" for j in range(15)), ("total_tag",)))
    app.tree = FakeTree(cols, heads, rows)
    app.lbl_section_summary = Label("إجمالي الخياس الفعلي لـ (المصنعين): 12.40 جم")
    data = app.khayas_section_print_data()
    assert data["heads"] == heads and len(data["rows"]) == 48 and len(data["totals"]) == 1
    assert data["totals"][0][0] == "الإجمالي العام" and data["summary"].endswith("12.40 جم") and data["period"] == "2026-10"
    out = tempfile.mkdtemp(prefix="khayas_print_")
    path = os.path.join(out, "wide.pdf")
    info = app.draw_khayas_section_pdf(path, data)
    cv = made[-1]
    assert info["landscape"] and cv._pagesize[0] > cv._pagesize[1], "١٦ عموداً ← صفحة عرضية"
    n_pages = info["pages"]
    assert n_pages >= 3, n_pages
    texts = [s for _p, _x, _y, s in cv.items]
    for p in range(1, n_pages + 1):
        assert ar(f"صفحة {p} من {n_pages}") in texts, p
        page_texts = [s for pg, _x, _y, s in cv.items if pg == p]
        assert ar("الاسم") in page_texts and ar("الخياس") in page_texts, "العناوين في كل صفحة"
        assert ar("صندوق خياس — المصنعين") in page_texts and ar("الفترة:") in page_texts and "2026-10" in page_texts
    assert sum(1 for s in texts if s == ar("إجمالي الخياس الفعلي لـ (المصنعين): 12.40 جم   ·   عدد الصفوف: 48")) == 1, \
        "بطاقة الملخّص في الصفحة الأولى وحدها"
    last = [s for pg, _x, _y, s in cv.items if pg == n_pages]
    assert ar("الإجمالي العام") in last and all(ar(w) in last for w in ("المحاسب", "مدير الإنتاج", "المدير"))
    for i in range(48):
        assert ar(f"صانع {i + 1}") in texts, i
    assert "-0.35" in texts
    pw, ph = cv._pagesize
    M = 12 * mm
    for _p, x, y, s in cv.items:
        assert M - 0.5 <= x <= pw - M + 0.5 and 0 < y < ph, (s, x, y)
    print(f"✔ ١٦ عموداً و٤٨ صفاً: صفحة عرضية × {n_pages} — العناوين والعنوان والفترة و«صفحة س من {n_pages}» في كل صفحة، "
          "والملخّص في الأولى، والإجمالي والتوقيعات في الأخيرة، وكل نص داخل الهوامش")

    # قسمٌ بأعمدة قليلة: صفحة طولية واحدة
    app.tree = FakeTree(("الشهر والسنة", "مدين", "دائن", "الرصيد"), ["الشهر والسنة", "الخياس", "القبض/الإقفال", "الرصيد التراكمي"],
                        [(("2026-09", "3.10", "1.00", "2.10"), ()), (("2026-10", "1.20", "0.00", "3.30"), ()),
                         (("الإجمالي", "4.30", "1.00", "3.30"), ("total_tag",))])
    app.current_view_cat = "التلميع"
    app.lbl_section_summary = Label("صافي خياس صندوق (التلميع): 3.30 جم")
    info = app.draw_khayas_section_pdf(os.path.join(out, "narrow.pdf"), app.khayas_section_print_data())
    cv = made[-1]
    assert not info["landscape"] and info["pages"] == 1 and cv._pagesize == A4
    page = [s for _p, _x, _y, s in cv.items]
    assert ar("صفحة 1 من 1") in page and ar("المحاسب") in page and ar("الرصيد التراكمي") in page
    print("✔ أربعة أعمدة: صفحة A4 طولية واحدة بالجدول وإجماليه والتوقيعات")
    if len(sys.argv) > 2:                                # نسخة للمعاينة البصرية
        import shutil
        shutil.copy(path, os.path.join(sys.argv[2], "khayas_wide.pdf"))
        shutil.copy(os.path.join(out, "narrow.pdf"), os.path.join(sys.argv[2], "khayas_narrow.pdf"))
else:
    print("… reportlab غير مثبتة: فحص الرسم الفعلي متروك")

print("\n✅ 1.93: طباعة قسم صناديق الخياس واضحة ومرتبة")
