# -*- coding: utf-8 -*-
"""1.98 هوية المصنع — «لكل مصنع نظامه وبياناته»:
  • الشعار بلا خلفية ولا إطار (brand_logo_cleanup): خلفية فاتحة أو داكنة، وإطارٌ حول الشعار، وصورة شفافة أصلاً —
    والشارة الملوّنة الممتلئة والصورة التي تملأ إطارها تبقيان؛
  • بيانات الترويسة لكل حساب (الافتراضي هوية جاديت كما كانت حرفياً)، والسطر الفارغ لا يُطبع؛
  • الشعار يُحفظ/يُحذف/يعود لشعار جاديت، والمعاينة قبل الحفظ لا تكتب شيئاً؛
  • نسخة العميل تحفظ الهوية على الجهاز لشاشة الدخول؛
  • قالب رقم التشغيل في الرابط SVG صالحٌ بقيمه (مُهرَّبة) وشعار المصنع؛
  • كل مطبوعٍ وواجهةٍ تأخذ من الهوية (لا من ثوابت جاديت)."""
import ast, base64, io, json, os, sys, tempfile, textwrap
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
methods = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}


def member(name):
    node = methods.get(name) or next(m for m in cls.body if isinstance(m, ast.Assign)
                                     and getattr(m.targets[0], "id", "") == name)
    deco = "".join(f"@{ast.get_source_segment(src, d)}\n" for d in getattr(node, "decorator_list", []))
    return deco + textwrap.dedent(ast.get_source_segment(src, node))


def pixels(img):
    return list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())


def module_src(name):
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(src, node)


def module_const(name):
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name)
    return ast.get_source_segment(src, node)


# ═══ ١) الشعار بلا خلفية ولا إطار ═══
ns = {"Image": Image}
for name in ("_brand_crop", "_brand_ring", "_brand_clear_connected", "brand_logo_cleanup"):
    exec(module_src(name), ns)
cleanup = ns["brand_logo_cleanup"]


def alpha_at(img, x, y):
    return img.getpixel((x, y))[3]


def noisy(img, amount=6):
    """ضجيج JPEG الخفيف على الخلفية"""
    px = img.load()
    for y in range(0, img.height, 3):
        for x in range(0, img.width, 3):
            r, g, b, a = px[x, y]
            d = ((x * 7 + y * 13) % (2 * amount + 1)) - amount
            px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)), max(0, min(255, b + d)), a)
    return img


# أ) خلفية بيضاء (بضجيج): دائرة حمراء وشريط داكن كالكلمات ← الخلفية شفافة والقصّ على الرسم
img = Image.new("RGBA", (600, 400), (252, 252, 250, 255))
d = ImageDraw.Draw(img)
d.ellipse((200, 80, 320, 200), fill=(200, 30, 40, 255))
d.ellipse((240, 120, 280, 160), fill=(252, 252, 250, 255))         # فراغٌ داخل الدائرة (لا يتصل بالخارج)
d.rectangle((150, 240, 450, 280), fill=(30, 30, 40, 255))
out = cleanup(noisy(img))
assert out.mode == "RGBA"
assert out.width < 340 and out.height < 230, f"قُصّت على الرسم ({out.size})"
assert alpha_at(out, 0, 0) == 0 and alpha_at(out, out.width - 1, 0) == 0, "الخلفية شفافة"
bbox = out.getchannel("A").getbbox()
assert bbox and bbox[2] - bbox[0] >= 290, "الرسم والكلمات كاملة"
cx, cy = out.width // 2, None
# مركز الدائرة الأحمر الداخلي (الفراغ المغلق) يبقى كما هو — ليس متصلاً بالخارج
red = [(x, y) for y in range(out.height) for x in range(out.width) if out.getpixel((x, y))[:3] == (200, 30, 40)]
assert red and all(out.getpixel(p)[3] == 255 for p in red[:50]), "ألوان الشعار معتمة"
print("✔ خلفية فاتحة (بضجيج JPEG): تصير شفافة، والصورة تُقصّ على الرسم والكلمات")

