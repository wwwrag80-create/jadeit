# -*- coding: utf-8 -*-
"""1.93: الماس في المبيعات للعرض والمعرفة فقط، وخانات سطر البيع حسب نوع العملية.

  • الوزن القائم = الذهب + الفصوص + الأحجار، والمقيد = الذهب + الفصوص + الأحجار بعد الخصم — بلا الماس في كل
    موضع (الخانات، جدول السطور، نافذة التعديل، الفاتورة، التذاكر، قالب رقم التشغيل وسنده).
  • عملية «ذهب»: كل الخانات ما عدا الماس؛ عملية «الماس»: رقم التشغيل والذهب والماس فقط.
  • الخانة المخفية لا تُقرأ عند «إضافة»، ولا يُتنقّل إليها، وعمودها خارج الجدول ما لم يحمل قيمة؛ وتبديل النوع لا يمرّ
    وفي السطور قيمة في خانة لا تظهر في النوع الجديد.
  • بيع طقمٍ بنوعٍ تخفى فيه خانة لا يمسح قيمتها من قالب رقم التشغيل."""
import ast, datetime, io, sys, textwrap

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


def flat(text):
    """النص بمسافات موحّدة — لمقارنة أسطر متتالية بلا اعتماد على عمق الإزاحة"""
    return " ".join(text.split())


def module_src(name):
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


class Box:
    def __init__(self):
        self.log = []

    def showwarning(self, title, msg, **k):
        self.log.append((title, msg))


box = Box()
ns = {"messagebox": box, "save_ui_pref": lambda *a: None, "datetime": datetime}
for fn in ("sale_standing_weight", "sale_bound_weight"):
    exec(module_src(fn), ns)
MEMBERS = ("SALE_KIND_GOLD", "SALE_KIND_DIAMOND", "SALE_KINDS", "SALE_KIND_HIDDEN_KEYS", "SALE_EDIT_FIELDS",
           "SALE_TABLE_COL_KEYS", "current_sale_kind", "sale_hidden_keys", "sale_value_present",
           "sale_rows_hidden_values", "sale_field_hidden", "request_sale_kind", "sb_apply_sale")
exec("class App:\n" + "\n".join(textwrap.indent(member(m), "    ") for m in MEMBERS), ns)
G, D = "ذهب", "الماس"
standing, bound = ns["sale_standing_weight"], ns["sale_bound_weight"]

# ═══ ١) الوزنان بلا الماس — مصدر واحد في كل موضع ═══
assert standing(30.0, 2.0, 3.0) == 35.0 and bound(30.0, 2.0, 2.1) == 34.1
assert standing(None, None, None) == 0.0 and bound(10.0, None, None) == 10.0
sites = {
    "build_sales_tab": ("weight_standing = sale_standing_weight(gold_v, gems_v, stones_v)",
                        "weight_bound = sale_bound_weight(gold_v, gems_v, stones_disc_v)"),
    "refresh_pending_sales_table": ('standing = sale_standing_weight(num(row, "ذهب"), num(row, "فصوص"), num(row, "أحجار"))',
                                    'bound = sale_bound_weight(num(row, "ذهب"), num(row, "فصوص"), num(row, "أحجار بعد الخصم"))'),
    "edit_pending_sale_row": ('standing = sale_standing_weight(read("ذهب"), read("فصوص"), read("أحجار"))',
                              'bound = sale_bound_weight(read("ذهب"), read("فصوص"), read("أحجار بعد الخصم"))'),
    "sales_summary_rows": ('"الوزن القائم": sale_standing_weight(gold, gems, stones)',
                           '"الوزن المقيد": sale_bound_weight(gold, gems, stones_disc)'),
    "sale_ticket_data": ("bound = sale_bound_weight(gold, gems, stones_after)",
                         '"standing": sale_standing_weight(gold, gems, stones)'),
    "set_voucher_sections": ('"bound": sale_bound_weight(gold, gems, disc) if sold else None',),
    "sb_values": ("bound = sale_bound_weight(net, gems, stones_disc) if net is not None else None",),
}
for name, needles in sites.items():
    body = member(name)
    for needle in needles:
        assert needle in body, (name, needle)
    for bad in ("+ diamond_v", '+ num(row, "الماس")', '+ read("الماس")', "stones_disc + diamond", "disc + diamond",
                "stones_after + diamond", "(diamond or 0.0), 2) if net"):
        assert bad not in body, (name, bad)
