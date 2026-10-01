# -*- coding: utf-8 -*-
"""
قيمة الأرصدة بالريال (الدفعة ١٥) — من دوال البرنامج نفسها ومعادلة شريط السعر نفسها:

  • القيمة = الجرامات × سعر جرام عيار التقييم (gram_price من وحدة سعر الذهب، بلا معادلة جديدة).
  • عيار التقييم الافتراضي ١٨ (عيار ٧٥٠ المرجعي)، ويُختار من الشريط ويُحفظ لهذا الجهاز وحده.
  • بلا سعر معروف لا تُعرض قيمة مخترعة، وعيار غير معروف يُتجاهل.
  • الشريط وتفصيل الرصيد يتحدّثان مع كل سعر جديد ومع كل إعادة حساب للخزينة.
"""
import ast, io, os, sys, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gold_price

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
en_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "en")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def body(name):
    return ast.get_source_segment(src, node(name))


PREFS = {}
ns = {"gram_price": gold_price.gram_price, "LTR_MARK": "‎",
      "load_ui_prefs": lambda: dict(PREFS), "save_ui_pref": lambda k, v: PREFS.__setitem__(k, v)}
exec(ast.get_source_segment(src, en_fn), ns)
MEMBERS = ["VALUE_KARATS", "KARAT_LATIN", "DEFAULT_VALUE_KARAT", "value_karat", "set_value_karat",
           "gram_value_sar", "sar_value", "refresh_gold_value_label"]
exec("class Base:\n" + "\n".join(textwrap.indent(textwrap.dedent(ast.get_source_segment(src, node(m))), "    ")
                                 for m in MEMBERS), ns)
en = ns["en"]


class Label:
    text = ""
    def configure(self, text=""): self.text = text
    def cget(self, k): return self.text


class Watcher:
    ounce_price = 2650.0


class App(ns["Base"]):
    current_treasury_balance = 1000.0
    current_total_gold = 1250.5


app = App()
app.lbl_gold_value = Label()
app.gold_watcher = Watcher()
g18 = gold_price.gram_price(2650.0, "١٨")
assert app.value_karat() == "١٨" and app.gram_value_sar() == g18
assert app.sar_value(10) == round(10 * g18, 2) and app.sar_value(None) == 0.0
app.refresh_gold_value_label()
assert app.lbl_gold_value.text == (f"💰 الخزينة ≈ {en(1000 * g18, 0)} ر.س   ·   "
                                   f"الرصيد ≈ {en(round(1250.5 * g18, 2), 0)} ر.س"), app.lbl_gold_value.text
print(f"✔ عيار 18 افتراضياً: الخزينة 1000 جم × {g18} = {en(1000 * g18, 0)} ر.س (معادلة شريط السعر نفسها)")

app.set_value_karat("٢٤")
g24 = gold_price.gram_price(2650.0, "٢٤")
assert PREFS == {"gold_value_karat": "٢٤"} and app.gram_value_sar() == g24
assert en(1000 * g24, 0) in app.lbl_gold_value.text
app.set_value_karat("٩٩")
assert app.value_karat() == "٢٤" and PREFS["gold_value_karat"] == "٢٤"
fresh = App(); fresh.gold_watcher = Watcher()
assert fresh.value_karat() == "٢٤", "الاختيار المحفوظ يُقرأ عند التشغيل التالي"
PREFS["gold_value_karat"] = "عبث"
assert App().value_karat() == "١٨", "قيمة تالفة في الملف ترجع للافتراضي"
print("✔ اختيار العيار يعيد التقييم فوراً ويُحفظ للجهاز، والقيمة المجهولة أو التالفة تُتجاهل")

app.gold_watcher.ounce_price = None
app.refresh_gold_value_label()
assert app.sar_value(5) is None and "بانتظار سعر الذهب" in app.lbl_gold_value.text
app.gold_watcher = None
assert app.gram_value_sar() is None
print("✔ بلا سعر معروف: لا قيمة تُعرض (لا رقم مخترع)")

assert "from gold_price import GoldPriceWatcher, gram_price" in src
assert "self.refresh_gold_value_label()" in body("_on_gold_price")
assert "self.refresh_gold_value_label()" in body("recalculate_all")
bar = body("build_gold_price_bar")
assert "command=lambda label: self.set_value_karat(names[label])" in bar and "self.lbl_gold_value = " in bar
brk = body("show_gold_balance_breakdown")
assert "self.sar_value(value)" in brk and "self.sar_value(total)" in brk
print("✔ الشريط السفلي (اختيار العيار + القيمة) وتفصيل الرصيد يتحدّثان مع كل سعر وكل إعادة حساب")

print("\n✅ قيمة الأرصدة بالريال سليمة")
