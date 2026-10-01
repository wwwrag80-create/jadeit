# -*- coding: utf-8 -*-
"""
اللوحة الهادئة الموحّدة (الدفعة ١٣): ألوان أقل في الشاشات والجداول والأزرار.

  • الأزرار ثلاثة أساليب فقط: أساسي (لون رئيسي واحد)، وثانوي (رمادي فاتح)، وحذف
    (أحمر هادئ) — بدل ثمانية ألوان (أخضر، أزرق، ذهبي، أحمر، برتقالي، بنفسجي، رمادي، كحلي).
  • النصوص: عنوان كحلي هادئ، وعناوين الخانات رمادي داكن، والأحمر للأخطاء والسالب فقط.
  • الذهبي للشعار والخزينة وحدهما.
  • كل لون مقروء (≥ ٤٫٥:١) في المظهرين.
يقرأ الثوابت والدوال من البرنامج نفسه ويفحص كل أزرار الكود.
"""
import ast, io, re, sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
lines = src.split("\n")
tree = ast.parse(src)
APP = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
ROUTER = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ScreenRouter")

# الثوابت ودالة أسلوب الزر بترتيبها في الملف
WANT = {"UI", "BUTTON_STYLES", "BUTTON_ROLE_STYLE", "TREASURY_BAR_TEXT", "UI_TITLE", "_LEGACY_BUTTON_COLORS",
        "_LEGACY_HOVER_COLORS", "_ROLE_BY_HEX", "_CALM_TITLE", "_CALM_LABEL", "_LEGACY_TEXT_COLORS"}
ns = {}
for n in tree.body:
    names = {getattr(t, "id", None) for t in getattr(n, "targets", [])}
    if (isinstance(n, ast.Assign) and names & WANT) or \
            (isinstance(n, ast.For) and getattr(n.target, "id", "") == "_role") or \
            (isinstance(n, ast.FunctionDef) and n.name == "button_style_for"):
        exec(compile(ast.Module([n], []), TARGET, "exec"), ns)
UI, STYLES, button_style_for = ns["UI"], ns["BUTTON_STYLES"], ns["button_style_for"]


def lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def method(name, cls=APP):
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


# ═══ ١) ثلاثة أساليب أزرار فقط، مقروءة في المظهرين ═══
assert set(STYLES) == {"primary", "secondary", "danger"}, STYLES
assert set(ns["BUTTON_ROLE_STYLE"].values()) == {"primary", "secondary", "danger"}
for name, st in STYLES.items():
    for i, mode in enumerate(("فاتح", "داكن")):
        c = contrast(st["text_color"][i], st["fg_color"][i])
        assert c >= 4.5, (name, mode, round(c, 2))
print("✔ ثلاثة أساليب أزرار فقط (أساسي، ثانوي، حذف) — نصها مقروء ≥ ٤٫٥:١ في الفاتح والداكن")

# كل الأدوار القديمة (أخضر، ذهبي، برتقالي، بنفسجي، كحلي…) تُرسم بأحد الثلاثة
for old in list(ns["_LEGACY_BUTTON_COLORS"]) + ["#d4af37", "#b8952e"]:
    assert button_style_for(old) in STYLES, old
for role in ("primary", "success", "navy", "violet", "neutral", "edit", "warning", "danger"):
    assert button_style_for(UI[role]) in STYLES, role
# زر «دخول» الذهبي في شاشة الدخول الداكنة (هوية البرنامج) لا يُترجَم إلى زر رمادي فاتح
login = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LoginWindow")
login_gold = next(ast.literal_eval(x.value) for x in login.body if isinstance(x, ast.Assign)
                  and getattr(x.targets[0], "id", "") == "_GOLD")
assert button_style_for(login_gold) is None and "fg_color=self._GOLD" in "\n".join(
    lines[login.lineno - 1:login.end_lineno])
assert button_style_for("#1e8449") == button_style_for("#1f77b4") == "primary"          # حفظ/ترحيل = أساسي
assert button_style_for("#b8860b") == button_style_for("#555555") == "secondary"         # تعديل/عرض = ثانوي
assert button_style_for("#8b0000") == "danger"                                            # حذف = أحمر هادئ
print("✔ الأخضر والأزرق والكحلي والبنفسجي ← أساسي واحد؛ الذهبي والبرتقالي والرمادي ← ثانوي؛ الأحمر ← حذف هادئ؛"
      " وزر «دخول» الذهبي في شاشة الدخول باقٍ كما هو")

# ═══ ٢) كل أزرار الكود فعلاً: لون تعبئتها بعد الترجمة من الأساليب الثلاثة ═══
fills, raw = {}, []
for node in ast.walk(tree):
    if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "CTkButton"):
        continue
    kw = {k.arg: k.value for k in node.keywords if k.arg}
    fg = kw.get("fg_color")
    if fg is None:
        fills["(افتراضي = أساسي)"] = fills.get("(افتراضي = أساسي)", 0) + 1
        continue
    try:
        val = eval(compile(ast.Expression(fg), "x", "eval"), {"UI": UI})
    except Exception:
        continue              # تعبير شرطي/متغيّر يُحسب وقت التشغيل (يمرّ بالترجمة نفسها)
    if isinstance(val, str) and val != "transparent":
        style = button_style_for(val)
        if style is None:
            raw.append((node.lineno, val))
        else:
            fills[style] = fills.get(style, 0) + 1