print("✔ الوزن القائم والمقيد بلا الماس من مصدر واحد: الخانات، جدول السطور، نافذة التعديل، الفاتورة، التذاكر، القالب وسنده")

# ═══ ٢) خانات كل نوع ═══
a = ns["App"]()
a._sale_kind = G
assert a.sale_hidden_keys() == {"الماس"} and a.sale_hidden_keys(G) == {"الماس"}
assert a.sale_hidden_keys(D) == {"فصوص", "أحجار", "أحجار بعد الخصم", "خياس", "خياس البوليش", "خياس المركب", "البيان"}
shown_d = [k for _l, k in a.SALE_EDIT_FIELDS if k not in a.sale_hidden_keys(D)]
shown_g = [k for _l, k in a.SALE_EDIT_FIELDS if k not in a.sale_hidden_keys(G)]
assert shown_d == ["set_number", "ذهب", "الماس"], shown_d
assert "الماس" not in shown_g and len(shown_g) == len(a.SALE_EDIT_FIELDS) - 1
assert set(dict(a.SALE_TABLE_COL_KEYS).values()) >= a.sale_hidden_keys(D) | a.sale_hidden_keys(G)
assert a.sale_value_present("البيان", " ") is False and a.sale_value_present("فصوص", "0") is False
assert a.sale_value_present("الماس", 0.4) and a.sale_value_present("set_number", "88001")
print("✔ عملية الذهب: كل الخانات ما عدا الماس؛ عملية الماس: رقم التشغيل والذهب والماس فقط")

# ═══ ٣) تبديل النوع لا يُخفي قيمة في سطور الفاتورة ═══
calls = []
a.set_sale_kind = lambda k, initial=False: (calls.append(k), setattr(a, "_sale_kind", k))
a.pending_sale_rows = [{"row_number": "1", "set_number": "88001", "ذهب": 30.0, "فصوص": 2.0},
                       {"row_number": "2", "set_number": "88002", "ذهب": 20.0, "البيان": "خاص"}]
assert a.request_sale_kind(D) is False and calls == [] and a.current_sale_kind() == G
title, msg = box.log[-1]
assert "السطر 1: الفصوص" in msg and "السطر 2: البيان" in msg, msg
a.pending_sale_rows = [{"row_number": "1", "set_number": "88001", "ذهب": 30.0, "الماس": 0}]
assert a.request_sale_kind(D) is True and calls == [D]
a.pending_sale_rows = [{"row_number": "1", "set_number": "88001", "ذهب": 30.0, "الماس": 1.5}]
assert a.request_sale_kind(G) is False and "السطر 1: الماس" in box.log[-1][1]
assert a.request_sale_kind(D) is True                  # النوع نفسه: لا فحص
a.pending_sale_rows = []
assert a.request_sale_kind(G) is True and a.current_sale_kind() == G
print("✔ تبديل نوع العملية يُرفض (برسالة تسمّي السطر والخانة) وفي السطور قيمة لا تظهر في النوع الجديد")

