# -*- coding: utf-8 -*-
"""
تذاكر أرقام التشغيل في المبيعات (الدفعة ١٧) — من دوال البرنامج نفسها:

  • تذكرة لكل رقم تشغيل في الفاتورة بترتيب سطورها، والسطر بلا رقم تشغيل لا تذكرة له.
  • أوزان التذكرة = أوزان الفاتورة نفسها: القائم (بالأحجار الخام) والمقيد (بعد الخصم)،
    والصافي بمعادلته الواحدة sale_net_weight، والصانع من مراحل التصنيع إن كان رقمه مسجّلاً.
  • عند الترحيل والطباعة تُرفق صفحة التذاكر بالفاتورة (خيار يُحفظ للجهاز)، وزر يطبعها وحدها،
    ونافذة تتبّع الرقم (المسح) تفتح فاتورة البيع وتذكرته.
"""
import ast, io, re, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def member_src(name):
    x = node(name)
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(x, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, x))


def body(name):
    return ast.get_source_segment(src, node(name))


net_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "sale_net_weight")
PREFS = {}
ns = {"re": re, "load_ui_prefs": lambda: dict(PREFS)}
exec(ast.get_source_segment(src, net_fn), ns)
MEMBERS = ["_SET_DIGITS", "normalize_set_number", "WORKER_SECTIONS", "SALE_TYPES", "sale_tickets_with_invoice",
           "sale_ticket_data", "set_sale_move", "sale_invoice_groups"]
exec("class Base:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in MEMBERS), ns)

DATE, CUST = "2026-09-20 10:00:00", "زبون"


class App(ns["Base"]):
    def __init__(self):
        self.invoices = {
            1: {"set_number": "٨٨٠٠١", "التاريخ": DATE, "الاسم": CUST, "رقم الفاتورة اليدوي": "S-7001",
                "النوع": "مبيعات ذهب", "رقم الفاتورة": 1, "settled_status": "ACTIVE"},
            2: {"set_number": "88002", "التاريخ": DATE, "الاسم": CUST, "رقم الفاتورة اليدوي": "S-7001",
                "النوع": "مبيعات ذهب", "رقم الفاتورة": 2, "settled_status": "ACTIVE"},
        }
        self.data = {
            "٨٨٠٠١": {"gold": 35.25, "gems": 2.5, "stones": 3.0, "stones_discount": "2.10", "diamond": 0.4,
                      "khayas": 0.3, "khayas_polish": 0.2, "khayas_assembler": 0.1, "row_number": "1"},
            "88002": {"gold": 20.0, "gems": 0.0, "stones": 0.0, "stones_discount": "", "diamond": 0.0,
                      "khayas": 0.15, "khayas_polish": 0.0, "khayas_assembler": 0.0, "row_number": ""},
        }

    def get_invoice_group_data(self, sn, date_str, name):
        assert date_str == DATE and name == CUST
        return dict(self.data[sn])

    def job_ticket_info(self, sn):
        return {"88001": {"worker": "سالم", "section": "المصنعين"},
                "88002": {"worker": "زبون", "section": "المبيعات"}}.get(sn)

    def get_display_label(self, sec):
        return sec

    def get_sale_invoice_records(self, key):
        return list(self.invoices.values())


app = App()
groups = [("٨٨٠٠١", DATE, CUST), ("", DATE, CUST), ("88002", DATE, CUST)]
t = app.sale_ticket_data(groups)
assert [x["set_number"] for x in t] == ["88001", "88002"], "السطر بلا رقم لا تذكرة له، والأرقام الهندية توحَّد"
a, b = t
assert a["invoice"] == "S-7001" and a["customer"] == CUST and a["date"] == "2026-09-20" and a["row"] == "1"
assert a["standing"] == round(35.25 + 2.5 + 3.0 + 0.4, 2) == 41.15
assert a["bound"] == round(35.25 + 2.5 + 2.1 + 0.4, 2) == 40.25
assert a["net"] == ns["sale_net_weight"]({"فصوص": 2.5, "أحجار بعد الخصم": 2.1, "خياس": 0.3, "خياس البوليش": 0.2,
                                          "خياس المركب": 0.1}) == 4.0
assert a["maker"] == "سالم (المصنعين)" and b["maker"] == "", "الصانع من المصنعين/المركبين فقط"
assert b["stones_after"] == 0.0 and b["net"] == -0.15 and b["row"] == ""
print("✔ تذكرة لكل رقم تشغيل بترتيب السطور (والسطر بلا رقم لا تذكرة له)، بأوزان الفاتورة: القائم 41.15 "
      "والمقيد 40.25 والصافي بمعادلته الواحدة، والصانع من مراحل التصنيع")

assert app.sale_tickets_with_invoice() is True
PREFS["sale_tickets_with_invoice"] = False
assert app.sale_tickets_with_invoice() is False
PREFS.clear()
print("✔ «إرفاق التذاكر بالفاتورة» مفعّل افتراضياً ويُحفظ لهذا الجهاز")

moves = [{"النوع": "صرف ذهب"}, {"النوع": "مبيعات ذهب", "x": 1}, {"النوع": "خياس طقوم"}, {"النوع": "مبيعات الماس", "x": 2}]
assert app.set_sale_move(moves)["x"] == 2 and app.set_sale_move(moves[:1]) is None
assert app.sale_invoice_groups(("S-7001", DATE, CUST)) == [("٨٨٠٠١", DATE, CUST), ("88002", DATE, CUST)]
print("✔ مجموعات الفاتورة للطباعة بترتيب سطورها، وحركة البيع في رحلة الرقم تُعرف")

gen = body("generate_invoice_pdf")
assert "if self.sale_tickets_with_invoice():" in gen and "self.draw_sale_tickets(c, tickets)" in gen
assert gen.index("self.draw_invoice_page(c, data)") < gen.index("self.draw_sale_tickets(c, tickets)")
draw = body("draw_sale_tickets")
assert "code128.Code128(code" in draw and 'qr.QrCodeWidget(t["set_number"])' in draw and "c.setDash(3, 2)" in draw
for label in ("الوزن القائم", "الوزن المقيد", "صافي الطقم", "خياس التلميع", "البوليش", "المركب", "الفاتورة", "العميل"):
    assert f'"{label}"' in draw, label
assert "TICKETS_PER_ROW, TICKET_ROWS = 2, 4" in src
assert "self.draw_sale_tickets(c, tickets)" in body("print_sale_tickets")
assert "command=self.print_selected_sale_tickets" in body("build_sales_ops_ui")
assert 'save_ui_pref("sale_tickets_with_invoice"' in body("build_sales_ops_ui")
assert "تذكرة لكل رقم تشغيل" in body("commit_sale_invoice")
tr = body("open_set_number_trace")
assert "self.set_sale_move(moves)" in tr and "فاتورة البيع" in tr and "self.print_sale_tickets(" in tr
print("✔ الترحيل والطباعة يرفقان صفحة التذاكر بعد الفاتورة (٨ تذاكر في الصفحة بحدود قصّ، باركود وQR بالرقم)، "
      "وزر «تذاكر الطقوم» في العمليات، والمسح يفتح فاتورة البيع وتذكرته")

print("\n✅ تذاكر أرقام التشغيل في المبيعات سليمة")