# ب) إطارٌ حول الشعار: خلفية بيضاء، مربعٌ أسود رفيع، داخله أبيض، وفيه نجمة زرقاء ← لا إطار ولا خلفية
img = Image.new("RGBA", (500, 500), (255, 255, 255, 255))
d = ImageDraw.Draw(img)
d.rectangle((40, 40, 460, 460), outline=(20, 20, 20, 255), width=6)
d.polygon([(250, 150), (290, 240), (380, 250), (300, 300), (330, 390), (250, 330), (170, 390), (200, 300),
           (120, 250), (210, 240)], fill=(30, 80, 200, 255))
out = cleanup(img)
assert out.width < 300 and out.height < 280, f"الإطار أُزيل والقصّ على النجمة ({out.size})"
assert not any(out.getpixel((x, y))[:3] == (20, 20, 20) and out.getpixel((x, y))[3] > 200
               for y in range(out.height) for x in range(out.width)), "لا يبقى شيءٌ من الإطار"
print("✔ إطارٌ حول الشعار: يُزال مع الخلفية التي داخله، فيبقى الرسم وحده")

# ج) خلفية داكنة: شعار ذهبي على أسود ← الأسود شفاف
img = Image.new("RGBA", (400, 300), (8, 8, 10, 255))
ImageDraw.Draw(img).ellipse((120, 90, 280, 210), fill=(212, 175, 55, 255))
out = cleanup(img)
assert alpha_at(out, 0, 0) == 0 and out.width < 200, "الخلفية الداكنة تزول أيضاً"
print("✔ خلفية داكنة: تزول أيضاً")

# د) شارة ملوّنة ممتلئة عليها كلمات بيضاء: الشارة جزءٌ من الشعار تبقى، والبيض داخلها لا يُمسّ
img = Image.new("RGBA", (500, 300), (255, 255, 255, 255))
d = ImageDraw.Draw(img)
d.rounded_rectangle((60, 60, 440, 240), radius=30, fill=(16, 120, 80, 255))
d.rectangle((120, 130, 380, 170), fill=(255, 255, 255, 255))
out = cleanup(img)
opaque = sum(1 for a in pixels(out.getchannel("A")) if a > 200)
assert opaque > 0.7 * out.width * out.height, "الشارة باقية (لا تُحذف كأنها خلفية)"
white_inside = sum(1 for p in pixels(out) if p[3] > 200 and p[:3] == (255, 255, 255))
assert white_inside > 0.8 * 260 * 40, "الكلمات البيضاء داخل الشارة باقية"
print("✔ شارة ملوّنة عليها كلمات: تبقى كاملة بكلماتها")