# ═══ ٤) الخانة المخفية لا تُقرأ، ولا يُتنقّل إليها، وعمودها خارج الجدول ═══
stage = member("stage_sale_row")
assert "hidden = self.sale_hidden_keys()" in stage and "if key in hidden: return 0.0" in flat(stage)
assert 'diamond_v = safe_val(self.sale_diamond, "الماس")' in stage
assert '"البيان": "" if "البيان" in hidden else self.sale_row_note.get().strip()' in stage
build = member("build_sales_tab")
assert "self.bind_enter_navigation(nav_fields, on_last=self.stage_sale_row, skip=self.sale_field_hidden)" in build
assert "self.apply_sale_kind_fields()" in build and "command=lambda k=kind: self.request_sale_kind(k)" in build
assert "return 0.0 if key in hidden else safe_read(entry)" in build
apply_fn = member("apply_sale_kind_fields")
assert 'if "أحجار" not in hidden: items.append(self._sale_pct_cells)' in flat(apply_fn)
assert "items.append((None, self._sale_add_btn))" in apply_fn and "self.refresh_pending_sales_table()" in apply_fn
assert "self.apply_sale_kind_fields()" in member("set_sale_kind")
table = member("refresh_pending_sales_table")
assert "tree.configure(displaycolumns=shown)" in table and "hidden = self.sale_hidden_keys()" in table
edit = member("edit_pending_sale_row")
assert "if key in hidden_keys: new_row[key] = 0.0" in flat(edit)
assert "order = [entries[key] for _l, key in shown_fields]" in edit
w1, w2 = object(), object()
a._sale_hidden_widgets = {w1}
assert a.sale_field_hidden(w1) and not a.sale_field_hidden(w2)
print("✔ الخانة المخفية صفر عند «إضافة» (ولو مُلئت من القالب)، يتخطاها Enter والأسهم، وعمودها ونافذة التعديل بلا هي")

# ═══ ٥) قالب رقم التشغيل: البيع بنوعٍ تخفى فيه خانة لا يمسح قيمتها ═══
a.sb_set_kind_mark = lambda rec, field, at=None, period=None: None
a.SB_READY = "ready"
rec = {"gems": 2.0, "stones": 3.0, "stones_pct": 70.0, "diamond": 0.5, "status": "draft"}
a.sb_apply_sale(rec, 2.0, 3.0, 2.1, 0.0, "عميل", "2026-10-15 10:00:00", G)
assert (rec["gems"], rec["stones"], rec["diamond"], rec["kind"]) == (2.0, 3.0, 0.5, G), rec
rec = {"gems": 2.0, "stones": 3.0, "stones_pct": 70.0, "diamond": 0.5, "status": "draft"}
a.sb_apply_sale(rec, 0.0, 0.0, 0.0, 0.8, "عميل", "2026-10-15 10:00:00", D)
assert (rec["gems"], rec["stones"], rec["stones_pct"], rec["diamond"]) == (2.0, 3.0, 70.0, 0.8), rec
rec = {"diamond": 0.5, "status": "draft"}
a.sb_apply_sale(rec, 1.0, 0.0, 0.0, 0.7, "عميل", "2026-10-15 10:00:00", G)       # فاتورة أقدم بماسٍ في عملية ذهب
assert rec["diamond"] == 0.7 and rec["gems"] == 1.0 and rec["stones"] is None
rec = {"diamond": 0.5, "status": "draft"}
a.sb_apply_sale(rec, 0.0, 0.0, 0.0, 0.0, "عميل", "2026-10-15 10:00:00", "")      # بلا نوع: كما كانت
assert rec["diamond"] is None
values = member("sb_values")
assert 'hidden = self.sale_hidden_keys(sale.get("kind")) if sale.get("kind") in self.SALE_KINDS else set()' in values
assert 'pieces_w = round(sale["gold"] + sale["gems"] + sale["stones"] + sale["diamond"] + rest, 2)' in values
print("✔ بيع طقمٍ بالذهب لا يمسح ماسه من القالب، وبالماس لا يمسح فصوصه وأحجاره (والفاتورة الأقدم تُكتب كما كانت)")

print("\n✅ 1.93: الماس للعرض في المبيعات، وخانات كل نوع عملية سليمة")