assert not raw, raw
total = sum(fills.values())
print(f"✔ {total} زراً في الكود: لا لون تعبئة خارج الأساليب الثلاثة ({fills})")

# ═══ ٣) النصوص: أربعة ألوان فقط بدل تسعة ═══
legacy = ns["_LEGACY_TEXT_COLORS"]
light_colors = {v[0].lower() for v in legacy.values()}
assert len(light_colors) == 4, light_colors           # عنوان، عنوان خانة، أحمر، رمادي ثانوي
assert legacy["#d4af37"] == legacy["#2ecc71"] == legacy["#e67e22"] == legacy["#f1c40f"] == ns["_CALM_TITLE"]
assert legacy["#1f77b4"] == ns["_CALM_LABEL"]
assert legacy["#e74c3c"][0].lower() == UI["danger"].lower()
for old, (light, dark) in legacy.items():
    assert contrast(light, "#FFFFFF") >= 4.5 and contrast(light, UI["canvas"]) >= 4.5, old
    assert contrast(dark, "#151A21") >= 4.5 and contrast(dark, "#1D232B") >= 4.5, old
print("✔ النصوص الملوّنة القديمة (ذهبي، أخضر، برتقالي، أصفر، بنفسجي) ← كحلي هادئ واحد للعناوين؛ "
      "الأزرق ← رمادي داكن للخانات؛ الأحمر للأخطاء والسالب فقط — كلها ≥ ٤٫٥:١")

# ═══ ٤) الذهبي للشعار والخزينة وحدهما ═══
hdr = method("_ensure_header", ROUTER)
pills = re.findall(r'pill\((\(.*?\)), (\(.*?\))\)', hdr)
bgs = {eval(b, {"UI": UI})[0] for b, _ in pills}
fgs = [eval(f, {"UI": UI})[0] for _, f in pills]
assert len(pills) == 3 and len(bgs) == 1, (pills, bgs)
assert "#F0CF6A" in fgs and len(set(fgs)) == 2
assert all(contrast(f, next(iter(bgs))) >= 4.5 for f in fgs)
print("✔ شارات الإطار العلوي بخلفية واحدة؛ الخزينة وحدها بالذهبي (لون الشعار) والبقية بلون هادئ")
seg_src = method("style_segment_buttons")
assert 'UI["gold"]' not in seg_src and 'UI["primary"]' in seg_src and '(UI["ink"], "#E6EDF3")' in seg_src
print("✔ أزرار الأقسام: المختار باللون الرئيسي (كان ذهبياً)، والبقية بيضاء بنص داكن (كان أزرق)")

# ═══ ٥) الشاشات: الخسائر والرئيسية والأشرطة الداكنة ═══
m = re.search(r'calm_fg, calm_bg = (\(.*?\)), (\(.*?\))', src)
assert m and src.count("calm_fg, calm_bg)") + src.count("calm_fg, calm_bg,") == 4, "مربعات الخسائر"
print("✔ شاشة الخسائر: المربعات الأربعة لكل صندوق بلون واحد (كانت أحمر وذهبي وأزرق وأخضر)")
assert 'tint = (UI["primary_soft"], "#1B2B45")' in src and 'UI["warning_soft"], "#33261A"' not in src
assert 'fg_color=(UI["success_soft"], "#16261a")' not in src
assert 'fg_color=(UI["gold_soft"], UI["gold_soft"])' not in src
print("✔ الرئيسية: بطاقات الملخص بخلفية أيقونة واحدة، وشريط الرصيد الحالي محايد، وزر «أخرى» محايد")
for dark in ('fg_color="#1a1a1a"', 'fg_color="#2c3e50"'):
    assert dark not in src, dark
print("✔ لا أشرطة داكنة وسط الشاشات الفاتحة (أشرطة الإجماليات صارت محايدة بنص كحلي)")

# ═══ ٦) الجداول: التحديد بدرجة من اللون الرئيسي، والقوائم المنسدلة بشكل الخانات ═══
design_node = next(x for x in APP.body if isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == "DESIGN")
DESIGN = ast.literal_eval(design_node.value)
sel = DESIGN["light"]["sel_bg"].lstrip("#")
r, g, b = (int(sel[i:i + 2], 16) for i in (0, 2, 4))
assert b > r and b >= g, DESIGN["light"]["sel_bg"]                 # أزرق فاتح لا أصفر
assert contrast(DESIGN["light"]["sel_text"], DESIGN["light"]["sel_bg"]) >= 7
assert contrast(DESIGN["dark"]["sel_text"], DESIGN["dark"]["sel_bg"]) >= 4.5
theme = "\n".join(lines[next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                             and n.name == "_apply_theme_defaults").lineno - 1:][:60])
assert 't["CTkOptionMenu"].update(corner_radius=8, fg_color=["#FFFFFF", "#1E242C"]' in theme
print("✔ الصف المحدد بأزرق فاتح هادئ (كان أصفر)، والقوائم المنسدلة بيضاء كالخانات (كانت زرقاء ممتلئة)")

for tree_tag in ('self.normalize_tree_tags(self.report_tree)', 'self.normalize_tree_tags(self.account_statement_tree)'):
    assert tree_tag in src, tree_tag
print("✔ وسوم الجداول (الإجمالي والأقسام والافتتاحي) تمرّ باللوحة الهادئة: كحلي للإجماليات، أحمر للسالب")

print("\n✅ لوحة هادئة موحّدة: لون رئيسي واحد، رمادي للثانوي، أحمر للحذف والسالب، وذهبي للشعار والخزينة")
