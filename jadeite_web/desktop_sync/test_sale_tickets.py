# -*- coding: utf-8 -*-
"""
تذاكر أرقام التشغيل في المبيعات (الدفعة ١٧، ومحتواها بطلب المستخدم في ١٨) — من دوال البرنامج نفسها:

  • تذكرة لكل رقم تشغيل في الفاتورة بترتيب سطورها، والسطر بلا رقم تشغيل لا تذكرة له.
  • محتواها فقط: باركود وQR ورقم التشغيل كبيراً، الفاتورة والتاريخ، والأوزان: الذهب، الفصوص،
    الأحجار، بعد الخصم، الماس، الوزن القائم (بالأحجار الخام)، والوزن المقيد (بعد الخصم).
  • رمز QR يحمل رقم التشغيل والوزن المقيد (يقرؤه أي تطبيق مسح بلا إنترنت)، والباركود الخطي يحملهما
    أيضاً (الدفعة ١٩) بخانة واحدة «88001 40.25» أو بخانتين «88001⇥40.25» أو الرقم وحده — يُختار للجهاز؛
    والبرنامج يأخذ رقم التشغيل وحده من أي صيغة منها أياً كانت لغة لوحة مفاتيح القارئ.
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


PREFS = {}
ns = {"re": re, "load_ui_prefs": lambda: dict(PREFS)}
MEMBERS = ["_SET_DIGITS", "_SCANNED_WEIGHT", "normalize_set_number", "scanned_set_number", "SALE_TYPES",
           "sale_tickets_with_invoice", "sale_ticket_data", "sale_ticket_qr", "SALE_BARCODE_MODES",
           "DEFAULT_SALE_BARCODE_MODE", "sale_barcode_mode", "sale_ticket_barcode", "set_sale_move",
           "sale_invoice_groups"]
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

    def get_sale_invoice_records(self, key):
        return list(self.invoices.values())


app = App()
groups = [("٨٨٠٠١", DATE, CUST), ("", DATE, CUST), ("88002", DATE, CUST)]
t = app.sale_ticket_data(groups)
assert [x["set_number"] for x in t] == ["88001", "88002"], "السطر بلا رقم لا تذكرة له، والأرقام الهندية توحَّد"
a, b = t
assert set(a) == {"set_number", "invoice", "date", "gold", "gems", "stones", "stones_after", "diamond",
                  "standing", "bound", "qr", "barcode"}, "محتوى التذكرة كما طلبه المستخدم فقط"
assert a["invoice"] == "S-7001" and a["date"] == "2026-09-20"
assert (a["gold"], a["gems"], a["stones"], a["stones_after"], a["diamond"]) == (35.25, 2.5, 3.0, 2.1, 0.4)
assert a["standing"] == round(35.25 + 2.5 + 3.0 + 0.4, 2) == 41.15
assert a["bound"] == round(35.25 + 2.5 + 2.1 + 0.4, 2) == 40.25
assert b["stones_after"] == 0.0 and b["bound"] == b["standing"] == 20.0
print("✔ تذكرة لكل رقم تشغيل بترتيب السطور (والسطر بلا رقم لا تذكرة له)، بالمحتوى المطلوب فقط: الفاتورة والتاريخ "
      "والذهب والفصوص والأحجار وبعد الخصم والماس، والقائم 41.15 والمقيد 40.25")

assert a["qr"] == "رقم التشغيل: 88001 | الوزن المقيد: 40.25 جم" and b["qr"].endswith("| الوزن المقيد: 20.00 جم")
# الباركود الخطي: الرقم والوزن المقيد (خانة واحدة افتراضياً)، أو خانتان بـ Tab، أو الرقم وحده
assert a["barcode"] == "88001 40.25" and b["barcode"] == "88002 20.00", "افتراضياً: خانة واحدة"
PREFS["sale_barcode_mode"] = "tab"
assert app.sale_ticket_data(groups)[0]["barcode"] == "88001\t40.25"
PREFS["sale_barcode_mode"] = "number"
assert app.sale_ticket_data(groups)[0]["barcode"] == "88001"
PREFS["sale_barcode_mode"] = "عبث"
assert app.sale_barcode_mode() == "one" and app.sale_ticket_data(groups)[0]["barcode"] == "88001 40.25"
PREFS.clear()
assert app.sale_ticket_barcode("A-7", 0.5, "one") == "A-7 0.50"
print("✔ الباركود الخطي يحمل رقم التشغيل ووزنه المقيد: «88001 40.25» في خانة واحدة، أو «88001⇥40.25» "
      "(Tab ينقل القارئ للخانة التالية)، أو الرقم وحده — يُختار ويُحفظ لهذا الجهاز")

S = ns["Base"].scanned_set_number
assert S("88001 40.25") == "88001" and S("88001\t40.25") == "88001" and S("٨٨٠٠١ ٤٠.٢٥") == "88001"
assert S("A-7 0.50") == "A-7" and S("A 12") == "A 12" and S("88001 40.2") == "88001 40.2", "لا يُحذف إلا وزن بخانتين عشريتين"
assert S(a["qr"]) == "88001" and S("٨٨٠٠١") == "88001" and S(" 88001 ") == "88001"
assert S(": 88001 | : 40.25 ") == "88001", "قارئ بلوحة إنجليزية أسقط الحروف العربية"
assert S("vrl hgja.dg 88001 | hg,.k 40.25") == "88001", "قارئ حوّل الحروف العربية لاتينية بلا نقطتين"
assert S("رقم التشغيل: A 12 | الوزن المقيد: 1.00 جم") == "A 12" and S("") == "" and S(None) == ""
print("✔ رمز QR = «رقم التشغيل: 88001 | الوزن المقيد: 40.25 جم» يعرضه أي تطبيق مسح بلا إنترنت، "
      "والبرنامج يأخذ منه رقم التشغيل وحده (ولو أسقط القارئ الحروف العربية)")

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
assert "code128.Code128(code" in draw and 'qr.QrCodeWidget(t["qr"])' in draw and "c.setDash(3, 2)" in draw
assert 'code = t.get("barcode") or t["set_number"]' in draw and "max(0.6, room / bar.width)" in draw
for label in ("الذهب", "الفصوص", "الأحجار", "بعد الخصم", "الماس", "الوزن القائم", "الوزن المقيد", "الفاتورة", "التاريخ"):
    assert f'"{label}"' in draw, label
for gone in ("صافي الطقم", "خياس التلميع", "البوليش", "المركب", "العميل", "الصانع", '"الصف"'):
    assert gone not in draw and gone not in body("sale_ticket_data"), gone
for fn in ("open_set_number_trace", "on_stage_set_number_entered", "global_search"):
    assert "self.scanned_set_number(" in body(fn), fn
assert "TICKETS_PER_ROW, TICKET_ROWS = 2, 4" in src
assert "self.draw_sale_tickets(c, tickets)" in body("print_sale_tickets")
assert "command=self.print_selected_sale_tickets" in body("build_sales_ops_ui")
assert 'save_ui_pref("sale_tickets_with_invoice"' in body("build_sales_ops_ui")
assert 'save_ui_pref("sale_barcode_mode", modes[label])' in body("build_sales_ops_ui")
assert "تذكرة لكل رقم تشغيل" in body("commit_sale_invoice")
tr = body("open_set_number_trace")
assert "self.set_sale_move(moves)" in tr and "فاتورة البيع" in tr and "self.print_sale_tickets(" in tr
print("✔ الترحيل والطباعة يرفقان صفحة التذاكر بعد الفاتورة (٨ تذاكر في الصفحة بحدود قصّ)، ومسح QR التذكرة "
      "في التتبّع والبحث وخانة رقم التشغيل يأخذ الرقم وحده، "
      "وزر «تذاكر الطقوم» في العمليات، والمسح يفتح فاتورة البيع وتذكرته")

print("\n✅ تذاكر أرقام التشغيل في المبيعات سليمة")