# هـ) شفافة أصلاً: تُقصّ فقط
img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
ImageDraw.Draw(img).ellipse((100, 150, 200, 250), fill=(90, 40, 160, 255))
out = cleanup(img)
assert out.width < 115 and out.height < 115 and alpha_at(out, out.width // 2, out.height // 2) == 255
print("✔ صورة شفافة أصلاً: تُقصّ على ما فيها فقط")

# و) صورةٌ تملأ إطارها (تدرّج — لا لون خلفية واحد) تبقى كما هي، والبيضاء كلها لا تصير فراغاً
img = Image.new("RGBA", (256, 128))
img.putdata([(x, y * 2, 255 - x, 255) for y in range(128) for x in range(256)])
out = cleanup(img)
assert out.size == (256, 128) and min(pixels(out.getchannel("A"))) == 255, "الصورة الممتلئة لا يُمسّ منها شيء"
blank = cleanup(Image.new("RGB", (200, 100), (255, 255, 255)))
assert blank.getchannel("A").getbbox() is not None, "صورة بيضاء كلها لا تُعاد فارغة"
big = cleanup(Image.new("RGB", (4000, 2000), (255, 255, 255)))
assert max(big.size) <= 1000, "الصورة الكبيرة تُصغَّر قبل المعالجة"
print("✔ الصورة التي تملأ إطارها تبقى، والبيضاء كلها لا تصير فراغاً، والكبيرة تُصغَّر")


# ═══ ٢) بيانات المصنع لكل حساب ═══
class Stub:
    pass


body = "\n".join(member(n) for n in ("LETTERHEAD_AR", "LETTERHEAD_EN", "BRAND_FIELDS", "BRAND_DEFAULT")) + "\n\n"
for n in ("_brand_setting", "brand_identity", "brand_is_custom", "brand_display_name", "letterhead_ar",
          "letterhead_en", "brand_logo_image", "brand_logo_bytes", "save_brand_identity"):
    body += member(n) + "\n\n"
errors = []
env = {"json": json, "io": io, "base64": base64, "Image": Image, "sqlite3": __import__("sqlite3"),
       "log_cloud_error": lambda *a: errors.append(a)}
exec(module_const("BRAND_KEY") + "\n" + module_const("BRAND_LOGO_KEY") + "\n" + module_const("BRAND_LOGO_MAX"), env)
exec("class App:\n" + textwrap.indent(body, "    "), env)
App = env["App"]
JADEITE_LOGO = Image.new("RGBA", (30, 60), (0, 128, 0, 255))
App.default_brand_logo = staticmethod(lambda: JADEITE_LOGO.copy())


def make_app():
    app = App()
    store = {}
    app.db_path = "x.db"
    app.get_setting = lambda k, default=None: store.get(k, default)
    app.set_setting = lambda k, v: store.__setitem__(k, v)
    app.changed = 0

    def changed():
        app.changed += 1
        app.__dict__.pop("_brand_logo_cache", None)
    app.brand_changed = changed
    app.client_name = "حساب العميل"
    return app, store


app, store = make_app()
assert app.letterhead_ar() == App.LETTERHEAD_AR and app.letterhead_en() == App.LETTERHEAD_EN, \
    "الافتراضي هوية جاديت كما كانت حرفياً"
assert not app.brand_is_custom() and app.brand_display_name() == "حساب العميل"
assert app.brand_identity()["short_ar"] == "مصنع جاديت"
assert app.brand_logo_image().size == (30, 60), "الشعار الافتراضي: جاديت"

data = {"name_ar": "  مصنع النور  ", "short_ar": "", "addr1_ar": "جدة - الصناعية", "addr2_ar": "", "cr": "4030000000",
        "name_en": "Al-Noor Factory", "addr1_en": "Jeddah", "addr2_en": "", "extra": "يُهمل"}
logo = Image.new("RGBA", (1600, 400), (180, 20, 20, 255))
app.save_brand_identity(data, "new", logo)
saved = json.loads(store["brand_identity"])
assert "extra" not in saved and saved["name_ar"] == "مصنع النور", "تُحفظ حقول الهوية وحدها مقصوصة المسافات"
assert app.letterhead_ar() == ("مصنع النور", "جدة - الصناعية", "سجل تجاري: 4030000000"), "السطر الفارغ لا يُطبع"
assert app.letterhead_en() == ("Al-Noor Factory", "Jeddah", "C.R: 4030000000")
assert app.brand_identity()["short_ar"] == "مصنع النور", "الاسم المختصر الفارغ ← اسم المصنع"
assert app.brand_is_custom() and app.brand_display_name() == "مصنع النور" and app.changed == 1
got = app.brand_logo_image()
assert got.size == (800, 200), "الشعار يُحفظ بأطول ضلع ٨٠٠ (يكفي للطباعة) بنسبته"
got.putpixel((0, 0), (0, 0, 0, 0))
assert app.brand_logo_image().getpixel((0, 0))[3] == 255, "كل استدعاءٍ نسخةٌ جديدة (لا يُفسد المخزّن)"

app.save_brand_identity(dict(data, cr=""), "keep")
assert app.letterhead_ar() == ("مصنع النور", "جدة - الصناعية") and app.brand_logo_image().size == (800, 200), \
    "keep: الشعار كما هو، وبلا سجل لا يُطبع سطره"
app.save_brand_identity(data, "none")
assert app.brand_logo_image() is None and store["brand_logo_png"] == "none", "حذف الشعار"
app.save_brand_identity(data, "default")
assert app.brand_logo_image().size == (30, 60) and store["brand_logo_png"] == "", "العودة لشعار جاديت"

# المعاينة قبل الحفظ تقرأ البديل ولا تكتب
before = dict(store)
app.__dict__["_brand_preview"] = {"brand_identity": json.dumps({"name_ar": "معاينة"}, ensure_ascii=False),
                                  "brand_logo_png": "none"}
assert app.letterhead_ar()[0] == "معاينة" and app.brand_logo_image() is None
del app.__dict__["_brand_preview"]
app.__dict__.pop("_brand_logo_cache", None)
assert store == before and app.letterhead_ar()[0] == "مصنع النور", "المعاينة لا تغيّر المحفوظ"

# قيمٌ تالفة لا توقف البرنامج
store["brand_identity"] = "{not json"
store["brand_logo_png"] = "@@@"
assert app.letterhead_ar() == App.LETTERHEAD_AR and app.brand_logo_image().size == (30, 60) and errors
store["brand_identity"] = json.dumps(["list"])
assert app.letterhead_ar() == App.LETTERHEAD_AR
# حسابٌ آخر (قاعدة أخرى) هويته مستقلة
other, _s = make_app()
assert other.letterhead_ar() == App.LETTERHEAD_AR
print("✔ بيانات الترويسة لكل حساب: الافتراضي جاديت حرفياً، والفارغ لا يُطبع، والشعار يُحفظ/يُحذف/يعود، والمعاينة لا تكتب")

# ═══ ٣) نسخة العميل: الهوية على الجهاز لشاشة الدخول ═══
tmp = tempfile.mkdtemp()
dev = {"os": os, "json": json, "APP_DATA_DIR": tmp, "IS_ADMIN_BUILD": False, "log_cloud_error": lambda *a: None}
exec(module_const("BRAND_DEVICE_FILE") + "\n" + module_src("device_brand") + "\n" + module_src("write_device_brand"), dev)
assert dev["device_brand"]() == (None, "", False), "لا هوية محفوظة: جاديت"
dev["write_device_brand"]("مصنع النور", Image.new("RGBA", (40, 20), (1, 2, 3, 255)))
path, name, no_logo = dev["device_brand"]()
assert name == "مصنع النور" and path and Image.open(path).size == (40, 20) and not no_logo
dev["write_device_brand"]("مصنع النور", None)
assert dev["device_brand"]() == (None, "مصنع النور", True), "بلا شعار: الاسم وحده"
dev["write_device_brand"]("", None)
assert dev["device_brand"]() == (None, "", False) and not os.listdir(tmp), "اسمٌ فارغ: تعود هوية جاديت"
dev["IS_ADMIN_BUILD"] = True
dev["write_device_brand"]("مصنع", None)
assert dev["device_brand"]() == (None, "", False), "برنامج المدير لا يأخذ هوية جهاز"
print("✔ نسخة العميل تحفظ اسم المصنع وشعاره على الجهاز لشاشة الدخول (وبرنامج المدير لا)")

# ═══ ٤) قالب رقم التشغيل في الرابط: SVG صالح بقيمه وشعاره ═══
exec(module_src("live_escape"), env)
exec("class Tpl:\n" + textwrap.indent(member("live_template_svg") + "\n\n" + member("brand_logo_bytes"), "    "), env)
Tpl = env["Tpl"]
t = Tpl()
t.SB_PAPER = {"page": "#FFFFFF", "line": "#3F4650", "ink": "#111", "muted": "#888", "posted": "#E3F0FF",
              "ext": "#E5F6EA", "head": "#DFF"}
t.set_voucher_layout = lambda compact=True: {"PW": 595.0, "PH": 842.0}
t.sb_paper_spec = lambda: [("box", 10, 10, 585, 60, "head"), ("text", 300, 35, "مصنع النور", 14, 200, 30),
                           ("line", 10, 70, 585, 1.0), ("logo", 580, 15, 55),
                           ("cell", "customer", 10, 80, 200, 100, 10), ("cell", "p1", 200, 80, 300, 100, 10),
                           ("cell", "p2", 300, 80, 400, 100, 10), ("calc", "net", 400, 80, 585, 100, 10)]
t.sb_cell_values = lambda q: {"set_no": ("A-1", None), "customer": ('<علي & "شركاه">', None), "p1": ("12.5", "posted"),
                              "p2": ("3", "ext"), "net": ("9.50", None)}
t.brand_logo_image = lambda: Image.new("RGBA", (80, 40), (200, 0, 0, 255))
svg = t.live_template_svg("A-1")
root = ET.fromstring(svg)                                 # SVG صالح (والقيم مُهرَّبة)
ns_svg = "{http://www.w3.org/2000/svg}"
texts = [e.text for e in root.iter(ns_svg + "text")]
assert '<علي & "شركاه">' in texts and "12.5" in texts and "9.50" in texts and "مصنع النور" in texts
assert [e.get("direction") for e in root.iter(ns_svg + "text") if e.text == "12.5"] == ["ltr"]
assert [e.get("direction") for e in root.iter(ns_svg + "text") if e.text == "مصنع النور"] == ["rtl"]
fills = [e.get("fill") for e in root.iter(ns_svg + "rect")]
assert "#E3F0FF" in fills and "#E5F6EA" in fills, "المُرحَّل والآتي من فاتورة البيع بلونيهما"
imgs = list(root.iter(ns_svg + "image"))
assert len(imgs) == 1 and imgs[0].get("href").startswith("data:image/png;base64,"), "شعار المصنع مضمّنٌ في القالب"
assert abs(float(imgs[0].get("width")) - 80.0) < 0.1 and float(imgs[0].get("x")) < 580, "الشعار بنسبته عند طرفه"
t.brand_logo_image = lambda: None
assert not list(ET.fromstring(t.live_template_svg("A-1")).iter(ns_svg + "image")), "بلا شعار: لا صورة"
print("✔ قالب رقم التشغيل في الرابط: SVG صالحٌ بقيمه المُهرَّبة وألوانها وشعار المصنع")

# ═══ ٥) كل مطبوعٍ وواجهةٍ تأخذ من الهوية ═══
lh = member("draw_pdf_letterhead")
assert "self.letterhead_ar()" in lh and "self.letterhead_en()" in lh and "self.LETTERHEAD_AR" not in lh
assert "self.brand_logo_image()" in member("sb_logo_image")
assert 'brand_identity()["short_ar"]' in member("sb_paper_spec")
assert "self.live_template_svg(q)" in member("live_view_set")
assert "self.brand_display_name()" in member("live_html")
home = member("build_home_screen")
assert "self.render_home_logo()" in home and "brand_is_custom" in member("render_home_logo")
assert "brand_is_custom" in member("build_sidebar")
changed = member("brand_changed")
for call in ('"build_sidebar"', '"render_home_logo"', "sb_layout_paper(force=True)", "write_device_brand("):
    assert call in changed, f"الحفظ يطبّق الهوية فوراً ({call})"
i = src.index('text="🏷️ هوية المصنع"')
assert 'if not getattr(self, "view_only", False):' in src[i - 600:i], "زر الهوية لا يظهر في عرض المدير للقراءة"
assert "command=self.open_brand_identity_window" in src[i:i + 600]
assert "device_brand()" in src[src.index("class LoginWindow"):], "شاشة الدخول تأخذ هوية الجهاز"
win = member("open_brand_identity_window")
for part in ("brand_logo_cleanup(", "tk_background", "filedialog.askopenfilename", "save_brand_identity(",
             "preview_brand_letterhead("):
    assert part in win, f"نافذة الهوية: {part}"
print("✔ الترويسة وقالب رقم التشغيل والتذاكر والشريط الجانبي والرئيسية والرابط وشاشة الدخول: من هوية المصنع")
print("✔ هوية المصنع 1.98 سليمة")
