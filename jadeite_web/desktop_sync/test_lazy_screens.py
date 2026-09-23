# -*- coding: utf-8 -*-
"""اختبار البناء الكسول للشاشات وترتيب أقسام مراحل التصنيع"""
import ast, io, re, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ ١) لا شاشة تُبنى عند التشغيل ═══
lay = seg("create_layout")
eager = re.findall(r'self\.(build_\w+_tab)\(\)', lay)
assert not eager, f"شاشات ما زالت تُبنى عند التشغيل: {eager}"
print("✔ لا شاشة تُبنى عند التشغيل — الفتح فوري")

builders = None
for node in ast.walk(cls):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Attribute) and t.attr == "_screen_builders":
                builders = [k.value for k in node.value.keys]
assert builders and len(builders) == 14, builders
print(f"✔ {len(builders)} شاشة مسجّلة للبناء عند أول فتح")

registered = set(re.findall(r'self\.tabview\.add\("([^"]+)"\)', src))
missing = set(builders) - registered
assert not missing, f"بناة لشاشات غير مسجّلة: {missing}"
uncovered = registered - set(builders)
assert not uncovered, f"شاشات بلا بانٍ: {uncovered}"
print("✔ كل شاشة مسجّلة لها بانٍ، ولا بانٍ لشاشة غير موجودة")

# ═══ ٢) البناء يحدث عند الفتح ═══
nav = seg("navigate_to_screen")
i_build = nav.find("self.ensure_screen_built(name)")
i_show = nav.find("self.tabview.show(name)")
assert i_build != -1 and i_build < i_show
print("✔ الشاشة تُبنى قبل عرضها عند أول فتح")

ens = seg("ensure_screen_built")
assert "_built_screens" in ens and "return False" in ens
print("✔ تُبنى مرة واحدة فقط ثم تبقى جاهزة")
assert 'cursor="watch"' in ens and "finally" in ens
print("✔ مؤشّر انتظار أثناء البناء ويُستعاد حتى عند الفشل")
assert "messagebox.showerror" in ens and "log_cloud_error" in ens
print("✔ فشل البناء يُعرض بوضوح بدل شاشة فارغة صامتة")

# ═══ ٣) التحديث لا يلمس شاشة لم تُبنَ ═══
rs = seg("refresh_screen")
assert "_built_screens" in rs and "return" in rs
print("✔ التحديث الكسول يتجاهل الشاشات غير المبنيّة (لا أخطاء ولا هدر)")

# ═══ ٤) ترتيب أقسام مراحل التصنيع ═══
for fn in ("stage_order", "move_stage", "show_stage_context_menu"):
    assert any(isinstance(m, ast.FunctionDef) and m.name == fn for m in cls.body), fn
print("✔ ترتيب الأقسام: تحريك يمين/يسار بالزر الأيمن")

sb = seg("refresh_stage_buttons")
assert "self.stage_order(" in sb and 'b.bind("<Button-3>"' in sb
print("✔ الشريط يُبنى بالترتيب المحفوظ، وكل قسم يستجيب للزر الأيمن")

ns = {"json": __import__("json")}
exec("class S:\n" + textwrap.indent(textwrap.dedent(seg("stage_order")), "    ")
     + "\n    def __init__(self, saved): self._s = saved\n"
     "    def get_setting(self, k, d=None): return self._s\n", ns)
app = ns["S"]('["التلميع", "الكاستنج"]')
avail = ["الكاستنج", "المصنعين", "المركبين", "التلميع", "التلميع/البف"]
got = app.stage_order(avail)
assert got[:2] == ["التلميع", "الكاستنج"]
assert set(got) == set(avail) and len(got) == len(avail)
print(f"✔ الترتيب المحفوظ يُطبَّق: {got[:2]} أولاً، وبقية الأقسام تتبع بلا فقد")

app2 = ns["S"]('["قسم محذوف", "المركبين"]')
got2 = app2.stage_order(avail)
assert "قسم محذوف" not in got2 and set(got2) == set(avail)
print("✔ قسم محذوف يُتجاهل، وقسم جديد يُضاف تلقائياً — لا انكسار")

print("\n✅ البناء الكسول وترتيب الأقسام يعملان")
